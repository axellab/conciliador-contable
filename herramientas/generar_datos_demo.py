"""Genera el set de datos FICTICIOS para la demo: facturas PDF con formato tipo ARCA,
un remito, el extracto bancario y los datos de la empresa.

Uso:  python herramientas/generar_datos_demo.py

Errores plantados a propósito (para que el agente los encuentre):
  1. Factura duplicada (Fletes Rápidos del Oeste, reenviada con otro nombre de archivo).
  2. IVA mal calculado (Envases y Packaging Norte: 22% en lugar de 21%).
  3. CUIT del proveedor con dígito verificador inválido (Ferreyra Mantenimiento Industrial).
  4. Factura emitida a otro CUIT (Gráfica Rivadavia, a nombre de "La Espiga Dorada SA").
  5. Factura de agosto mezclada en la carpeta de septiembre (Insumos Gastronómicos 0002-00004298).
  6. Factura B recibida por un Responsable Inscripto (Limpieza Total SRL).
  7. Transferencia sin comprobante (Martínez Roberto Carlos, "ALQ SEPT").
  8. Pago con dígitos invertidos (Insumos: factura $147.520, transferencia $147.250).
Además: un pago que cancela dos facturas (Molino), un remito, gastos e impuestos bancarios
sin registrar y una factura pendiente de pago (Telecomunicaciones Australes).

Todos los nombres, CUIT, CAE y domicilios son inventados.
"""
import csv
import sys
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "conciliador-contable" / "scripts"))
from comun import fmt_pesos  # noqa: E402

SALIDA = RAIZ / "datos_demo" / "La_Espiga_Dorada_2026-09"
AVISO = "DOCUMENTO FICTICIO GENERADO PARA DEMOSTRACIÓN - SIN VALIDEZ FISCAL"


def cuit(base10, invalido=False):
    pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    v = 11 - sum(int(a) * b for a, b in zip(base10, pesos)) % 11
    v = 0 if v == 11 else v
    assert v != 10, f"Elegí otra base para {base10}"
    if invalido:
        v = (v + 3) % 10
    return f"{base10}{v}"


def num(x):
    return fmt_pesos(x).replace("$ ", "")


def fdate(d):
    return d.strftime("%d/%m/%Y")


EMPRESA = {
    "razon_social": "LA ESPIGA DORADA SRL",
    "cuit": cuit("3071583246"),
    "condicion": "IVA Responsable Inscripto",
    "domicilio": "Av. Rivadavia 14.520 - Ramos Mejía, Buenos Aires",
}
OTRA_EMPRESA = dict(EMPRESA, razon_social="LA ESPIGA DORADA SA", cuit=cuit("3071583264"),
                    domicilio="Av. de Mayo 1.180 - Ramos Mejía, Buenos Aires")

RI = "IVA Responsable Inscripto"
MONO = "Responsable Monotributo"

