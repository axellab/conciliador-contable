"""Verifica el dígito verificador de uno o más CUIT/CUIL.

Uso:
  python verificar_cuit.py 30-71234560-4 30712345607
"""
import sys

from comun import cuit_valido, formatear_cuit, preparar_consola, solo_digitos


def main():
    preparar_consola()
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for cuit in sys.argv[1:]:
        d = solo_digitos(cuit)
        estado = "VÁLIDO" if cuit_valido(d) else ("INVÁLIDO" if len(d) == 11 else "INVÁLIDO (no tiene 11 dígitos)")
        print(f"{formatear_cuit(d):<15} {estado}")


if __name__ == "__main__":
    main()
