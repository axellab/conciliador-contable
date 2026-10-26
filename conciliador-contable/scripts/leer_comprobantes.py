"""Paso 1: inventario de la carpeta y lectura de comprobantes.

Recorre la carpeta (y subcarpetas), extrae el texto de cada PDF, reconoce los datos de
facturas con formato ARCA y sugiere una cuenta contable. Lo que no puede leer con
seguridad queda marcado con "revisar": true para que el agente lo complete.

Uso:
  python leer_comprobantes.py <carpeta_con_archivos> --trabajo <carpeta_de_trabajo>
"""
import argparse
import re
from collections import Counter
from pathlib import Path

from comun import (TIPOS_COMPROBANTE, cargar_plan, cuit_valido, descripcion_comprobante, fecha_iso, fmt_pesos,
                   formatear_cuit,
                   guardar_json, normalizar, parsear_fecha, parsear_importe, preparar_consola, r2,
                   solo_digitos, titulo_paso)

NUM = r"(-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}|-?\d{1,3}(?:,\d{3})*\.\d{2}|-?\d+\.\d{2}|-?\d+)"
CORTE = r"\s+(?=CUIT|Domicilio|Fecha|Ingresos|Condici[oó]n|Punto de Venta|Comp\.|COD\.|Apellido|Hasta)"
TASAS = [27.0, 21.0, 10.5, 5.0, 2.5, 0.0]
CAMPOS_OBLIGATORIOS = ["tipo", "punto_venta", "numero", "fecha", "emisor.cuit", "emisor.razon_social", "total"]


def extraer_texto_pdf(ruta):
    try:
        import pdfplumber
        with pdfplumber.open(ruta) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except ImportError:
        pass
    try:
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(ruta)).pages)
    except ImportError:
        raise SystemExit("Falta una librería para leer PDF. Instalá una con:  pip install pdfplumber")


def buscar(patron, texto, grupo=1):
    m = re.search(patron, texto, re.IGNORECASE)
    return m.group(grupo).strip() if m else None


def importe(etiqueta, texto):
    return parsear_importe(buscar(etiqueta + r"[ \t]*:?[ \t]*\$?[ \t]*" + NUM, texto))


def valor_hasta_corte(valor):
    return re.split(CORTE, valor)[0].strip(" -:") if valor else None


def detectar_clase(texto_n):
    if "NOTA DE CREDITO" in texto_n:
        return "Nota de Crédito"
    if "NOTA DE DEBITO" in texto_n:
        return "Nota de Débito"
    if "FACTURA" in texto_n:
        return "Factura"
    return None


def extraer_detalle(texto):
    lineas = texto.splitlines()
    inicio = next((i for i, l in enumerate(lineas) if re.search(r"Producto\s*/\s*Servicio|Descripci[oó]n", l)), None)
    if inicio is None:
        return []
    items = []
    for linea in lineas[inicio + 1:inicio + 16]:
        if re.match(r"\s*(Importe|Subtotal:|Otros tributos|IVA \d)", linea, re.IGNORECASE):
            break
        resto = re.sub(r"^\s*\d{1,4}\s+", "", linea)
        desc = re.split(r"\s+\d[\d.]*(?:,\d+)?\s+[A-Za-zÁÉÍÓÚáéíóú.]+\s+[\d.]+,\d{2}", resto)[0].strip()
        if len(desc) >= 3 and re.search(r"[A-Za-z]{3}", desc):
            items.append(desc)
    return items


def sugerir_cuenta(texto, plan):
    texto_n = normalizar(texto)
    mejor, puntaje_mejor = None, 0
    for cuenta in plan["cuentas"]:
        puntaje = 0
        for clave in cuenta.get("palabras_clave", []):
            puntaje += len(re.findall(r"\b" + re.escape(normalizar(clave)) + r"\w{0,3}\b", texto_n))
        if puntaje > puntaje_mejor:
            mejor, puntaje_mejor = cuenta, puntaje
    if not mejor:
        return None
    return {"codigo": mejor["codigo"], "nombre": mejor["nombre"], "coincidencias": puntaje_mejor}


