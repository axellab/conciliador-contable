# Formato de `comprobantes.json`

`leer_comprobantes.py` genera un objeto con estas claves:

- `comprobantes`: lista de comprobantes (ver abajo).
- `otros_documentos`: remitos, textos, imágenes y PDF no reconocidos (`id` D01, D02…).
- `extractos_bancarios`: archivos que parecen extractos.
- `datos_empresa_en_archivos` / `datos_empresa_inferidos`: CUIT, razón social y período detectados.

## Un comprobante

```json
{
  "id": "C05",
  "archivo": "comprobantes/Insumos 4410.pdf",
  "clase": "Factura",                 // "Factura" | "Nota de Crédito" | "Nota de Débito"
  "tipo": "A",                         // A | B | C | M
  "codigo_arca": "001",
  "punto_venta": "00002",              // 5 dígitos
  "numero": "00004410",                // 8 dígitos
  "fecha": "2026-09-08",               // AAAA-MM-DD
  "fecha_vto_pago": "2026-09-18",
  "emisor":   {"cuit": "30711223343", "razon_social": "...", "condicion_iva": "IVA Responsable Inscripto"},
  "receptor": {"cuit": "30715832468", "razon_social": "...", "condicion_iva": "IVA Responsable Inscripto"},
  "neto_gravado": 124000.0,            // solo A y M
  "no_gravado": 0.0,
  "exento": 0.0,
  "alicuotas": [                       // una entrada por alícuota de IVA (solo A y M)
    {"tasa": 21.0, "neto": 100000.0, "iva": 21000.0},
    {"tasa": 10.5, "neto": 24000.0, "iva": 2520.0}
  ],
  "iva_total": 23520.0,
  "subtotal": null,                    // solo B y C: importe antes de otros tributos
  "otros_tributos": 0.0,               // percepciones y otros tributos
  "total": 147520.0,
  "iva_contenido": null,               // Factura B (Ley 27.743)
  "cae": "76361428830214",
  "vto_cae": "2026-09-18",
  "detalle": ["Levadura fresca prensada - kg", "..."],
  "cuenta_sugerida": {"codigo": "5.1.01", "nombre": "Compras de materias primas e insumos", "coincidencias": 9},
                                       // coincidencias = cuántas palabras clave del plan aparecieron;
                                       // con 1 o 2, revisá la sugerencia con más cuidado
  "cuenta": "5.1.01",                  // OPCIONAL: la agrega el agente si corrige la sugerencia
  "incluir": true,                     // OPCIONAL: decisión del profesional (pisa la exclusión automática)
  "motivo_decision": "No se registró en agosto",  // OPCIONAL: acompaña a "incluir"
  "revisar": false,
  "motivos_revision": [],
  "campos_faltantes": [],
  "texto_extraido": "trabajo/textos/C05.txt"
}
```

## Reglas al corregir a mano

- Importes con punto decimal y sin separador de miles: `1082900.0`.
- CUIT solo con dígitos (11).
- En facturas A, `neto_gravado` es la suma de los `neto` de `alicuotas`, e `iva_total` la suma de los `iva`.
- En facturas B y C, `alicuotas` queda vacía e `iva_total` en 0. El total va en `total`.
- Cuando completes un dato, sacalo de `campos_faltantes`. Si ya no falta nada, poné `"revisar": false`.
- Si agregás un comprobante que no tenía PDF legible, usá el siguiente `id` libre (C14, C15…).
