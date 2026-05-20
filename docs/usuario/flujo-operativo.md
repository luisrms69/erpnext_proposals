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

La Cotización pasa por un flujo de aprobación interna con cinco estados:

```
Borrador → En Revisión → Aprobada → Enviada al Cliente
                     ↘ Rechazada → Borrador (para corregir)
```

### Estados y quién actúa

| Estado | Quién puede avanzar | Acción disponible |
|---|---|---|
| Borrador | Proposals User o Manager | Enviar a Revisión |
| En Revisión | Proposals Manager | Aprobar o Rechazar |
| Aprobada | Proposals Manager | Marcar como Enviada al Cliente |
| Rechazada | Proposals User o Manager | Revisar (regresa a Borrador) |
| Enviada al Cliente | — | Fin del workflow |

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
**Tipo:** Manual

El PDF de propuesta comercial se genera desde ERPNext usando el Print Format **"Propuesta Comercial"**.

**El envío al cliente es completamente manual:**

1. Generar el PDF desde ERPNext (imprimir o descargar)
2. Adjuntar el PDF a un correo en el cliente de correo habitual
3. Enviarlo al cliente

El estado **"Enviada al Cliente"** en el workflow **únicamente indica que alguien marcó ese estado**. No envía ningún correo, no activa ninguna notificación ni integración.

Ver instrucciones detalladas en [Generar y enviar al cliente](generar-enviar-propuesta.md).

---

## Etapa 4 — Propuesta ganada

**Quién:** Proposals Manager o quien administre la Cotización
**Tipo:** Manual

Cuando el cliente acepta la propuesta, el siguiente paso es **Enviar (Submit)** la Cotización en ERPNext. Este es el mecanismo nativo de ERPNext para marcar una cotización como cerrada/ganada.

El Submit de la Cotización es una acción separada e independiente del flujo de aprobación interna del módulo.

Después del Submit, opcionalmente se puede crear una **Sales Order** desde la Cotización siguiendo el flujo comercial nativo de ERPNext.

Ver detalle en [Propuesta ganada](propuesta-ganada.md).

---

## Etapa 5 — Creación del proyecto de ejecución

**Quién:** Proposals Manager
**Tipo:** Manual (botón) + automático (creación de tareas)

Con la Cotización en estado Submitted (enviada):

1. Usar el botón **"Crear Proyecto desde Propuesta"** que aparece en la Cotización
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