def parsear_comprobante(texto, plan, cuit_empresa=None):
    texto_n = normalizar(texto)
    comp = {}

    codigo = buscar(r"COD\.?\s*(?:N[°º]?\s*)?(\d{1,3})\b", texto)
    clase, letra = TIPOS_COMPROBANTE.get(int(codigo), (None, None)) if codigo else (None, None)
    if not letra:
        letra = buscar(r"^\s*([ABCM])\s*$", texto)
    comp["codigo_arca"] = codigo.zfill(3) if codigo else None
    comp["clase"] = clase or detectar_clase(texto_n)
    comp["tipo"] = letra

    pv = buscar(r"Punto de Venta:?\s*(\d{1,5})", texto)
    nro = buscar(r"Comp(?:robante)?\.?\s*N(?:ro|°|º)\.?:?\s*(\d{1,8})", texto)
    if not (pv and nro):
        m = re.search(r"\b(\d{4,5})-(\d{8})\b", texto)
        if m:
            pv, nro = pv or m.group(1), nro or m.group(2)
    comp["punto_venta"] = pv.zfill(5) if pv else None
    comp["numero"] = nro.zfill(8) if nro else None

    comp["fecha"] = fecha_iso(parsear_fecha(buscar(r"Fecha de Emisi[oó]n:?\s*(\d{1,2}/\d{1,2}/\d{2,4})", texto)))
    comp["fecha_vto_pago"] = fecha_iso(parsear_fecha(buscar(r"Vto\.? para el pago:?\s*(\d{1,2}/\d{1,2}/\d{2,4})", texto)))
    desde = buscar(r"Desde:?\s*(\d{1,2}/\d{1,2}/\d{4})", texto)
    hasta = buscar(r"Hasta:?\s*(\d{1,2}/\d{1,2}/\d{4})", texto)
    comp["periodo_facturado"] = {"desde": fecha_iso(parsear_fecha(desde)), "hasta": fecha_iso(parsear_fecha(hasta))} if desde else None

    cuits = [solo_digitos(c) for c in re.findall(r"CUIT:?\s*(\d{2}-?\d{8}-?\d)", texto, re.IGNORECASE)]
    cuit_receptor = solo_digitos(buscar(r"CUIT:?\s*(\d{2}-?\d{8}-?\d)\s+Apellido", texto) or "")
    cuit_emisor = next((c for c in cuits if c != cuit_receptor), None)
    if not cuit_receptor:
        cuit_receptor = next((c for c in cuits if c != cuit_emisor), None)
    if cuit_empresa and cuit_emisor == cuit_empresa and cuit_receptor and cuit_receptor != cuit_empresa:
        cuit_emisor, cuit_receptor = cuit_receptor, cuit_emisor

    razon_emisor, razon_receptor = None, None
    for m in re.finditer(r"(Apellido y Nombre\s*/\s*)?Raz[oó]n Social:?[ \t]*([^\n]+)", texto, re.IGNORECASE):
        valor = valor_hasta_corte(m.group(2))
        if m.group(1) and not razon_receptor:
            razon_receptor = valor
        elif not m.group(1) and not razon_emisor:
            razon_emisor = valor
    condiciones = [valor_hasta_corte(v) for v in re.findall(r"Condici[oó]n frente al IVA:?[ \t]*([^\n]+)", texto, re.IGNORECASE)]

    comp["emisor"] = {"cuit": cuit_emisor, "razon_social": razon_emisor,
                      "condicion_iva": condiciones[0] if condiciones else None}
    comp["receptor"] = {"cuit": cuit_receptor, "razon_social": razon_receptor,
                        "condicion_iva": condiciones[1] if len(condiciones) > 1 else None}

    neto = importe(r"Importe Neto Gravado", texto)
    subtotal = importe(r"(?<!Imp\. )Subtotal", texto)
    comp["neto_gravado"] = neto
    comp["no_gravado"] = importe(r"Importe Neto No Gravado", texto) or 0.0
    comp["exento"] = importe(r"Importe Exento", texto) or 0.0
    ivas = {}
    for tasa_txt, monto in re.findall(r"IVA[ \t]*(27|21|10[.,]5|5|2[.,]5|0)[ \t]*%[ \t]*:?[ \t]*\$?[ \t]*" + NUM, texto, re.IGNORECASE):
        tasa = float(tasa_txt.replace(",", "."))
        valor = parsear_importe(monto)
        if valor:
            ivas[tasa] = valor
    alicuotas = []
    if comp["tipo"] == "A" or (comp["tipo"] in (None, "M") and ivas):
        if len(ivas) == 1 and neto is not None:
            (tasa, iva), = ivas.items()
            alicuotas.append({"tasa": tasa, "neto": r2(neto), "iva": r2(iva)})
        else:
            for tasa in TASAS:
                if tasa in ivas:
                    alicuotas.append({"tasa": tasa, "neto": r2(ivas[tasa] / (tasa / 100)) if tasa else None, "iva": r2(ivas[tasa])})
    comp["alicuotas"] = alicuotas
    comp["iva_total"] = r2(sum(a["iva"] for a in alicuotas))
    comp["subtotal"] = subtotal if comp["tipo"] in ("B", "C") else None
    comp["otros_tributos"] = importe(r"Importe Otros Tributos", texto) or 0.0
    comp["total"] = importe(r"Importe Total", texto)
    comp["iva_contenido"] = importe(r"IVA Contenido", texto)
    comp["cae"] = buscar(r"C\.?A\.?E\.?\s*N?[°º]?:?\s*(\d{14})", texto)
    comp["vto_cae"] = fecha_iso(parsear_fecha(buscar(r"Vto\.? de CAE:?\s*(\d{1,2}/\d{1,2}/\d{4})", texto)))

    detalle = extraer_detalle(texto)
    comp["detalle"] = detalle
    comp["cuenta_sugerida"] = sugerir_cuenta(f"{razon_emisor or ''}\n" + "\n".join(detalle) + "\n" + texto, plan)

    faltantes = []
    for campo in CAMPOS_OBLIGATORIOS:
        valor = comp
        for parte in campo.split("."):
            valor = (valor or {}).get(parte)
        if valor in (None, ""):
            faltantes.append(campo)
    if comp["tipo"] == "A" and not alicuotas:
        faltantes.append("alicuotas")
    motivos = []
    if faltantes:
        motivos.append("faltan datos: " + ", ".join(faltantes))
    if comp["tipo"] == "A" and neto is not None and alicuotas and abs(sum(a["neto"] or 0 for a in alicuotas) - neto) > 1:
        motivos.append("el neto por alícuota no coincide con el neto gravado: revisar el detalle")
    if not comp["cuenta_sugerida"]:
        motivos.append("no se pudo sugerir una cuenta")
    comp["campos_faltantes"] = faltantes
    comp["revisar"] = bool(motivos)
    comp["motivos_revision"] = motivos
    return comp