PROVEEDORES = {
    "molino": {"razon_social": "MOLINO HARINERO SAN MARTIN SA", "cuit": cuit("3070845123"), "condicion": RI,
               "domicilio": "Ruta 7 Km 64 - Luján, Buenos Aires", "iibb": "901-845123-4", "inicio": "12/03/1998"},
    "insumos": {"razon_social": "INSUMOS GASTRONOMICOS DEL CENTRO SRL", "cuit": cuit("3071122334"), "condicion": RI,
                "domicilio": "Av. Gaona 3.450 - CABA", "iibb": "901-122334-1", "inicio": "01/06/2010"},
    "energia": {"razon_social": "ENERGIA DEL PLATA SA", "cuit": cuit("3050001234"), "condicion": RI,
                "domicilio": "Av. del Libertador 6.800 - CABA", "iibb": "901-500012-3", "inicio": "01/09/1992"},
    "telecom": {"razon_social": "TELECOMUNICACIONES AUSTRALES SA", "cuit": cuit("3068765431"), "condicion": RI,
                "domicilio": "Av. Corrientes 1.250 - CABA", "iibb": "901-687654-3", "inicio": "15/02/1995"},
    "fletes": {"razon_social": "FLETES RAPIDOS DEL OESTE SRL", "cuit": cuit("3071456789"), "condicion": RI,
               "domicilio": "Juan B. Justo 980 - Haedo, Buenos Aires", "iibb": "901-456789-2", "inicio": "20/08/2014"},
    "gomez": {"razon_social": "GOMEZ MARIA LAURA", "cuit": cuit("2728456789"), "condicion": MONO,
              "domicilio": "Belgrano 455 - Morón, Buenos Aires", "iibb": "Exento - Monotributo", "inicio": "01/04/2012"},
    "limpieza": {"razon_social": "LIMPIEZA TOTAL SRL", "cuit": cuit("3071890123"), "condicion": RI,
                 "domicilio": "Av. Rivadavia 17.300 - Haedo, Buenos Aires", "iibb": "901-890123-0", "inicio": "05/05/2016"},
    "envases": {"razon_social": "ENVASES Y PACKAGING NORTE SA", "cuit": cuit("3070987654"), "condicion": RI,
                "domicilio": "Panamericana Km 38 - Garín, Buenos Aires", "iibb": "901-987654-8", "inicio": "10/10/2001"},
    "ferreyra": {"razon_social": "FERREYRA MANTENIMIENTO INDUSTRIAL SRL", "cuit": cuit("3071234560", invalido=True),
                 "condicion": RI, "domicilio": "Pueyrredón 2.210 - Castelar, Buenos Aires",
                 "iibb": "901-234560-7", "inicio": "14/07/2017"},
    "grafica": {"razon_social": "GRAFICA RIVADAVIA SRL", "cuit": cuit("3071345678"), "condicion": RI,
                "domicilio": "Av. Rivadavia 13.900 - Ramos Mejía, Buenos Aires", "iibb": "901-345678-5", "inicio": "02/02/2015"},
}
CUIT_MARTINEZ = cuit("2017654321")
CUIT_CAFE = cuit("3071999888")


def item(desc, cant, unidad, precio, tasa):
    return {"desc": desc, "cant": cant, "unidad": unidad, "precio": precio, "tasa": tasa}


