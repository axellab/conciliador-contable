"""Paso 2: controles sobre los comprobantes.

Controla con reglas fijas (no con "intuición"): CUIT, destinatario, duplicados, período,
aritmética, IVA por alícuota, tipo de comprobante y CAE. Cada comprobante queda con un
estado (OK / OBSERVADO / EXCLUIDO) y la lista de observaciones con la acción sugerida.

Uso:
  python validar.py --trabajo <carpeta_de_trabajo> --cuit-empresa 30-71583246-8 --periodo 2026-09
                    [--empresa "LA ESPIGA DORADA SRL"] [--condicion RI]
"""
import argparse
from pathlib import Path

from comun import (cargar_json, cuit_valido, descripcion_comprobante, fecha_ar, fmt_pesos, formatear_cuit,
                   guardar_json, normalizar, parsear_fecha, preparar_consola, r2, solo_digitos, titulo_paso)

SEVERIDAD_ORDEN = {"ALTA": 0, "MEDIA": 1, "INFO": 2}


def tolerancia(base):
    return max(1.0, abs(base or 0) * 0.0005)


def validar(comprobantes, cuit_empresa, periodo, condicion):
    resultados = {}
    vistos = {}
    for c in comprobantes:
        obs = []
        excluir = False
        computa_cf = c.get("tipo") == "A" or (c.get("tipo") == "M" and bool(c.get("alicuotas")))
        emisor = c.get("emisor") or {}
        receptor = c.get("receptor") or {}
        ref = f"{descripcion_comprobante(c)} - {emisor.get('razon_social') or 'proveedor sin nombre'}"

        def agregar(codigo, severidad, detalle, accion):
            obs.append({"codigo": codigo, "severidad": severidad, "detalle": detalle, "accion": accion})

        # 1. Duplicados
        clave = (solo_digitos(emisor.get("cuit")), c.get("tipo"), c.get("punto_venta"), c.get("numero"))
        if all(clave) and clave in vistos:
            original = vistos[clave]
            agregar("DUPLICADO", "ALTA",
                    f"Es el mismo comprobante que {original['id']} ({original['archivo']}). Se recibió dos veces.",
                    "No registrarlo de nuevo. Se excluye del Libro IVA y de la conciliación.")
            excluir = True
        elif all(clave):
            vistos[clave] = c

        # 2. Destinatario
        cuit_receptor = solo_digitos(receptor.get("cuit"))
        if cuit_empresa and cuit_receptor and cuit_receptor != cuit_empresa:
            agregar("RECEPTOR_DISTINTO", "ALTA",
                    f"La factura está emitida a {receptor.get('razon_social') or 'otro receptor'} "
                    f"(CUIT {formatear_cuit(cuit_receptor)}), no a la empresa (CUIT {formatear_cuit(cuit_empresa)}).",
                    "No computar el crédito fiscal. Pedir al proveedor que la anule con nota de crédito y la "
                    "vuelva a emitir a nombre de la empresa.")
            excluir = True
            computa_cf = False

        # 3. CUIT del emisor
        cuit_emisor = solo_digitos(emisor.get("cuit"))
        if cuit_emisor and not cuit_valido(cuit_emisor):
            agregar("CUIT_INVALIDO", "ALTA",
                    f"El CUIT del proveedor ({formatear_cuit(cuit_emisor)}) no pasa la validación del dígito "
                    "verificador: puede ser un error de tipeo o un comprobante apócrifo.",
                    "Verificar el CUIT en la constancia de inscripción de ARCA y constatar el comprobante "
                    "antes de registrarlo y computar el crédito fiscal.")
        elif not cuit_emisor:
            agregar("SIN_CUIT", "MEDIA", "No se pudo leer el CUIT del proveedor.", "Completar el CUIT a mano.")

        # 4. Período
        fecha = parsear_fecha(c.get("fecha"))
        if periodo and fecha and fecha.strftime("%Y-%m") != periodo:
            agregar("FUERA_DE_PERIODO", "MEDIA",
                    f"Fecha de emisión {fecha_ar(fecha)}: corresponde al período {fecha.strftime('%m/%Y')}, "
                    f"no al {periodo[5:]}/{periodo[:4]} que se está procesando.",
                    f"Verificar si ya se registró en {fecha.strftime('%m/%Y')} para no duplicar el crédito fiscal. "
                    "Si no se registró, puede incluirse en este período.")
            excluir = True

        # 5. Aritmética
        total = c.get("total")
        if total is not None:
            if c.get("tipo") in ("B", "C"):
                base = (c.get("subtotal") if c.get("subtotal") is not None else total - (c.get("otros_tributos") or 0))
                suma = base + (c.get("otros_tributos") or 0)
            else:
                suma = ((c.get("neto_gravado") or 0) + (c.get("no_gravado") or 0) + (c.get("exento") or 0)
                        + (c.get("iva_total") or 0) + (c.get("otros_tributos") or 0))
            if abs(suma - total) > tolerancia(total):
                agregar("NO_CIERRA", "MEDIA",
                        f"Los importes no cierran: la suma de los conceptos da {fmt_pesos(suma)} y el total es "
                        f"{fmt_pesos(total)} (diferencia {fmt_pesos(total - suma)}).",
                        "Revisar la lectura del comprobante; si los datos son correctos, pedir al proveedor que lo corrija.")
        else:
            agregar("SIN_TOTAL", "MEDIA", "No se pudo leer el importe total.", "Completar el total a mano.")

        # 6. IVA por alícuota
        for a in c.get("alicuotas") or []:
            if not a.get("tasa") or a.get("neto") is None:
                continue
            esperado = r2(a["neto"] * a["tasa"] / 100)
            if abs(esperado - (a.get("iva") or 0)) > tolerancia(esperado):
                diferencia = r2((a.get("iva") or 0) - esperado)
                equivale = (f" (equivale a una alícuota de {(a.get('iva') or 0) / a['neto'] * 100:.2f}%)"
                            if a["neto"] else "")
                agregar("IVA_MAL_CALCULADO", "MEDIA",
                        f"IVA {a['tasa']:g}% facturado {fmt_pesos(a.get('iva'))}, pero el {a['tasa']:g}% de "
                        f"{fmt_pesos(a['neto'])} es {fmt_pesos(esperado)}. Diferencia {fmt_pesos(diferencia)}{equivale}.",
                        f"Computar solo el IVA correcto ({fmt_pesos(esperado)}) y pedir al proveedor una nota de "
                        f"crédito por {fmt_pesos(abs(diferencia))}.")

        # 7. Tipo de comprobante según la condición frente al IVA
        cond_emisor = normalizar(emisor.get("condicion_iva"))
        if condicion == "RI" and c.get("tipo") == "B" and "RESPONSABLE INSCRIPTO" in cond_emisor:
            contenido = c.get("iva_contenido")
            monto = f" ({fmt_pesos(contenido)} de IVA contenido)" if contenido else ""
            agregar("FACTURA_B_A_RI", "MEDIA",
                    f"Un proveedor Responsable Inscripto emitió Factura B a una empresa Responsable Inscripta: "
                    f"el IVA no se puede computar como crédito fiscal{monto}.",
                    "Pedir al proveedor que anule la Factura B y emita Factura A. Mientras tanto se registra "
                    "por el total como gasto, sin crédito fiscal.")
        if c.get("tipo") in ("B", "C"):
            computa_cf = False

        # 8. CAE
        if not c.get("cae"):
            agregar("SIN_CAE", "MEDIA", "No se encontró el CAE del comprobante.",
                    "Constatar el comprobante en el servicio de ARCA antes de registrarlo.")

        # 9. Datos incompletos (lo que el agente no pudo completar)
        if c.get("campos_faltantes"):
            agregar("DATOS_INCOMPLETOS", "MEDIA", "Faltan datos: " + ", ".join(c["campos_faltantes"]),
                    "Completar los datos mirando el comprobante original.")

        # Decisión del profesional: "incluir": true/false en comprobantes.json pisa la exclusión automática.
        # Las observaciones se mantienen para dejar constancia. Un duplicado nunca se incluye.
        if c.get("incluir") is not None and not any(o["codigo"] == "DUPLICADO" for o in obs):
            excluir = not c["incluir"]
            motivo = f": {c['motivo_decision']}" if c.get("motivo_decision") else ""
            agregar("DECISION_PROFESIONAL", "INFO",
                    f"{'Incluido' if c['incluir'] else 'Excluido'} por decisión del profesional{motivo}.", "Ninguna.")
            computa_cf = (c["incluir"] and c.get("tipo") in ("A", "M") and bool(c.get("alicuotas"))
                          and not any(o["codigo"] == "RECEPTOR_DISTINTO" for o in obs))

        if excluir:
            estado = "EXCLUIDO"
        elif any(o["severidad"] in ("ALTA", "MEDIA") for o in obs):
            estado = "OBSERVADO"
        else:
            estado = "OK"
        obs.sort(key=lambda o: SEVERIDAD_ORDEN[o["severidad"]])
        resultados[c["id"]] = {
            "id": c["id"], "referencia": ref, "estado": estado,
            "incluir_en_libro": not excluir, "computa_cf": computa_cf and not excluir,
            "observaciones": obs,
        }
    return resultados


