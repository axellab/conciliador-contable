"""Paso 3: conciliación bancaria contra los comprobantes.

Lee el extracto (CSV o Excel, con formato argentino de números) y busca, para cada débito,
la factura que paga:
  a) mismo importe (y proveedor/CUIT en el concepto si está),
  b) un pago que cancela varias facturas del mismo proveedor,
  c) pagos con diferencia (detecta dígitos invertidos, el clásico "divisible por 9").
Lo que no tiene factura se clasifica con las reglas de referencias/reglas_banco.json
(comisiones, impuestos, percepciones, cobros) y lo que queda es un pago sin comprobante.

Uso:
  python conciliar.py --trabajo <carpeta_de_trabajo> --extracto <archivo_del_banco>
"""
import argparse
import csv
import io
import re
from datetime import timedelta
from itertools import combinations
from pathlib import Path

from comun import (REFERENCIAS, cargar_json, coincidencia_nombre, descripcion_comprobante, fecha_ar, fecha_iso,
                   fmt_pesos, formatear_cuit, guardar_json, normalizar, parsear_fecha, parsear_importe, preparar_consola, r2,
                   solo_digitos, titulo_paso)

COLUMNAS = {
    "fecha": ["FECHA", "FECHA MOV", "FECHA OPERACION", "FECHA VALOR"],
    "concepto": ["CONCEPTO", "DESCRIPCION", "DETALLE", "MOVIMIENTO"],
    "referencia": ["REFERENCIA", "COMPROBANTE", "NRO COMPROBANTE", "OBSERVACIONES", "INFORMACION ADICIONAL"],
    "debito": ["DEBITO", "DEBITOS", "DEBE", "EGRESO", "EGRESOS"],
    "credito": ["CREDITO", "CREDITOS", "HABER", "INGRESO", "INGRESOS"],
    "importe": ["IMPORTE", "MONTO"],
    "saldo": ["SALDO"],
}


def leer_filas(ruta):
    ruta = Path(ruta)
    if ruta.suffix.lower() == ".csv":
        texto = ruta.read_bytes().decode("utf-8-sig", errors="replace")
        primera = next((l for l in texto.splitlines() if l.count(";") + l.count(",") + l.count("\t") >= 3), "")
        delimitador = max([";", "\t", ","], key=primera.count)
        return [fila for fila in csv.reader(io.StringIO(texto), delimiter=delimitador)]
    import openpyxl
    libro = openpyxl.load_workbook(ruta, data_only=True)
    hoja = libro.worksheets[0]
    return [["" if v is None else v for v in fila] for fila in hoja.iter_rows(values_only=True)]


def mapear_encabezado(fila):
    nombres = [normalizar(c) for c in fila]
    mapa = {}
    for campo, alias in COLUMNAS.items():
        for i, n in enumerate(nombres):
            if n in alias and campo not in mapa and i not in mapa.values():
                mapa[campo] = i
    if "fecha" in mapa and "concepto" in mapa and ("debito" in mapa or "importe" in mapa):
        return mapa
    return None


def leer_extracto(ruta):
    filas = leer_filas(ruta)
    mapa, inicio = None, None
    for i, fila in enumerate(filas[:40]):
        mapa = mapear_encabezado(fila)
        if mapa:
            inicio = i + 1
            break
    if not mapa:
        raise SystemExit("No encontré la fila de encabezados del extracto (Fecha, Concepto, Débito/Crédito o Importe, Saldo).")

    def celda(fila, campo):
        i = mapa.get(campo)
        return fila[i] if i is not None and i < len(fila) else ""

    movimientos, saldo_inicial, saldo_final_informado = [], None, None
    for fila in filas[inicio:]:
        if not any(str(c).strip() for c in fila):
            continue
        concepto = str(celda(fila, "concepto")).strip()
        concepto_n = normalizar(concepto)
        saldo = parsear_importe(celda(fila, "saldo"))
        if re.match(r"SALDO (ANTERIOR|INICIAL)", concepto_n):
            saldo_inicial = saldo
            continue
        if re.match(r"SALDO (FINAL|ACTUAL|AL)", concepto_n):
            saldo_final_informado = saldo
            continue
        fecha = parsear_fecha(celda(fila, "fecha"))
        if not fecha:
            continue
        if "debito" in mapa:
            debito = abs(parsear_importe(celda(fila, "debito")) or 0)
            credito = abs(parsear_importe(celda(fila, "credito")) or 0)
        else:
            valor = parsear_importe(celda(fila, "importe")) or 0
            debito, credito = (abs(valor), 0) if valor < 0 else (0, valor)
        if not debito and not credito:
            continue
        movimientos.append({
            "fecha": fecha_iso(fecha), "concepto": concepto, "referencia": str(celda(fila, "referencia")).strip(),
            "tipo": "debito" if debito else "credito", "importe": r2(debito or credito), "saldo": saldo,
        })
        if saldo is not None:
            saldo_final_informado = saldo
    for i, m in enumerate(movimientos, 1):
        m["id"] = f"B{i:02d}"
    return movimientos, saldo_inicial, saldo_final_informado