FACTURAS = [
    # archivo, proveedor, letra, cod, pv, nro, fecha, vto, items, otros tributos, ajustes
    dict(archivo="FC A 0005-00012841 Molino.pdf", prov="molino", letra="A", cod="01", pv="00005", nro="00012841",
         fecha=date(2026, 9, 3), vto=date(2026, 9, 30),
         items=[item("Harina de trigo 000 - bolsa 25 kg", 40, "unidades", 24500, 10.5)]),
    dict(archivo="factura molino 2.pdf", prov="molino", letra="A", cod="01", pv="00005", nro="00012967",
         fecha=date(2026, 9, 17), vto=date(2026, 10, 15),
         items=[item("Harina de trigo 0000 - bolsa 25 kg", 30, "unidades", 26800, 10.5)]),
    dict(archivo="Insumos 4410.pdf", prov="insumos", letra="A", cod="01", pv="00002", nro="00004410",
         fecha=date(2026, 9, 8), vto=date(2026, 9, 18),
         items=[item("Levadura fresca prensada - kg", 10, "kilogramos", 4800, 21),
                item("Margarina para hojaldre - kg", 20, "kilogramos", 2600, 21),
                item("Harina leudante - bolsa 25 kg", 1, "unidades", 24000, 10.5)]),
    dict(archivo="Insumos 4298.pdf", prov="insumos", letra="A", cod="01", pv="00002", nro="00004298",
         fecha=date(2026, 8, 27), vto=date(2026, 9, 7),
         items=[item("Azúcar refinada - bolsa 50 kg", 2, "unidades", 57500, 21)]),
    dict(archivo="Energia del Plata - factura luz.pdf", prov="energia", letra="A", cod="01", pv="00045",
         nro="01234567", fecha=date(2026, 9, 5), vto=date(2026, 9, 22),
         desde=date(2026, 8, 1), hasta=date(2026, 8, 31),
         items=[item("Consumo de energía eléctrica T2 - 1.750 kWh (cliente 0045-778812)", 1, "unidades", 210000, 27)],
         otros=[("Percepción Ingresos Brutos Bs. As.", 3.0, 6300)]),
    dict(archivo="Australes internet sept.pdf", prov="telecom", letra="A", cod="01", pv="00012", nro="00876543",
         fecha=date(2026, 9, 10), vto=date(2026, 10, 10), desde=date(2026, 9, 1), hasta=date(2026, 9, 30),
         items=[item("Abono internet fibra óptica 1 Gb + telefonía fija", 1, "unidades", 48000, 27)]),
    dict(archivo="Fletes Oeste 231.pdf", prov="fletes", letra="A", cod="01", pv="00001", nro="00000231",
         fecha=date(2026, 9, 12), vto=date(2026, 9, 22),
         items=[item("Servicio de flete y distribución a sucursales", 37, "viajes", 5000, 21)]),
    dict(archivo="Fletes_Oeste_reenvio.pdf", prov="fletes", letra="A", cod="01", pv="00001", nro="00000231",
         fecha=date(2026, 9, 12), vto=date(2026, 9, 22),
         items=[item("Servicio de flete y distribución a sucursales", 37, "viajes", 5000, 21)]),
    dict(archivo="Honorarios Gomez.pdf", prov="gomez", letra="C", cod="011", pv="00002", nro="00000187",
         fecha=date(2026, 9, 1), vto=date(2026, 9, 10),
         items=[item("Honorarios por asesoramiento contable e impositivo - agosto 2026", 1, "unidades", 350000, None)]),
    dict(archivo="Limpieza Total.pdf", prov="limpieza", letra="B", cod="06", pv="00003", nro="00002156",
         fecha=date(2026, 9, 11), vto=date(2026, 9, 21),
         items=[item("Detergente industrial bidón 5 L", 12, "unidades", 3630, 21),
                item("Lavandina concentrada bidón 5 L", 20, "unidades", 2178, 21),
                item("Desinfectante de superficies 5 L", 4, "unidades", 2420, 21)]),
    dict(archivo="Envases Norte 15532.pdf", prov="envases", letra="A", cod="01", pv="00004", nro="00015532",
         fecha=date(2026, 9, 15), vto=date(2026, 9, 30),
         items=[item("Bolsa de papel kraft panadería N°5", 10000, "unidades", 28, 21),
                item("Caja para tortas 30x30 cm", 1000, "unidades", 100, 21)],
         iva_forzado={21: 83600}),
    dict(archivo="Ferreyra reparacion horno.pdf", prov="ferreyra", letra="A", cod="01", pv="00001", nro="00000412",
         fecha=date(2026, 9, 18), vto=date(2026, 9, 30),
         items=[item("Reparación de horno rotativo: cambio de quemador y service general", 1, "unidades", 420000, 21)]),
    dict(archivo="Grafica Rivadavia folletos.pdf", prov="grafica", letra="A", cod="01", pv="00002", nro="00003310",
         fecha=date(2026, 9, 20), vto=date(2026, 10, 20), receptor=OTRA_EMPRESA,
         items=[item("Folletos publicitarios color A5 - 5.000 unidades", 5000, "unidades", 29, 21)]),
]

CAES = iter([
    "76351284567301", "76381295012457", "76361428830214", "76341190021586", "76365510983422",
    "76371288104573", "76372019845530", "76372019845530", "76351093388217", "76372400018853",
    "76374412093368", "76382017746629", "76384120056731",
])


class Hoja:
    """Ayudante mínimo para dibujar con coordenadas desde arriba."""

    def __init__(self, ruta):
        self.c = canvas.Canvas(str(ruta), pagesize=A4)
        self.W, self.H = A4

    def txt(self, x, y, texto, tam=8.5, negrita=False, alinear="izq"):
        self.c.setFont("Helvetica-Bold" if negrita else "Helvetica", tam)
        yy = self.H - y
        if alinear == "der":
            self.c.drawRightString(x, yy, texto)
        elif alinear == "centro":
            self.c.drawCentredString(x, yy, texto)
        else:
            self.c.drawString(x, yy, texto)

    def linea(self, x1, y1, x2, y2):
        self.c.line(x1, self.H - y1, x2, self.H - y2)

    def caja(self, x, y, w, h):
        self.c.rect(x, self.H - y - h, w, h)

    def guardar(self):
        self.c.setFont("Helvetica-Oblique", 7)
        self.c.drawCentredString(self.W / 2, 28, AVISO)
        self.c.showPage()
        self.c.save()