def clasificar_tabla(ruta):
    """Indica si un CSV/Excel parece un extracto bancario."""
    try:
        if ruta.suffix.lower() == ".csv":
            muestra = ruta.read_text(encoding="utf-8-sig", errors="ignore")[:4000]
        else:
            import openpyxl
            libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
            hoja = libro.worksheets[0]
            muestra = " ".join(str(c) for fila in hoja.iter_rows(max_row=25, values_only=True) for c in fila if c)
    except Exception:
        return "planilla"
    n = normalizar(muestra)
    return "extracto_bancario" if ("SALDO" in n and ("DEBITO" in n or "CREDITO" in n or "IMPORTE" in n)) else "planilla"


def datos_desde_texto(texto):
    cuit = buscar(r"CUIT:?\s*(\d{2}-?\d{8}-?\d)", texto)
    periodo = re.search(r"\((\d{2})/(\d{4})\)|per[ií]odo[^\n]*?(\d{2})/(\d{4})", texto, re.IGNORECASE)
    razon = buscar(r"Raz[oó]n social:?[ \t]*([^\n]+)", texto)
    condicion = buscar(r"Condici[oó]n frente al IVA:?[ \t]*([^\n]+)", texto)
    resultado = {}
    if cuit:
        resultado["cuit"] = solo_digitos(cuit)
    if razon:
        resultado["razon_social"] = razon
    if condicion:
        resultado["condicion_iva"] = condicion
    if periodo:
        mes, anio = (periodo.group(1), periodo.group(2)) if periodo.group(1) else (periodo.group(3), periodo.group(4))
        resultado["periodo"] = f"{anio}-{mes}"
    return resultado