def solo_digitos_con_espacios(texto):
    """Quita guiones dentro de los números (30-71234560-1 -> 30712345601) y deja el resto separado."""
    return re.sub(r"(?<=\d)-(?=\d)", "", texto)


def es_transposicion(a, b):
    """True si a y b difieren solo por dos dígitos contiguos intercambiados."""
    x, y = f"{a:.2f}".replace(".", ""), f"{b:.2f}".replace(".", "")
    if len(x) != len(y) or x == y:
        return False
    distintos = [i for i in range(len(x)) if x[i] != y[i]]
    return len(distintos) == 2 and distintos[1] == distintos[0] + 1 and x[distintos[0]] == y[distintos[1]] and x[distintos[1]] == y[distintos[0]]


def vinculo_proveedor(comp, mov):
    texto = f"{mov['concepto']} {mov['referencia']}"
    cuit = solo_digitos((comp.get("emisor") or {}).get("cuit"))
    if cuit and cuit in solo_digitos(texto):
        return 1.0
    return coincidencia_nombre((comp.get("emisor") or {}).get("razon_social"), texto)


def en_ventana(comp, mov, antes, despues):
    f_comp, f_mov = parsear_fecha(comp.get("fecha")), parsear_fecha(mov["fecha"])
    if not f_comp or not f_mov:
        return True
    return f_comp - timedelta(days=antes) <= f_mov <= f_comp + timedelta(days=despues)


