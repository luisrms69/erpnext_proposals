# Flujo operativo

## Resumen

El proceso completo de una propuesta tiene seis etapas:

```
Configuración → Creación → Revisión interna → PDF al cliente → Ganada → Proyecto
```

Algunas etapas ocurren automáticamente al guardar. Otras requieren acción manual del usuario.

---

## Etapa 0 — Configuración inicial

**Quién:** Administrador o Proposals Manager
**Cuándo:** Una sola vez antes de crear la primera propuesta. Se puede actualizar en cualquier momento.

El sistema instala automáticamente 10 secciones de texto base y 3 templates al instalarse por primera vez. Antes de usar el módulo en producción conviene:

1. Revisar las **Secciones de propuesta** y personalizar su contenido al tono y estilo del negocio
2. Revisar los **Templates de propuesta** existentes o crear nuevos
3. Crear el catálogo de **Alcances** con las actividades/servicios que la empresa ofrece
4. Verificar que los **Activity Types** de ERPNext tengan configurado el costo por hora — esto es necesario para que el reporte de rentabilidad calcule correctamente

Sin la configuración del catálogo de alcances, el módulo funciona pero la tabla de alcance en cada cotización quedará vacía y deberá llenarse manualmente.

---

## Etapa 1 — Creación de la propuesta

**Quién:** Proposals User o Proposals Manager
**Tipo:** Manual

### Paso 1. Crear la Cotización

Crear una Cotización normal en ERPNext con:
- El cliente
- Los servicios o productos cotizados, con cantidades y precios
- Las condiciones comerciales si aplica

### Paso 2. Completar la pestaña "Propuesta"

Con la Cotización abierta, ir a la pestaña **Propuesta** y completar:

| Campo | Descripción | Obligatorio para workflow |
|---|---|---|
| Template de propuesta | El esquema narrativo que se usará (Implementación, Integración, etc.) | Sí |
| Título de la propuesta | Nombre que aparecerá en la portada del PDF | No |
| Centro de costo | Centro de costo del proyecto | Sí |

### Paso 3. Guardar

Al guardar la Cotización, el sistema busca automáticamente en el catálogo de alcances actividades que correspondan a los ítems cotizados y las agrega a la tabla de alcance. Este proceso es silencioso: si no hay coincidencias en el catálogo, la tabla queda vacía.

### Paso 4. Revisar y ajustar el alcance

Revisar la tabla **Alcance** en la pestaña Propuesta:

- Agregar o quitar filas manualmente si es necesario
- Marcar **Incluir en propuesta** para cada actividad que debe aparecer en el PDF
- Ajustar el orden con el campo **Secuencia** si se quiere cambiar el orden en el PDF
- Modificar la descripción o el entregable de alguna actividad cuando difiere del catálogo

Los cambios hechos aquí son independientes del catálogo — no modifican el catálogo maestro.

---

## Etapa 2 — Revisión interna

**Quién:** Proposals User inicia. Proposals Manager aprueba o rechaza.
**Tipo:** Manual

La Cotización pasa por un flujo de aprobación interna con seis estados:

```
Borrador → En Revisión → Aprobada → Enviada al Cliente → Ganada
                     ↘ Rechazada          ↘ Rechazada (por cliente)
```

### Estados y quién actúa

| Estado | Editable | Quién puede avanzar | Acción disponible |
|---|---|---|---|
| Borrador | Sí | Proposals User o Manager | Enviar a Revisión |
| En Revisión | **No — congelada** | Proposals Manager | Aprobar o Rechazar |
| Aprobada | **No — congelada** | Proposals Manager | Enviar al Cliente |
| Rechazada | **No — congelada** | Proposals Manager | Crear nueva versión |
| Enviada al Cliente | **No — congelada** | Proposals Manager | Marcar como Ganada / Rechazar por Cliente |
| Ganada | **No — congelada** | — | Crear Proyecto desde Propuesta |

> **Importante:** al pasar a **En Revisión**, la Cotización queda bloqueada permanentemente (submitted). Si se rechaza, se puede crear una nueva versión con trazabilidad desde el botón "Crear nueva versión" en la propuesta rechazada.