def encabezado(h, emisor, titulo, letra, cod, pv, nro, fecha):
    W = h.W
    h.caja(20, 20, W - 40, h.H - 40)
    h.txt(W / 2, 38, "ORIGINAL", 12, True, "centro")
    h.linea(20, 45, W - 20, 45)
    h.linea(20, 172, W - 20, 172)
    h.caja(W / 2 - 25, 50, 50, 50)
    h.txt(W / 2, 85, letra, 30, True, "centro")
    h.txt(W / 2, 96, f"COD. {cod}", 7, True, "centro")
    h.linea(W / 2, 100, W / 2, 172)
    largo = len(emisor["razon_social"])
    tam = 13 if largo < 24 else (10.5 if largo < 31 else 9)
    h.txt(30, 75, emisor["razon_social"], tam, True)
    h.txt(30, 115, f"Razón Social: {emisor['razon_social']}")
    h.txt(30, 129, f"Domicilio Comercial: {emisor['domicilio']}")
    h.txt(30, 143, f"Condición frente al IVA: {emisor['condicion']}")
    h.txt(W / 2 + 38, 70, titulo, 15, True)
    h.txt(W / 2 + 38, 92, f"Punto de Venta: {pv}    Comp. Nro: {nro}", 8.5, True)
    h.txt(W / 2 + 38, 106, f"Fecha de Emisión: {fdate(fecha)}", 8.5, True)
    h.txt(W / 2 + 38, 122, f"CUIT: {emisor['cuit']}")
    h.txt(W / 2 + 38, 136, f"Ingresos Brutos: {emisor['iibb']}")
    h.txt(W / 2 + 38, 150, f"Fecha de Inicio de Actividades: {emisor['inicio']}")


def bloque_receptor(h, receptor, y, condicion_venta):
    h.txt(30, y, f"CUIT: {receptor['cuit']}")
    h.txt(200, y, f"Apellido y Nombre / Razón Social: {receptor['razon_social']}")
    h.txt(30, y + 15, f"Condición frente al IVA: {receptor['condicion']}")
    h.txt(30, y + 30, f"Domicilio: {receptor['domicilio']}")
    h.txt(30, y + 45, f"Condición de venta: {condicion_venta}")


