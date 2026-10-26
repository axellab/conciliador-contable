"""Arma los .zip para compartir en dist/.

  conciliador-contable.zip  La skill, con la carpeta en la raíz (formato que pide claude.ai).
  datos_demo.zip            La carpeta ficticia de La Espiga Dorada para probar.

Uso:  python herramientas/empaquetar.py
"""
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIST = RAIZ / "dist"
IGNORAR = {"__pycache__", ".DS_Store", "Thumbs.db"}


def comprimir(carpeta, destino):
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for ruta in sorted(carpeta.rglob("*")):
            if ruta.is_file() and not (set(ruta.parts) & IGNORAR) and ruta.suffix != ".pyc":
                zf.write(ruta, ruta.relative_to(carpeta.parent).as_posix())
    with zipfile.ZipFile(destino) as zf:
        nombres = zf.namelist()
    print(f"{destino.name}: {len(nombres)} archivos, {destino.stat().st_size / 1024:.0f} KB")
    return nombres


def main():
    DIST.mkdir(exist_ok=True)
    nombres = comprimir(RAIZ / "conciliador-contable", DIST / "conciliador-contable.zip")
    assert "conciliador-contable/SKILL.md" in nombres, "SKILL.md tiene que quedar dentro de la carpeta raíz del zip"
    comprimir(RAIZ / "datos_demo" / "La_Espiga_Dorada_2026-09", DIST / "datos_demo.zip")


if __name__ == "__main__":
    main()