### Condiciones para avanzar cualquier estado

Antes de procesar cualquier cambio de estado, el sistema verifica automáticamente:

- Que esté asignado un **Template de propuesta**
- Que esté asignado un **Centro de costo**
- Que el **total neto** de la cotización sea mayor a cero

Si alguna condición falla, el sistema muestra un error y bloquea el avance.

El sistema también muestra **advertencias no bloqueantes** cuando:
- Alguna actividad de alcance no tiene tipo de actividad asignado
- Algún tipo de actividad no tiene costo por hora configurado
- La moneda de la cotización es distinta a la moneda base de la empresa

Las advertencias no impiden avanzar, pero indican datos incompletos que afectarán el cálculo de rentabilidad.

---

## Etapa 3 — Generación del PDF y envío al cliente

**Quién:** Proposals User o Manager
**Tipo:** Automático al enviar a revisión + manual para envío

Al pasar a **En Revisión**, el sistema genera y adjunta automáticamente dos PDFs a la Cotización:

- **Propuesta Comercial** (público) — el documento formal para el cliente
- **Rentabilidad Estimada** (privado, solo interno) — análisis de costos y margen

Estos PDFs quedan en la sección de adjuntos de la Cotización y reflejan exactamente el contenido al momento de enviar a revisión.

**El envío al cliente sigue siendo manual:**

1. Descargar el PDF adjunto "Propuesta Comercial" desde la Cotización
2. Adjuntarlo a un correo en el cliente de correo habitual
3. Enviarlo al cliente

El estado **"Enviada al Cliente"** en el workflow **únicamente indica que alguien marcó ese estado**. No envía ningún correo, no activa ninguna notificación ni integración.

Ver instrucciones detalladas en [Generar y enviar al cliente](generar-enviar-propuesta.md).

---

## Etapa 4 — Propuesta ganada

**Quién:** Proposals Manager
**Tipo:** Acción de workflow

Cuando el cliente acepta la propuesta, el Proposals Manager ejecuta la acción **"Marcar como Ganada"** desde la Cotización en estado "Enviada al Cliente". Este paso mueve el estado al estado final **Ganada** del workflow.

Si el cliente rechaza la propuesta, usar la acción **"Rechazar por Cliente"** en su lugar. Esto permite crear una nueva versión para una propuesta revisada.

Ver detalle en [Propuesta ganada](propuesta-ganada.md).

---

## Etapa 5 — Creación del proyecto de ejecución

**Quién:** Proposals Manager
**Tipo:** Manual (botón) + automático (creación de tareas)

El botón **"Crear Proyecto desde Propuesta"** aparece solo cuando la Cotización está en estado **Ganada**.

1. Hacer clic en el botón en la barra superior de la Cotización
2. El sistema crea automáticamente un **Proyecto** con el nombre, cliente y centro de costo de la propuesta
3. Por cada actividad marcada como "Incluir en propuesta", el sistema crea una **Tarea** en el proyecto
4. El campo **"Proyecto de propuesta"** en la Cotización se llena automáticamente

El proyecto queda listo para que el equipo de ejecución registre avance.

Ver detalle en [Proyecto generado](proyecto-generado.md).

---

## Resumen automático vs manual

| Acción | Tipo |
|---|---|
| Agregar alcances al guardar la cotización | **Automático** |
| Validar condiciones antes de cambiar estado | **Automático** |
| Propagar centro de costo y proyecto a Sales Order | **Automático** |
| Crear tareas al crear el proyecto | **Automático** |
| Completar pestaña Propuesta | Manual |
| Ajustar tabla de alcance | Manual |
| Avanzar estados del workflow | Manual |
| Generar y descargar el PDF | Manual |
| Enviar el PDF al cliente por correo | Manual |
| Submit de la Cotización | Manual |
| Crear Sales Order | Manual (nativo ERPNext) |
| Crear Proyecto desde Propuesta | Manual (botón) |