def conciliar(movimientos, comprobantes, validacion, reglas, antes, despues):
    candidatos = [c for c in comprobantes
                  if not any(o["codigo"] == "DUPLICADO" for o in validacion[c["id"]]["observaciones"])
                  and c.get("total") and "Crédito" not in (c.get("clase") or "")]
    pagado = {c["id"]: 0.0 for c in candidatos}
    asignado = set()
    debitos = [m for m in movimientos if m["tipo"] == "debito"]

    def marcar(mov, comps, estado, confianza, comentario="", diferencia=0.0):
        cuits_banco = set(re.findall(r"\b\d{11}\b", solo_digitos_con_espacios(f"{mov['concepto']} {mov['referencia']}")))
        cuits_factura = {solo_digitos((c.get("emisor") or {}).get("cuit")) for c in comps}
        distintos = cuits_banco - cuits_factura
        if distintos and comps:
            comentario += (f" Ojo: el banco muestra el CUIT {', '.join(formatear_cuit(x) for x in sorted(distintos))} "
                           f"y la factura dice {', '.join(formatear_cuit(x) for x in sorted(cuits_factura))}.")
        mov.update({"estado": estado, "comprobantes": [c["id"] for c in comps], "confianza": confianza,
                    "diferencia": r2(diferencia), "comentario": comentario})
        for c in comps:
            asignado.add(c["id"])
        if comps:
            restante = mov["importe"]
            for c in comps:
                aplicado = min(c["total"] - pagado[c["id"]], restante) if c is not comps[-1] else restante
                pagado[c["id"]] = r2(pagado[c["id"]] + aplicado)
                restante -= aplicado

    # a) Mismo importe
    for mov in debitos:
        opciones = []
        for c in candidatos:
            if c["id"] in asignado or abs(c["total"] - mov["importe"]) > 0.01 or not en_ventana(c, mov, antes, despues):
                continue
            opciones.append((vinculo_proveedor(c, mov), c))
        if not opciones:
            continue
        opciones.sort(key=lambda o: -o[0])
        puntaje, comp = opciones[0]
        if puntaje >= 0.5:
            marcar(mov, [comp], "CONCILIADO", "alta", "Mismo importe y proveedor identificado en el concepto.")
        elif len(opciones) == 1:
            marcar(mov, [comp], "CONCILIADO", "media", "Mismo importe; el concepto del banco no menciona al proveedor.")

    # b) Un pago que cancela varias facturas del mismo proveedor
    for mov in debitos:
        if mov.get("estado"):
            continue
        del_proveedor = [c for c in candidatos if c["id"] not in asignado and vinculo_proveedor(c, mov) >= 0.5
                         and en_ventana(c, mov, antes, despues)]
        encontrado = None
        for n in range(2, min(5, len(del_proveedor) + 1)):
            for combo in combinations(del_proveedor, n):
                if abs(sum(c["total"] for c in combo) - mov["importe"]) <= 0.01:
                    encontrado = combo
                    break
            if encontrado:
                break
        if encontrado:
            marcar(mov, list(encontrado), "CONCILIADO", "alta",
                   f"Un solo pago cancela {len(encontrado)} facturas del mismo proveedor.")

    # c) Pagos con diferencia
    for mov in debitos:
        if mov.get("estado"):
            continue
        cercanos = []
        for c in candidatos:
            if c["id"] in asignado or vinculo_proveedor(c, mov) < 0.5 or not en_ventana(c, mov, antes, despues):
                continue
            diferencia = r2(mov["importe"] - c["total"])
            if abs(diferencia) <= max(0.05 * c["total"], 1.0):
                cercanos.append((abs(diferencia), diferencia, c))
        if not cercanos:
            continue
        _, diferencia, comp = min(cercanos, key=lambda x: x[0])
        if es_transposicion(mov["importe"], comp["total"]):
            pista = (f"Se pagó {fmt_pesos(mov['importe'])} y la factura es de {fmt_pesos(comp['total'])}: son los mismos "
                     f"dígitos con dos invertidos (la diferencia, {fmt_pesos(abs(diferencia))}, es divisible por 9). "
                     "Probable error de tipeo al cargar la transferencia.")
        elif round(abs(diferencia) * 100) % 9 == 0:
            pista = f"Diferencia de {fmt_pesos(abs(diferencia))}, divisible por 9: posible error de tipeo."
        elif diferencia < 0:
            pista = f"Se pagó {fmt_pesos(abs(diferencia))} menos que la factura (¿retención, descuento o pago parcial?)."
        else:
            pista = f"Se pagó {fmt_pesos(diferencia)} más que la factura (¿intereses, otro concepto o error?)."
        marcar(mov, [comp], "CONCILIADO_CON_DIFERENCIA", "media", pista, diferencia)

    # d) Reglas para movimientos sin comprobante
    for mov in movimientos:
        if mov.get("estado"):
            continue
        texto = normalizar(f"{mov['concepto']} {mov['referencia']}")
        regla = next((r for r in reglas if r.get("solo", mov["tipo"]) == mov["tipo"] and re.search(r["patron"], texto)), None)
        if regla:
            estado = "COBRO_A_IMPUTAR" if mov["tipo"] == "credito" else "GASTO_BANCARIO"
            mov.update({"estado": estado, "comprobantes": [], "confianza": "alta", "diferencia": 0.0,
                        "categoria": regla["categoria"], "cuenta": regla["cuenta"],
                        "comentario": "Sin factura: se respalda con el resumen bancario."
                        if estado == "GASTO_BANCARIO" else "Ingreso: cruzar con el Libro IVA Ventas / cobranzas."})
        elif mov["tipo"] == "debito":
            mov.update({"estado": "SIN_COMPROBANTE", "comprobantes": [], "confianza": "-", "diferencia": 0.0,
                        "comentario": "Pago sin factura ni regla que lo explique: pedir el comprobante."})
        else:
            mov.update({"estado": "COBRO_A_IMPUTAR", "comprobantes": [], "confianza": "baja", "diferencia": 0.0,
                        "categoria": "Crédito sin identificar", "cuenta": None,
                        "comentario": "Ingreso no identificado: consultar el origen."})

    pendientes = []
    for c in candidatos:
        saldo = r2(c["total"] - pagado[c["id"]])
        if saldo > 0.01 and validacion[c["id"]]["incluir_en_libro"]:
            pendientes.append({"id": c["id"], "comprobante": descripcion_comprobante(c),
                               "proveedor": (c.get("emisor") or {}).get("razon_social"),
                               "fecha": c.get("fecha"), "vencimiento": c.get("fecha_vto_pago"),
                               "total": c["total"], "pagado": pagado[c["id"]], "saldo": saldo})
    return movimientos, pendientes, pagado