def main():
    preparar_consola()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("carpeta", help="Carpeta con las facturas, el extracto y demás archivos del cliente")
    ap.add_argument("--trabajo", default="trabajo", help="Carpeta donde guardar los resultados intermedios")
    ap.add_argument("--plan", help="Plan de cuentas JSON (por defecto el de la skill)")
    ap.add_argument("--cuit-empresa", help="CUIT de la empresa, si ya se conoce")
    args = ap.parse_args()

    carpeta = Path(args.carpeta)
    trabajo = Path(args.trabajo)
    (trabajo / "textos").mkdir(parents=True, exist_ok=True)
    plan = cargar_plan(args.plan)
    cuit_empresa = solo_digitos(args.cuit_empresa) if args.cuit_empresa else None

    titulo_paso("PASO 1 - Inventario y lectura de comprobantes")
    archivos = sorted(p for p in carpeta.rglob("*") if p.is_file() and not p.name.startswith((".", "~$")))
    print(f"Carpeta: {carpeta.resolve()}")
    print(f"Archivos encontrados: {len(archivos)}\n")

    comprobantes, otros, extractos, datos_empresa = [], [], [], {}
    for ruta in archivos:
        ext = ruta.suffix.lower()
        relativo = str(ruta.relative_to(carpeta))
        if ext == ".pdf":
            texto = extraer_texto_pdf(ruta)
            texto_n = normalizar(texto)
            if len(texto_n) < 40:
                otros.append({"archivo": relativo, "tipo": "pdf_sin_texto",
                              "detalle": "PDF escaneado o imagen: leerlo visualmente y cargar los datos a mano"})
                continue
            if re.search(r"\bREMITO\b", texto_n[:300]) and "IMPORTE TOTAL" not in texto_n:
                otros.append({"archivo": relativo, "tipo": "remito", "texto": texto,
                              "detalle": "Remito: documenta una entrega, no tiene valor fiscal para el Libro IVA"})
                continue
            comp = parsear_comprobante(texto, plan, cuit_empresa)
            if not comp["clase"] and comp["total"] is None:
                otros.append({"archivo": relativo, "tipo": "pdf_no_reconocido", "texto": texto,
                              "detalle": "No parece un comprobante fiscal: revisar"})
                continue
            comp["archivo"] = relativo
            comp["_texto"] = texto
            comprobantes.append(comp)
        elif ext in (".csv", ".xlsx", ".xlsm", ".xls"):
            tipo = clasificar_tabla(ruta) if ext != ".xls" else "planilla"
            (extractos if tipo == "extracto_bancario" else otros).append({"archivo": relativo, "tipo": tipo})
        elif ext in (".txt", ".md"):
            texto = ruta.read_text(encoding="utf-8", errors="ignore")
            datos = datos_desde_texto(texto)
            if datos:
                datos_empresa.update({k: v for k, v in datos.items() if k not in datos_empresa})
            otros.append({"archivo": relativo, "tipo": "texto", "detalle": texto[:300]})
        elif ext in (".jpg", ".jpeg", ".png", ".heic", ".webp"):
            otros.append({"archivo": relativo, "tipo": "imagen",
                          "detalle": "Imagen (foto de ticket o factura): leerla visualmente y cargar los datos a mano"})
        else:
            otros.append({"archivo": relativo, "tipo": "desconocido"})

    comprobantes.sort(key=lambda c: (c["fecha"] or "9999", c["archivo"]))
    for i, comp in enumerate(comprobantes, 1):
        comp["id"] = f"C{i:02d}"
        ruta_texto = trabajo / "textos" / f"{comp['id']}.txt"
        ruta_texto.write_text(comp.pop("_texto"), encoding="utf-8")
        comp["texto_extraido"] = str(ruta_texto)
    for j, doc in enumerate(otros, 1):
        doc["id"] = f"D{j:02d}"
        if "texto" in doc:
            ruta_texto = trabajo / "textos" / f"{doc['id']}.txt"
            ruta_texto.write_text(doc.pop("texto"), encoding="utf-8")
            doc["texto_extraido"] = str(ruta_texto)

    receptores = Counter(c["receptor"]["cuit"] for c in comprobantes if c["receptor"]["cuit"])
    meses = Counter((c["fecha"] or "")[:7] for c in comprobantes if c["fecha"])
    inferido = {}
    if receptores:
        cuit_frecuente = receptores.most_common(1)[0][0]
        nombre = next((c["receptor"]["razon_social"] for c in comprobantes if c["receptor"]["cuit"] == cuit_frecuente), None)
        inferido = {"cuit": cuit_frecuente, "razon_social": nombre, "periodo": meses.most_common(1)[0][0] if meses else None}

    ordenados = [{k: c[k] for k in ("id", "archivo", "clase", "tipo", "codigo_arca", "punto_venta", "numero", "fecha",
                                    "fecha_vto_pago", "periodo_facturado", "emisor", "receptor", "neto_gravado",
                                    "no_gravado", "exento", "alicuotas", "iva_total", "subtotal", "otros_tributos",
                                    "total", "iva_contenido", "cae", "vto_cae", "detalle", "cuenta_sugerida",
                                    "revisar", "motivos_revision", "campos_faltantes", "texto_extraido")}
                 for c in comprobantes]
    salida = {
        "carpeta": str(carpeta.resolve()),
        "datos_empresa_en_archivos": datos_empresa,
        "datos_empresa_inferidos": inferido,
        "comprobantes": ordenados,
        "extractos_bancarios": extractos,
        "otros_documentos": otros,
    }
    guardar_json(salida, trabajo / "comprobantes.json")

    print(f"{'ID':<4} {'Archivo':<38} {'Comprobante':<20} {'Proveedor':<34} {'Fecha':<10} {'Total':>16}  Revisar")
    print("-" * 138)
    for c in ordenados:
        desc = descripcion_comprobante(c)
        print(f"{c['id']:<4} {c['archivo'][:38]:<38} {desc:<20} {(c['emisor']['razon_social'] or '?')[:34]:<34} "
              f"{c['fecha'] or '?':<10} {fmt_pesos(c['total']):>16}  {'SI' if c['revisar'] else ''}")
    print()
    for d in otros:
        print(f"{d['id']:<4} {d['archivo'][:60]:<60} -> {d['tipo']}: {(d.get('detalle') or '').splitlines()[0][:70] if d.get('detalle') else ''}")
    for e in extractos:
        print(f"     {e['archivo']:<60} -> extracto bancario")

    print()
    print(f"Comprobantes leídos: {len(ordenados)}  |  a revisar: {sum(c['revisar'] for c in ordenados)}  |  "
          f"otros documentos: {len(otros)}  |  extractos bancarios: {len(extractos)}")
    if datos_empresa:
        print(f"Datos de la empresa encontrados en archivos: {datos_empresa}")
    if inferido:
        print(f"Inferido de los comprobantes: receptor más frecuente {formatear_cuit(inferido['cuit'])} "
              f"({inferido['razon_social']}), período más frecuente {inferido['periodo']}")
        if not cuit_valido(inferido["cuit"]):
            print("ATENCIÓN: el CUIT inferido de la empresa no pasa la validación.")
    for c in ordenados:
        if c["revisar"]:
            print(f"  {c['id']} ({c['archivo']}): " + "; ".join(c["motivos_revision"]))
    print(f"\nResultado guardado en: {(trabajo / 'comprobantes.json').resolve()}")


if __name__ == "__main__":
    main()
