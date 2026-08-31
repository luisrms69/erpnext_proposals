# Generar y enviar la propuesta al cliente

## Documentos disponibles

El módulo incluye dos documentos PDF para la Cotización:

| PDF | Propósito | Para quién |
|---|---|---|
| **Propuesta Comercial** | Propuesta formal para el cliente | Cliente externo |
| **Rentabilidad Estimada** | Análisis de margen y costos | Uso interno — solo Proposals Manager y administradores |

!!! note "¿No ves los formatos en el selector de impresión?"
    Los formatos de impresión se **cargan en el site al instalar la app** (durante `bench migrate`).
    No es algo que el usuario final cargue manualmente. Si al imprimir una Cotización no aparecen
    **Propuesta Comercial** ni **Rentabilidad Estimada** en el selector de formato, el administrador
    del site debe cargarlos siguiendo la
    [guía de despliegue → Cargar los Print Formats](../tecnico/despliegue-produccion.md#5-cargar-los-print-formats).

---

## Cómo generar el PDF "Propuesta Comercial"

### Desde la Cotización

1. Abrir la Cotización con la propuesta lista
2. Hacer clic en el botón de **Imprimir** (ícono de impresora) en la barra superior, o usar el menú **Herramientas → Imprimir**
3. En el selector de formato, elegir **"Propuesta Comercial"**
4. El sistema genera la vista previa del PDF en pantalla
5. Para guardar como archivo: usar el botón de descarga en la vista previa (ícono de descarga o PDF)

### Qué formato de propuesta se usa

El módulo agrega el botón **Propuesta → Imprimir Propuesta Comercial**, que elige **automáticamente**
el formato que corresponde a la propuesta y **descarga el PDF directamente** (ya no abre la vista previa
de impresión en una pestaña). El PDF lo genera el renderer configurado para ese formato, según esta
precedencia:

1. **Override de la propuesta** — campo **Proposal Print Format** (pestaña Propuesta), editable en
   Borrador. Si tiene valor, ese formato manda.
2. **Formato del Proposal Template** — si el template asignado define un formato, se usa ese.
3. **Default del sistema** — `Propuesta Comercial` (genérico).

El campo Proposal Print Format muestra abajo *"Formato efectivo actual: …"* para que sepas cuál se
usará. Al pasar la propuesta a **En Revisión**, el formato efectivo **se congela**: una propuesta ya
emitida no cambia de formato aunque después cambien los defaults. Una **nueva versión** hereda ese
formato como override editable.

> El botón **Imprimir** genérico de la barra superior te deja elegir cualquier formato manualmente y
> abre la vista previa en pantalla; el botón **Imprimir Propuesta Comercial** aplica la resolución
> automática descrita arriba y **descarga** el PDF ya generado por el renderer configurado.

### Sincronización con el catálogo al generar el PDF (en Borrador)

Mientras la propuesta está en **Borrador**, al pulsar **Imprimir Propuesta Comercial** o **Imprimir
Rentabilidad Estimada** aparece primero un **aviso de sincronización con el catálogo**:

- Si **Confirmas**, el sistema **sincroniza el alcance con el catálogo vigente** (mismo efecto que
  **Propuesta → Sincronizar alcance con catálogo**) y **después** genera el PDF, de modo que cada PDF de
  revisión refleja el catálogo actual. Cada nueva generación en Borrador vuelve a mostrar el aviso y a
  sincronizar.
- Si **Cancelas**, **no** se sincroniza y **no** se genera el PDF.

Al pasar la propuesta a **En Revisión** (freeze), el sistema **NO** vuelve a sincronizar: congela y
adjunta los PDFs oficiales con el contenido **exactamente como quedó tras tu última revisión**; los
cambios que ocurran en el catálogo después de esa revisión **no** se incorporan a la propuesta ya
formalizada.

### Cuándo dejan de estar disponibles "Imprimir Propuesta Comercial" / "Imprimir Rentabilidad Estimada"

Cuando la propuesta pasa a **En Revisión**, el sistema **genera y adjunta automáticamente** los
documentos oficiales: la **Propuesta Comercial** (para el cliente) y la **Rentabilidad Estimada**
(interna). Una vez que un documento oficial ya está generado y adjunto, su acción de **volver a
generarlo** desaparece del botón **Propuesta**:

- Si ya existe la Propuesta Comercial oficial → deja de mostrarse **Imprimir Propuesta Comercial**.
- Si ya existe la Rentabilidad Estimada oficial → deja de mostrarse **Imprimir Rentabilidad Estimada**.

Esto evita reimprimir/generar por accidente una versión distinta después de formalizar la propuesta.
La comprobación es **real** sobre los adjuntos (no depende solo del estado): si por algún motivo un
documento oficial no llegó a generarse, su acción de generar **permanece** disponible para completarlo.
Los botones de **descarga** de los documentos oficiales ya generados (**↓ …**) siguen disponibles, y el
botón **Imprimir** genérico de la barra superior no se ve afectado.

### Los documentos oficiales no pueden eliminarse por accidente

Una vez generados y adjuntados, la **Propuesta Comercial** y la **Rentabilidad Estimada** oficiales
quedan **protegidas contra eliminación**: son la evidencia formal de la propuesta emitida. Ni un
usuario normal ni un System Manager pueden borrarlas desde los adjuntos; **solo un Administrator** puede
hacerlo deliberadamente. La protección se mantiene aunque la propuesta se cancele. **No** afecta a los
demás adjuntos de la cotización (esos se borran normalmente) ni a la **descarga/apertura** de los
documentos oficiales.

### Los documentos oficiales se adjuntan como archivos privados

Al congelar la propuesta, **ambos** documentos oficiales —la **Propuesta Comercial** y la
**Rentabilidad Estimada**— se adjuntan como **archivos privados**: no quedan accesibles mediante una
URL pública. Los usuarios con permiso sobre la Cotización los **abren y descargan normalmente** desde
los adjuntos (por ejemplo, para enviar la Propuesta Comercial al cliente por correo); Frappe valida el
permiso al servir el archivo. Así se evita que el PDF de la propuesta quede expuesto por un enlace
público.

### Qué contiene el PDF

El PDF "Propuesta Comercial" incluye:

1. **Portada** — Nombre de la empresa, título de la propuesta, folio de cotización, cliente, fecha, vigencia y moneda
2. **Secciones narrativas** — Las secciones del template asignado (Objetivo, Metodología, Exclusiones, etc.) con su contenido
3. **Plan de Trabajo** — Tabla de actividades del alcance, agrupadas por fase. Incluye perfil, tipo de actividad, horas estimadas, días estimados y totales por fase
4. **Entregables** — Lista de entregables por actividad (cuando están definidos)
5. **Inversión** — Tabla de ítems de la cotización con cantidades, precios unitarios y subtotales
6. **Totales** — Subtotal, descuento, impuestos y total general en la moneda de la cotización
7. **Condiciones Comerciales** — Contenido del campo "Términos y Condiciones" de la cotización, si existe
8. **Bloque de aceptación** — Líneas de firma para cliente y proveedor

### Condiciones para que el PDF sea completo

El PDF funciona aunque falten datos, pero puede quedar incompleto:

| Dato faltante | Qué falta en el PDF |
|---|---|
| Template de propuesta no asignado | Las secciones narrativas no aparecen |
| Sin actividades en la tabla de alcance | La sección Plan de Trabajo aparece vacía |
| Sin "Tipo de actividad" en las actividades | La columna de tipo no aparece en el Plan de Trabajo |
| Sin "Perfil" en las actividades | La columna de perfil no aparece en el Plan de Trabajo |
| Sin entregables en las actividades | La sección Entregables no aparece |
| Sin condiciones comerciales en la cotización | La sección Condiciones Comerciales no aparece |

### Limitación conocida — contenido HTML en secciones

El contenido de las Secciones de propuesta puede incluir formato (negritas, listas, párrafos). En algunos entornos este formato se renderiza correctamente en el PDF, pero en otros puede aparecer como texto con etiquetas visibles (ej: `<p>Texto</p>`).

**Solución temporal:** Usar texto plano sin formato en el contenido de las secciones hasta que esta limitación sea resuelta. Ver [Limitaciones del RC](limitaciones-rc.md).

---

## Cómo generar el PDF "Rentabilidad Estimada"

1. Abrir la Cotización
2. Hacer clic en **Imprimir** y seleccionar **"Rentabilidad Estimada"**

Este documento es de uso interno. Muestra:
- Desglose de costo laboral por actividad (horas × costo por hora)
- Costo de ítems comprados/revendidos
- Resumen de rentabilidad: venta neta, costo total, margen estimado y porcentaje
- Validaciones de completitud de datos
- Advertencias detectadas

**Prerequisito:** Para que los cálculos sean correctos, los tipos de actividad usados en el alcance deben tener configurado el costo por hora en ERPNext.

---

## Cómo enviar la propuesta al cliente

**El módulo no tiene función de envío automático.** El envío al cliente es un proceso completamente manual:

1. Generar y descargar el PDF "Propuesta Comercial" desde ERPNext
2. Abrir el cliente de correo electrónico habitual (Outlook, Gmail, etc.)
3. Redactar el correo al cliente
4. Adjuntar el PDF descargado
5. Enviar

### Enviar usando el correo de ERPNext (composer de Email)

También puedes enviar la propuesta con el **Email** nativo de ERPNext (ícono de sobre / menú de la
Cotización). Para las Cotizaciones de propuesta, el módulo ajusta ese diálogo para evitar errores
comunes (sin reemplazar el comportamiento nativo):

- **Plantilla HTML automática:** si eliges —o está configurado como *Default Email Template* de la
  Cotización— un **Email Template** con *Use HTML* activado, el diálogo **marca "Use HTML"
  automáticamente** y carga el contenido en el editor HTML correcto, de modo que el diseño del correo
  no se degrada. Con una plantilla **sin** HTML, el editor normal funciona como siempre.
- **No adjunta el formato interno por error:** la casilla **"Attach Document Print" inicia
  DESMARCADA**. Así se evita adjuntar accidentalmente el formato *Standard* de la Cotización (que
  puede contener información interna). Los archivos ya adjuntos a la Cotización siguen disponibles en
  *Select Attachments*.
- **Si decides adjuntar el PDF:** al marcar "Attach Document Print", el selector queda
  **preseleccionado con el formato de propuesta** (el formato efectivo de la propuesta o, si no, el
  configurado en *Proposal Print Format*), **no** con *Standard*.
- **Tu firma se conserva:** la firma sigue proviniendo del mecanismo nativo de ERPNext (tu firma de
  usuario o la de la cuenta de correo); activar el modo HTML no la pierde.

!!! note "Requisito para el modo HTML automático"
    Para que "Use HTML" se active solo debe existir un **Email Template con *Use HTML*** y, si quieres
    que aplique desde el inicio, configurarlo como **Default Email Template** de la Cotización
    (*Personalizar formulario → Quotation → Default Email Template*). Sin una plantilla HTML, el correo
    se redacta en el editor normal.

### Sobre el estado "Enviada al Cliente"

El estado **"Enviada al Cliente"** en el workflow de aprobación interna **solo indica que alguien marcó ese estado manualmente** en el sistema. No dispara ningún correo, no abre ningún portal ni activa ninguna notificación automática.

Este estado sirve como registro interno de que la propuesta fue enviada. El envío real del documento siempre es responsabilidad del usuario.

---

## Secuencia recomendada antes de enviar

1. Completar y revisar la Cotización y la pestaña Propuesta
2. Avanzar el workflow hasta **"Aprobada"** (o al menos tener aprobación interna)
3. Generar el PDF y revisarlo visualmente
4. Marcar el workflow como **"Enviada al Cliente"** para registro interno
5. Enviar el PDF por correo manualmente al cliente