def main():
    preparar_consola()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trabajo", default="trabajo")
    ap.add_argument("--extracto", required=True, help="Archivo del banco (CSV o Excel)")
    ap.add_argument("--reglas", default=str(REFERENCIAS / "reglas_banco.json"))
    ap.add_argument("--dias-antes", type=int, default=5, help="Días antes de la factura en que puede estar el pago")
    ap.add_argument("--dias-despues", type=int, default=75, help="Días después de la factura en que puede estar el pago")
    args = ap.parse_args()

    trabajo = Path(args.trabajo)
    comprobantes = cargar_json(trabajo / "comprobantes.json")["comprobantes"]
    validacion = cargar_json(trabajo / "validacion.json")
    reglas = cargar_json(args.reglas)["reglas"]

    titulo_paso("PASO 3 - Conciliación bancaria")
    movimientos, saldo_inicial, saldo_final = leer_extracto(args.extracto)
    debitos = r2(sum(m["importe"] for m in movimientos if m["tipo"] == "debito"))
    creditos = r2(sum(m["importe"] for m in movimientos if m["tipo"] == "credito"))
    print(f"Extracto: {Path(args.extracto).name}  |  movimientos: {len(movimientos)}  |  "
          f"débitos {fmt_pesos(debitos)}  |  créditos {fmt_pesos(creditos)}")

    control = None
    if saldo_inicial is not None and saldo_final is not None:
        calculado = r2(saldo_inicial + creditos - debitos)
        control = {"saldo_inicial": saldo_inicial, "creditos": creditos, "debitos": debitos,
                   "saldo_final_calculado": calculado, "saldo_final_informado": saldo_final,
                   "cierra": abs(calculado - saldo_final) < 0.01}
        print(f"Control de integridad: saldo inicial {fmt_pesos(saldo_inicial)} + créditos - débitos = "
              f"{fmt_pesos(calculado)} vs saldo final del banco {fmt_pesos(saldo_final)} -> "
              f"{'CIERRA' if control['cierra'] else 'NO CIERRA: puede faltar un movimiento'}")

    movimientos, pendientes, pagado = conciliar(movimientos, comprobantes, validacion["resultados"], reglas,
                                                args.dias_antes, args.dias_despues)
    guardar_json({"extracto": str(Path(args.extracto).resolve()), "control_saldos": control,
                  "movimientos": movimientos, "pendientes_de_pago": pendientes, "pagado_por_comprobante": pagado},
                 trabajo / "conciliacion.json")

    print()
    for m in movimientos:
        comps = ", ".join(m["comprobantes"]) or m.get("categoria", "")
        signo_txt = "-" if m["tipo"] == "debito" else "+"
        print(f"{m['id']} {fecha_ar(m['fecha'])} {signo_txt}{fmt_pesos(m['importe']):>16}  {m['estado']:<26} "
              f"{m['concepto'][:46]:<46} {comps}")
        if m["estado"] in ("CONCILIADO_CON_DIFERENCIA", "SIN_COMPROBANTE"):
            print(f"      -> {m['comentario']}  [{m['referencia']}]")

    estados = [m["estado"] for m in movimientos]
    print()
    for estado in ("CONCILIADO", "CONCILIADO_CON_DIFERENCIA", "GASTO_BANCARIO", "COBRO_A_IMPUTAR", "SIN_COMPROBANTE"):
        print(f"  {estado:<28} {estados.count(estado)}")
    if pendientes:
        print("\nComprobantes con saldo pendiente de pago:")
        for p in pendientes:
            print(f"  {p['id']} {p['comprobante']} {p['proveedor']}: saldo {fmt_pesos(p['saldo'])} "
                  f"(vence {fecha_ar(p['vencimiento']) or 's/d'})")
    print(f"\nResultado guardado en: {(trabajo / 'conciliacion.json').resolve()}")


if __name__ == "__main__":
    main()