def factura_pdf(f, carpeta):
    emisor = PROVEEDORES[f["prov"]]
    receptor = f.get("receptor", EMPRESA)
    letra = f["letra"]
    h = Hoja(carpeta / f["archivo"])
    W = h.W
    encabezado(h, emisor, "FACTURA", letra, f["cod"], f["pv"], f["nro"], f["fecha"])

    desde = f.get("desde", f["fecha"])
    hasta = f.get("hasta", f["fecha"])
    h.txt(30, 188, f"Período Facturado Desde: {fdate(desde)}")
    h.txt(210, 188, f"Hasta: {fdate(hasta)}")
    h.txt(330, 188, f"Fecha de Vto. para el pago: {fdate(f['vto'])}")
    h.linea(20, 196, W - 20, 196)
    bloque_receptor(h, receptor, 212, "Transferencia Bancaria")
    h.linea(20, 266, W - 20, 266)

    # Detalle
    y = 282
    if letra == "A":
        cols = [(28, "Código"), (68, "Producto / Servicio"), (300, "Cantidad"), (345, "U. Medida"),
                (400, "Precio Unit."), (448, "% Bonif"), (482, "Subtotal"), (525, "Alícuota IVA")]
    else:
        cols = [(28, "Código"), (68, "Producto / Servicio"), (300, "Cantidad"), (345, "U. Medida"),
                (400, "Precio Unit."), (448, "% Bonif"), (482, "Imp. Bonif."), (525, "Subtotal")]
    for x, t in cols:
        h.txt(x, y, t, 7, True)
    h.linea(20, y + 5, W - 20, y + 5)

    netos = {}
    total_items = 0.0
    y += 18
    for i, it in enumerate(f["items"], 1):
        precio = it["precio"]
        subtotal = it["cant"] * precio
        total_items += subtotal
        if it["tasa"]:
            netos[it["tasa"]] = netos.get(it["tasa"], 0) + subtotal
        h.txt(28, y, f"{i:03d}", 7)
        h.txt(68, y, it["desc"][:66], 7)
        h.txt(335, y, f"{it['cant']:,}".replace(",", "."), 7, alinear="der")
        h.txt(345, y, it["unidad"], 7)
        h.txt(440, y, num(precio), 7, alinear="der")
        h.txt(470, y, "0,00", 7, alinear="der")
        if letra == "A":
            h.txt(518, y, num(subtotal), 7, alinear="der")
            h.txt(560, y, f"{str(it['tasa']).replace('.', ',')}%", 7, alinear="der")
        else:
            h.txt(518, y, "0,00", 7, alinear="der")
            h.txt(565, y, num(subtotal), 7, alinear="der")
        y += 14

    otros = f.get("otros", [])
    total_otros = sum(o[2] for o in otros)

    # Otros tributos (izquierda)
    yb = 600
    if otros:
        h.txt(30, yb, "Otros tributos", 8, True)
        h.txt(30, yb + 14, "Descripción", 7, True)
        h.txt(200, yb + 14, "Alíc. %", 7, True)
        h.txt(250, yb + 14, "Importe", 7, True)
        for j, (desc, alic, imp) in enumerate(otros):
            h.txt(30, yb + 28 + j * 12, desc, 7)
            h.txt(225, yb + 28 + j * 12, num(alic), 7, alinear="der")
            h.txt(290, yb + 28 + j * 12, num(imp), 7, alinear="der")

    # Totales (derecha)
    xl, xr = 370, W - 30
    if letra == "A":
        ivas = {t: round(n * t / 100, 2) for t, n in netos.items()}
        ivas.update(f.get("iva_forzado", {}))
        neto = sum(netos.values())
        total = neto + sum(ivas.values()) + total_otros
        filas = [("Importe Neto Gravado: $", neto)]
        for t in (27, 21, 10.5, 5, 2.5, 0):
            filas.append((f"IVA {t:g}%: $", ivas.get(t, 0.0)))
        filas += [("Importe Otros Tributos: $", total_otros), ("Importe Total: $", total)]
    else:
        total = total_items + total_otros
        filas = [("Subtotal: $", total_items), ("Importe Otros Tributos: $", total_otros), ("Importe Total: $", total)]
    yt = 590
    for etiqueta, valor in filas:
        negrita = etiqueta.startswith("Importe Total")
        h.txt(xl + 110, yt, etiqueta, 8.5, True, "der")
        h.txt(xr, yt, num(valor), 8.5, negrita, "der")
        yt += 15

    if letra == "B":
        iva_contenido = round(total_items - total_items / 1.21, 2)
        yt += 8
        h.txt(30, yt, "Régimen de Transparencia Fiscal al Consumidor (Ley 27.743)", 8, True)
        h.txt(30, yt + 13, f"IVA Contenido: $ {num(iva_contenido)}", 8)
        h.txt(30, yt + 26, "Otros Impuestos Nacionales Indirectos: $ 0,00", 8)

    # Pie
    h.linea(20, 760, W - 20, 760)
    h.caja(30, 768, 46, 46)
    h.txt(53, 794, "QR", 9, True, "centro")
    h.txt(90, 784, "Comprobante Autorizado", 9, True)
    h.txt(90, 798, "Pág. 1/1", 7)
    cae = next(CAES)
    vto_cae = date.fromordinal(f["fecha"].toordinal() + 10)
    h.txt(xr, 784, f"CAE N°: {cae}", 8.5, True, "der")
    h.txt(xr, 798, f"Fecha de Vto. de CAE: {fdate(vto_cae)}", 8.5, True, "der")
    h.guardar()
    return total