def main():
    preparar_consola()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trabajo", default="trabajo")
    ap.add_argument("--cuit-empresa", required=True)
    ap.add_argument("--periodo", required=True, help="Período a procesar en formato AAAA-MM, por ejemplo 2026-09")
    ap.add_argument("--empresa", help="Razón social de la empresa")
    ap.add_argument("--condicion", default="RI", choices=["RI", "MT", "EX"],
                    help="Condición de la empresa frente al IVA: RI (Responsable Inscripto), MT (Monotributo), EX (Exento)")
    args = ap.parse_args()

    trabajo = Path(args.trabajo)
    datos = cargar_json(trabajo / "comprobantes.json")
    comprobantes = datos["comprobantes"]
    cuit_empresa = solo_digitos(args.cuit_empresa)

    titulo_paso("PASO 2 - Controles sobre los comprobantes")
    print(f"Empresa: {args.empresa or '(sin nombre)'}  CUIT {formatear_cuit(cuit_empresa)}  "
          f"Condición: {args.condicion}  Período: {args.periodo}")
    if not cuit_valido(cuit_empresa):
        print("ATENCIÓN: el CUIT de la empresa no pasa la validación del dígito verificador.")

    resultados = validar(comprobantes, cuit_empresa, args.periodo, args.condicion)
    guardar_json({
        "empresa": {"razon_social": args.empresa, "cuit": cuit_empresa, "condicion": args.condicion},
        "periodo": args.periodo,
        "resultados": resultados,
    }, trabajo / "validacion.json")

    por_id = {c["id"]: c for c in comprobantes}
    print()
    for r in resultados.values():
        c = por_id[r["id"]]
        print(f"{r['id']}  {r['estado']:<9}  {r['referencia'][:70]:<70} {fmt_pesos(c.get('total')):>16}")
        for o in r["observaciones"]:
            print(f"       [{o['severidad']}] {o['codigo']}: {o['detalle']}")

    estados = [r["estado"] for r in resultados.values()]
    cf = sum(por_id[i].get("iva_total") or 0 for i, r in resultados.items() if r["computa_cf"])
    print()
    print(f"OK: {estados.count('OK')}  |  Observados: {estados.count('OBSERVADO')}  |  Excluidos: {estados.count('EXCLUIDO')}")
    print(f"IVA crédito fiscal de los comprobantes incluidos (antes de ajustes): {fmt_pesos(cf)}")
    print(f"\nResultado guardado en: {(trabajo / 'validacion.json').resolve()}")


if __name__ == "__main__":
    main()
