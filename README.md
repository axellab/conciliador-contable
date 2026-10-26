# Conciliador Contable: un agente de IA para el cierre mensual

## Descargas

| Archivo | Para qué |
|---|---|
| [**conciliador-contable.zip**](https://github.com/axellab/conciliador-contable/releases/latest/download/conciliador-contable.zip) | La skill que se instala en Claude |
| [**datos_demo.zip**](https://github.com/axellab/conciliador-contable/releases/latest/download/datos_demo.zip) | Una carpeta de prueba con facturas y extracto ficticios |

Después seguí los pasos de [Instalación](#instalación-en-claudeai-5-minutos-sin-programar).

---

Le das la carpeta que te manda un cliente a fin de mes (facturas de proveedores en PDF y el extracto del
banco) y te devuelve los **papeles de trabajo listos para revisar**:

- **Excel** con Resumen, Observaciones, Libro IVA Compras, Conciliación bancaria, Pendientes de pago,
  Asientos propuestos y Detalle de comprobantes.
- **Memo en Word** para pedirle al cliente lo que falta.

En el camino controla lo que un buen auxiliar controlaría:

| Control | Ejemplo |
|---|---|
| Facturas duplicadas | El cliente mandó la misma factura dos veces con otro nombre de archivo |
| Factura emitida a otro CUIT | La factura está a nombre de otra empresa del grupo |
| CUIT inválido | El dígito verificador no cierra: error de tipeo o comprobante apócrifo |
| Fuera de período | Una factura de agosto en la carpeta de septiembre |
| IVA mal calculado | 22% en lugar de 21%: solo se computa el IVA correcto |
| Factura B a un Responsable Inscripto | El IVA no se puede computar: pedir Factura A |
| Pagos sin comprobante | Salió plata del banco y no hay factura |
| Diferencias de pago | Detecta dígitos invertidos (el truco de "la diferencia es divisible por 9") |
| Gastos bancarios sin registrar | Comisiones, IVA, percepciones, SIRCREB e impuesto Ley 25.413 |
| Integridad del extracto | Saldo inicial + créditos - débitos = saldo final |

> **Importante:** es una herramienta de apoyo. No presenta nada en ARCA, no paga ni envía nada. Todo lo
> que produce es una **propuesta** que revisa y decide el profesional.

---

## Instalación en claude.ai (5 minutos, sin programar)

Funciona con cualquier cuenta de Claude, incluso la gratuita. En el plan gratuito el uso es más limitado y,
con muchas facturas, puede que tengas que esperar o procesarlas en tandas.

1. **Descargá** el archivo `conciliador-contable.zip`. No lo descomprimas.
2. En [claude.ai](https://claude.ai) andá a **Configuración → Capacidades** y activá
   **"Ejecución de código y creación de archivos"** (en la versión nueva se llama "Crear y editar archivos").
3. Andá a **Personalizar (Customize) → Skills**, tocá **"+" → "Crear skill" → "Subir una skill"** y
   elegí el zip. Verificá que quede **activada**.

Los nombres de los menús pueden variar un poco según la versión de claude.ai.

## Cómo usarlo

1. Abrí un chat nuevo.
2. Adjuntá las facturas en PDF y el extracto del banco (CSV o Excel). También podés subir todo junto en un
   `.zip`.
3. Escribí, por ejemplo:

   > Te paso la documentación de septiembre de mi cliente. ¿Me armás los papeles de trabajo y me decís qué encontraste?

4. Mirá cómo trabaja: va contando cada paso. Al final te deja el Excel y el memo para descargar.

Después podés seguir conversando. Por ejemplo: *"Redactame un WhatsApp para el proveedor de limpieza
pidiéndole la Factura A"* o *"¿Cuánto crédito fiscal estamos perdiendo por las observaciones?"*.

**¿Querés probarlo ya?** Descargá `datos_demo.zip`: es la carpeta de una panadería ficticia con 8 errores
escondidos. Subila y fijate si el agente los encuentra todos.

---

## Otras formas de usarlo

**Claude Code (para quien se anime a la terminal).** Copiá la carpeta `conciliador-contable` a
`~/.claude/skills/` (en Windows: `C:\Users\<tu usuario>\.claude\skills\`). Abrí una terminal en la carpeta
del cliente, ejecutá `claude` y pedile que procese la carpeta. Necesitás Python 3 y estas librerías:

```bash
pip install pdfplumber openpyxl python-docx
```

**Cowork (Claude Desktop).** Si usás Cowork, podés aprovechar la misma skill trabajando directo sobre una
carpeta de tu computadora. Verificá que esté activada en Personalizar → Skills.

---

## Cómo adaptarlo a tu estudio

La skill es una carpeta con texto y scripts, sin magia. Podés abrirla y cambiarla:

| Archivo | Qué es | Qué podés cambiar |
|---|---|---|
| `SKILL.md` | El **procedimiento** que sigue la IA, escrito en castellano | Los pasos, el tono del memo, qué controles priorizar |
| `referencias/plan_de_cuentas.json` | Plan de cuentas de ejemplo | Tus códigos y nombres de cuenta, y las palabras clave que sirven para sugerir la cuenta de cada factura |
| `referencias/reglas_banco.json` | Cómo clasificar movimientos sin factura | Los conceptos de tu banco (comisiones, impuestos, etc.) |
| `referencias/modelo_memo.md` | Estructura del memo al cliente | El estilo de comunicación de tu estudio |
| `scripts/` | Los cálculos y controles (Python) | Nuevos controles, si sabés programar o le pedís ayuda a Claude |

Después de cambiar algo, volvé a comprimir la carpeta `conciliador-contable` (la carpeta entera, no su
contenido) y subila de nuevo.

Si sabés escribir un procedimiento de control interno, sabés escribir un agente.

---

## Cómo funciona

```
Carpeta del cliente
      │
      ▼
1. Inventario y lectura ──► El código extrae los datos de cada PDF.
      │                    La IA revisa lo dudoso, clasifica documentos y asigna cuentas.
      ▼
2. Controles ────────────► Reglas fijas: CUIT, duplicados, período, IVA, tipo de comprobante, CAE.
      │
      ▼
3. Conciliación ─────────► Cruce banco-facturas, pagos múltiples, diferencias, gastos bancarios.
      │                    La IA interpreta lo que no cierra (por ejemplo, "ALQ SEPT" = alquiler).
      ▼
4. Papeles de trabajo ───► Excel con fórmulas y asientos balanceados.
      │
      ▼
5. Memo al cliente ──────► La IA redacta y el código lo pasa a Word.
```

**La regla de oro: la IA lee y razona, las cuentas las hace el código.** El modelo de lenguaje interpreta
documentos y decide el próximo paso. Los importes, sumas y controles los calculan scripts que dan siempre
el mismo resultado.

## Límites conocidos

- Lee automáticamente las facturas electrónicas con el formato estándar de ARCA. Con otros formatos,
  escaneos o fotos, la IA completa los datos leyendo el documento, pero conviene revisarlos.
- Procesa **compras** y **banco**. Las ventas y cobranzas quedan identificadas en el banco para cruzarlas
  aparte.
- El plan de cuentas y las reglas son de ejemplo: adaptalos a tu cliente.
- No consulta ARCA en línea: la validación del CUIT es matemática (dígito verificador), no del padrón.

## Confidencialidad

Los comprobantes tienen datos de tus clientes y de terceros. Antes de usarlo con datos reales:

- Revisá en **Configuración → Privacidad** si permitís que tus conversaciones se usen para mejorar los
  modelos.
- Si trabajás en un estudio, considerá un plan de equipo o empresa con condiciones de datos acordes.
- Para probar o capacitar, usá los datos ficticios o anonimizá nombres y CUIT.

## Contenido del repositorio

```
conciliador-contable/      La skill (esto es lo que se instala)
  SKILL.md                 Procedimiento del agente
  scripts/                 Lectura, controles, conciliación, Excel y memo
  referencias/             Plan de cuentas, reglas del banco, formatos y modelo de memo
datos_demo/                Carpeta ficticia de "La Espiga Dorada SRL" (septiembre 2026)
ejemplo_resultado/         Lo que produce el agente con los datos de demo
herramientas/              Generador de los datos ficticios
dist/                      Los .zip listos para descargar
```

Todos los nombres, CUIT, CAE e importes de los datos de demo son **ficticios**. Cualquier coincidencia con
personas o empresas reales es casual.