def remito_pdf(carpeta):
    emisor = PROVEEDORES["molino"]
    h = Hoja(carpeta / "remito molino.pdf")
    W = h.W
    encabezado(h, emisor, "REMITO", "R", "091", "00005", "00031877", date(2026, 9, 3))
    h.txt(30, 188, "Documento no válido como factura")
    h.linea(20, 196, W - 20, 196)
    bloque_receptor(h, EMPRESA, 212, "Cuenta corriente")
    h.linea(20, 266, W - 20, 266)
    h.txt(28, 282, "Código", 7, True)
    h.txt(68, 282, "Descripción", 7, True)
    h.txt(400, 282, "Cantidad", 7, True)
    h.txt(460, 282, "U. Medida", 7, True)
    h.linea(20, 287, W - 20, 287)
    h.txt(28, 300, "001", 7)
    h.txt(68, 300, "Harina de trigo 000 - bolsa 25 kg", 7)
    h.txt(440, 300, "40", 7, alinear="der")
    h.txt(460, 300, "unidades", 7)
    h.txt(30, 340, "Referencia: Factura A 0005-00012841", 8)
    h.txt(30, 354, "Transportista: Logística Luján SRL - Patente AF 482 KD", 8)
    h.txt(30, 368, "Recibí conforme: ______________________   Aclaración: ______________", 8)
    h.guardar()


def extracto_csv(carpeta):
    m = PROVEEDORES
    movs = [
        (date(2026, 9, 1), "ACREDITACION LIQ. PAYWAY", "LOTE 0831 TERM 22871", 0, 412380.50),
        (date(2026, 9, 2), "TRANSF. RECIBIDA - CAFE LOS ANDES SRL", f"CUIT {CUIT_CAFE} FAC 0002-00001520", 0, 286000.00),
        (date(2026, 9, 3), "TRANSF. A TERCEROS - MARTINEZ ROBERTO CARLOS", f"CUIT {CUIT_MARTINEZ} VAR - ALQ SEPT", 850000.00, 0),
        (date(2026, 9, 4), "DEPOSITO EN EFECTIVO", "SUC 045 RAMOS MEJIA", 0, 350000.00),
        (date(2026, 9, 7), "TRANSF. A TERCEROS - INSUMOS GASTRONOMICOS DEL CENTRO", f"CUIT {m['insumos']['cuit']} VAR", 139150.00, 0),
        (date(2026, 9, 8), "ACREDITACION LIQ. PAYWAY", "LOTE 0907 TERM 22871", 0, 498215.30),
        (date(2026, 9, 10), "TRANSF. A TERCEROS - GOMEZ MARIA LAURA", f"CUIT {m['gomez']['cuit']} HON", 350000.00, 0),
        (date(2026, 9, 15), "ACREDITACION LIQ. PAYWAY", "LOTE 0914 TERM 22871", 0, 527904.10),
        (date(2026, 9, 15), "TRANSF. A TERCEROS - INSUMOS GASTRONOMICOS DEL CENTRO", f"CUIT {m['insumos']['cuit']} VAR", 147250.00, 0),
        (date(2026, 9, 16), "TRANSF. A TERCEROS - LIMPIEZA TOTAL SRL", f"CUIT {m['limpieza']['cuit']} VAR", 96800.00, 0),
        (date(2026, 9, 18), "TRANSF. RECIBIDA - CAFE LOS ANDES SRL", f"CUIT {CUIT_CAFE} FAC 0002-00001544", 0, 312400.00),
        (date(2026, 9, 21), "TRANSF. A TERCEROS - FLETES RAPIDOS DEL OESTE SRL", f"CUIT {m['fletes']['cuit']} VAR", 223850.00, 0),
        (date(2026, 9, 22), "DEBITO AUTOMATICO - ENERGIA DEL PLATA SA", "CLIENTE 0045-778812", 273000.00, 0),
        (date(2026, 9, 22), "ACREDITACION LIQ. PAYWAY", "LOTE 0921 TERM 22871", 0, 541770.80),
        (date(2026, 9, 23), "DEPOSITO EN EFECTIVO", "SUC 045 RAMOS MEJIA", 0, 280000.00),
        (date(2026, 9, 25), "TRANSF. A TERCEROS - MOLINO HARINERO SAN MARTIN SA", f"CUIT {m['molino']['cuit']} FC 12841 Y 12967", 1971320.00, 0),
        (date(2026, 9, 28), "TRANSF. A TERCEROS - ENVASES Y PACKAGING NORTE SA", f"CUIT {m['envases']['cuit']} VAR", 463600.00, 0),
        (date(2026, 9, 29), "ACREDITACION LIQ. PAYWAY", "LOTE 0928 TERM 22871", 0, 509118.40),
        (date(2026, 9, 29), "TRANSF. A TERCEROS - FERREYRA MANTENIMIENTO IND", f"CUIT {cuit('3071234560')} VAR", 508200.00, 0),
        (date(2026, 9, 30), "COMISION MANTENIMIENTO CUENTA", "PAQUETE PYME", 18500.00, 0),
        (date(2026, 9, 30), "IVA 21% S/COMISIONES", "", 3885.00, 0),
        (date(2026, 9, 30), "PERCEPCION IVA RG 2408", "", 555.00, 0),
    ]
    creditos = sum(c for *_, c in movs)
    debitos = sum(d for *_, d, _c in movs)
    sircreb = round(creditos * 0.012, 2)
    imp_cred = round(creditos * 0.006, 2)
    imp_deb = round((debitos + sircreb + imp_cred) * 0.006, 2)
    movs += [
        (date(2026, 9, 30), "RETENCION IIBB SIRCREB", "REG. 1,20%", sircreb, 0),
        (date(2026, 9, 30), "IMP. LEY 25413 S/CREDITOS 0,6%", "", imp_cred, 0),
        (date(2026, 9, 30), "IMP. LEY 25413 S/DEBITOS 0,6%", "", imp_deb, 0),
    ]
    saldo = 3250000.00
    ruta = carpeta / "extracto_banco_ribera_cc_2026-09.csv"
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        fh.write("Banco de la Ribera S.A. - Extracto de Cuenta Corriente en Pesos\n")
        fh.write(f"Titular: {EMPRESA['razon_social']} - CUIT {EMPRESA['cuit']}\n")
        fh.write("Cuenta: CC $ 0123-004567/8 - CBU 4560123700000456780018\n")
        fh.write("Período: 01/09/2026 al 30/09/2026\n\n")
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Fecha", "Concepto", "Referencia", "Débito", "Crédito", "Saldo"])
        w.writerow(["01/09/2026", "SALDO ANTERIOR", "", "", "", num(saldo)])
        minimo = saldo
        for d, concepto, ref, deb, cred in movs:
            saldo = round(saldo - deb + cred, 2)
            minimo = min(minimo, saldo)
            w.writerow([fdate(d), concepto, ref, num(deb) if deb else "", num(cred) if cred else "", num(saldo)])
        w.writerow(["30/09/2026", "SALDO FINAL", "", "", "", num(saldo)])
    assert minimo > 0
    return saldo


