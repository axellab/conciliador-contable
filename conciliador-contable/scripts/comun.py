"""Funciones compartidas por los scripts del Conciliador Contable."""
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

CARPETA_SKILL = Path(__file__).resolve().parent.parent
REFERENCIAS = CARPETA_SKILL / "referencias"

# Códigos de comprobante de ARCA (ex AFIP) más frecuentes.
TIPOS_COMPROBANTE = {
    1: ("Factura", "A"), 2: ("Nota de Débito", "A"), 3: ("Nota de Crédito", "A"),
    6: ("Factura", "B"), 7: ("Nota de Débito", "B"), 8: ("Nota de Crédito", "B"),
    11: ("Factura", "C"), 12: ("Nota de Débito", "C"), 13: ("Nota de Crédito", "C"),
    51: ("Factura", "M"), 52: ("Nota de Débito", "M"), 53: ("Nota de Crédito", "M"),
    201: ("Factura de Crédito Electrónica MiPyME", "A"),
    206: ("Factura de Crédito Electrónica MiPyME", "B"),
    211: ("Factura de Crédito Electrónica MiPyME", "C"),
}

PALABRAS_VACIAS = {
    "SA", "SRL", "SAS", "SH", "SCA", "SACI", "SAIC", "SAU", "DE", "DEL", "LA", "LAS", "EL",
    "LOS", "Y", "E", "HNOS", "HERMANOS", "CIA", "COMPANIA", "ASOC", "ASOCIADOS", "LIC",
    "DR", "DRA", "CDOR", "CRA", "INC", "TRANSF", "TERCEROS",
}


def preparar_consola():
    """Evita errores de acentos en la consola de Windows."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except Exception:
            pass


def titulo_paso(texto):
    print()
    print("=" * 72)
    print(texto)
    print("=" * 72)


def solo_digitos(texto):
    return re.sub(r"\D", "", str(texto or ""))


def cuit_valido(cuit):
    """Valida el dígito verificador de un CUIT/CUIL (módulo 11)."""
    d = solo_digitos(cuit)
    if len(d) != 11:
        return False
    pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    resto = sum(int(a) * b for a, b in zip(d[:10], pesos)) % 11
    verificador = 11 - resto
    if verificador == 11:
        verificador = 0
    if verificador == 10:
        return False
    return verificador == int(d[10])


def formatear_cuit(cuit):
    d = solo_digitos(cuit)
    return f"{d[:2]}-{d[2:10]}-{d[10]}" if len(d) == 11 else (cuit or "")


def parsear_importe(texto):
    """Convierte '$ 1.234.567,89', '1234567.89' o '(1.234,00)' en float. None si no hay número."""
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    s = str(texto).strip()
    if not s:
        return None
    negativo = s.startswith("-") or (s.startswith("(") and s.endswith(")")) or s.endswith("-")
    s = re.sub(r"[^\d.,]", "", s)
    if not s or not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        miles = "." if decimal == "," else ","
        s = s.replace(miles, "").replace(decimal, ".")
    elif "," in s:
        partes = s.split(",")
        if len(partes) == 2 and len(partes[1]) in (1, 2):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        partes = s.split(".")
        if len(partes) > 2 or len(partes[1]) == 3:
            s = s.replace(".", "")
    valor = float(s)
    return -valor if negativo else valor


def parsear_fecha(texto):
    """Acepta dd/mm/aaaa, dd-mm-aaaa, dd/mm/aa y aaaa-mm-dd. Devuelve date o None."""
    if texto is None:
        return None
    if isinstance(texto, datetime):
        return texto.date()
    if isinstance(texto, date):
        return texto
    s = str(texto).strip()
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s[:10] if formato == "%Y-%m-%d" else s, formato).date()
        except ValueError:
            continue
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", s)
    if m:
        dia, mes, anio = (int(x) for x in m.groups())
        if anio < 100:
            anio += 2000
        try:
            return date(anio, mes, dia)
        except ValueError:
            return None
    return None


def fecha_iso(d):
    return d.isoformat() if d else None


def fecha_ar(valor):
    d = parsear_fecha(valor) if not isinstance(valor, date) else valor
    return d.strftime("%d/%m/%Y") if d else ""


def normalizar(texto):
    """Mayúsculas, sin acentos y con espacios simples, para comparar textos."""
    s = unicodedata.normalize("NFKD", str(texto or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w%]+", " ", s.upper())
    return re.sub(r"\s+", " ", s).strip()


def tokens_nombre(nombre):
    return [t for t in normalizar(nombre).split() if len(t) >= 4 and t not in PALABRAS_VACIAS]


def coincidencia_nombre(nombre, texto):
    """Proporción (0 a 1) de palabras significativas del nombre que aparecen en el texto."""
    tokens = tokens_nombre(nombre)
    if not tokens:
        return 0.0
    palabras = set(normalizar(texto).split())
    return sum(1 for t in tokens if t in palabras) / len(tokens)


def fmt_pesos(valor):
    if valor is None:
        return "-"
    signo = "-" if valor < 0 else ""
    entero, decimales = f"{abs(valor):,.2f}".split(".")
    return f"{signo}$ {entero.replace(',', '.')},{decimales}"


def r2(valor):
    return round((valor or 0.0) + 0.0, 2)


def es_nota_credito(comp):
    return "crédito" in (comp.get("clase") or "").lower() and "factura" not in (comp.get("clase") or "").lower()


def signo(comp):
    return -1 if es_nota_credito(comp) else 1


def descripcion_comprobante(comp):
    clase = comp.get("clase") or "Comprobante"
    abreviado = {"Factura": "FC", "Nota de Crédito": "NC", "Nota de Débito": "ND"}.get(clase, clase)
    return f"{abreviado} {comp.get('tipo') or '?'} {comp.get('punto_venta') or '?'}-{comp.get('numero') or '?'}"


def cargar_json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def guardar_json(datos, ruta):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def cargar_plan(ruta=None):
    return cargar_json(ruta or REFERENCIAS / "plan_de_cuentas.json")


def nombres_cuentas(plan):
    return {c["codigo"]: c["nombre"] for c in plan["cuentas"]}


def requerir(modulo, paquete=None):
    """Importa una librería o explica cómo instalarla."""
    import importlib
    try:
        return importlib.import_module(modulo)
    except ImportError:
        print(f"Falta la librería '{paquete or modulo}'. Instalala con:  pip install {paquete or modulo}")
        sys.exit(2)
