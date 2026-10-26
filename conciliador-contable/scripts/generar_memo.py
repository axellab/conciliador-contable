"""Paso 5: pasa a Word el memo para el cliente que redactó el agente.

Entiende un Markdown simple: títulos (#, ##, ###), viñetas (- ), listas numeradas (1. ),
**negrita** y párrafos (uno por línea). Una línea con sangría que sigue a un ítem se suma a ese ítem.
La numeración vuelve a 1 en cada título. Si no está instalada python-docx, deja el memo en .md.

Uso:
  python generar_memo.py --memo <trabajo>/memo.md --salida <carpeta_de_salida> [--nombre Memo_para_el_cliente]
"""
import argparse
import re
import shutil
from pathlib import Path

from comun import preparar_consola, titulo_paso


def bloques(lineas):
    """Agrupa el Markdown en (tipo, texto). Une las líneas de continuación de cada ítem o párrafo."""
    resultado = []
    for linea in lineas:
        texto = linea.rstrip()
        if not texto.strip() or texto.strip() == "---":
            resultado.append(("vacio", ""))
            continue
        m = re.match(r"^(#{1,3}) (.+)", texto)
        if m:
            resultado.append((f"titulo{len(m.group(1))}", m.group(2).strip()))
        elif re.match(r"^\s*[-*] ", texto):
            resultado.append(("vineta", re.sub(r"^\s*[-*] ", "", texto)))
        elif re.match(r"^\s*\d+[.)] ", texto):
            resultado.append(("numero", re.sub(r"^\s*\d+[.)] ", "", texto)))
        elif texto[:1].isspace() and resultado and resultado[-1][0] in ("vineta", "numero"):
            tipo, previo = resultado[-1]
            resultado[-1] = (tipo, f"{previo} {texto.strip()}")
        else:
            resultado.append(("parrafo", texto.strip()))
    return [b for b in resultado if b[0] != "vacio"]


def agregar_texto(parrafo, texto):
    for i, parte in enumerate(re.split(r"\*\*(.+?)\*\*", texto)):
        if parte:
            parrafo.add_run(parte).bold = i % 2 == 1


def main():
    preparar_consola()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--memo", required=True)
    ap.add_argument("--salida", default="salida")
    ap.add_argument("--nombre", default="Memo_para_el_cliente")
    args = ap.parse_args()

    titulo_paso("PASO 5 - Memo para el cliente")
    origen = Path(args.memo)
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)

    try:
        from docx import Document
        from docx.shared import Cm, Pt
    except ImportError:
        destino = salida / f"{args.nombre}.md"
        shutil.copy(origen, destino)
        print(f"python-docx no está instalado: dejé el memo en Markdown -> {destino.resolve()}")
        return

    doc = Document()
    estilo = doc.styles["Normal"]
    estilo.font.name = "Calibri"
    estilo.font.size = Pt(11)
    numero = 0
    for tipo, texto in bloques(origen.read_text(encoding="utf-8").splitlines()):
        if tipo.startswith("titulo"):
            doc.add_heading(texto, level=int(tipo[-1]))
            numero = 0
        elif tipo == "vineta":
            agregar_texto(doc.add_paragraph(style="List Bullet"), texto)
        elif tipo == "numero":
            numero += 1
            parrafo = doc.add_paragraph()
            parrafo.paragraph_format.left_indent = Cm(0.9)
            parrafo.paragraph_format.first_line_indent = Cm(-0.6)
            agregar_texto(parrafo, f"{numero}. {texto}")
        else:
            agregar_texto(doc.add_paragraph(), texto)
    destino = salida / f"{args.nombre}.docx"
    doc.save(destino)
    print(f"Memo generado: {destino.resolve()}")


if __name__ == "__main__":
    main()