def datos_empresa(carpeta):
    texto = f"""DATOS DE LA EMPRESA (cliente del estudio)

Razón social: {EMPRESA['razon_social']}
CUIT: {EMPRESA['cuit'][:2]}-{EMPRESA['cuit'][2:10]}-{EMPRESA['cuit'][10]}
Condición frente al IVA: Responsable Inscripto
Actividad: Elaboración de productos de panadería y pastelería
Domicilio: {EMPRESA['domicilio']}
Banco: Banco de la Ribera S.A. - Cuenta corriente en pesos N° 0123-004567/8
Período a procesar: septiembre 2026 (09/2026)
Contacto administrativo: Carla Benítez (administracion@laespigadorada.example)

Nota del cliente: "Te mando todo lo de septiembre: facturas de proveedores y el extracto del banco."

{AVISO}
"""
    (carpeta / "00_datos_empresa.txt").write_text(texto, encoding="utf-8")


def main():
    comprobantes = SALIDA / "comprobantes"
    comprobantes.mkdir(parents=True, exist_ok=True)
    for viejo in comprobantes.glob("*.pdf"):
        viejo.unlink()
    for f in FACTURAS:
        total = factura_pdf(f, comprobantes)
        print(f"  {f['archivo']:<40} {fmt_pesos(total):>18}")
    remito_pdf(comprobantes)
    print("  remito molino.pdf")
    saldo = extracto_csv(SALIDA)
    datos_empresa(SALIDA)
    print(f"\nExtracto generado. Saldo final: {fmt_pesos(saldo)}")
    print(f"Datos en: {SALIDA}")


if __name__ == "__main__":
    main()
