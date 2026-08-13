# Versionar formatos de propuesta (Print Formats)

Cuando cambia el diseño de un formato de propuesta (por ejemplo, la **Propuesta de Servicios
Profesionales**), **no se edita el formato existente**: se crea una **versión nueva** y se deja la
anterior como referencia. Así, las propuestas ya emitidas conservan exactamente su presentación y las
propuestas nuevas usan el diseño actualizado.

Esta página describe el **procedimiento operativo** para quien administra Print Formats y Proposal
Templates manualmente.

---

## 1. Crear una versión nueva del formato

Al publicar un cambio de diseño:

1. **Crea un Print Format nuevo** (no modifiques el HTML/CSS del anterior).
2. Usa la **convención de nombres**:

   ```
   <Familia> — AAAA-MM-DD — Vn
   ```

   Ejemplo: `Propuesta de Servicios Profesionales — 2026-08-12 — V1`. La fecha es la de entrada en
   vigor; si hay más de una revisión el mismo día, usa `V2`, `V3`, …
3. El formato nuevo debe quedar:
   - **Tipo de documento (`doc_type`) = Quotation**;
   - **Deshabilitado = No** (`disabled = 0`).
4. **Mantén intacto el formato anterior** y márcalo **Deshabilitado = Sí** (`disabled = 1`). No lo
   renombres ni lo elimines: sigue siendo la referencia histórica.

> El sistema **permite** deshabilitar un formato anterior aunque ya lo hayan usado propuestas
> congeladas; **no permite** cambiar su HTML/CSS, renombrarlo ni borrarlo.

---

## 2. Apuntar los Proposal Templates a la versión vigente

Después de publicar el formato nuevo:

1. Abre cada **Proposal Template** que deba usar el diseño nuevo.
2. En el campo **Print Format**, **selecciona explícitamente** la versión vigente
   (`… — AAAA-MM-DD — Vn`).
3. Guarda. Las propuestas nuevas creadas a partir de ese Template usarán el formato nuevo.

> No hay reemplazo automático: eres tú quien elige la versión vigente en cada Template.

---

## 3. Qué formatos ofrecen los selectores

Los campos donde se elige el formato de una propuesta:

- **Cotización → Proposal Print Format** (`proposal_print_format`);
- **Proposal Template → Print Format**;

muestran **solo** formatos que cumplen:

- **Tipo de documento = Quotation**;
- **Deshabilitado = No**.

Es decir, un formato deshabilitado **deja de aparecer** para nuevas selecciones (aunque siga existiendo
como referencia). Esto no afecta al botón de **Imprimir** estándar de Frappe.

---

## 4. Aviso cuando un Template apunta a un formato obsoleto

Si un **Proposal Template** existente sigue apuntando a un Print Format que fue **deshabilitado** (o que
ya no existe):

- al abrir el Template, el sistema muestra un **aviso** junto al campo Print Format;
- **no** se reemplaza el valor automáticamente;
- debes **seleccionar manualmente** la versión vigente para quitar el aviso.

---

## 5. Propuestas congeladas y el formato histórico

Cuando una propuesta pasa a **En Revisión** (freeze):

- se **generan y adjuntan** sus **PDFs oficiales** (Propuesta Comercial y Rentabilidad Estimada). Esos
  adjuntos son el **histórico oficial** de la propuesta y están protegidos contra borrado.
- Una propuesta congelada **no se reimprime** como flujo normal: para consultarla se usan **los PDFs
  oficiales ya adjuntos**, no se vuelve a generar.
- El Print Format que usó queda registrado como **referencia** (auditoría). Ese formato histórico
  **no debe modificarse**; si necesitas un diseño distinto, creas una **versión nueva** (sección 1).

> Por eso deshabilitar un formato anterior es seguro: el histórico de cada propuesta congelada vive en
> su PDF oficial adjunto, no en volver a renderizar el formato.
