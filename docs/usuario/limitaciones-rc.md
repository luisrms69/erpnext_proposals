# Limitaciones del release candidate

Este documento lista las limitaciones conocidas del RC actual. Se actualiza con cada release.

---

## Errores conocidos

Problemas confirmados en el código que producen comportamiento incorrecto.

El renderizado HTML de Proposal Sections está resuelto. El sistema detecta automáticamente si el contenido es HTML/WYSIWYG o texto plano/Markdown y lo procesa correctamente. No hay errores conocidos activos.

---

## Limitaciones funcionales

Características que no están implementadas en el RC actual, aunque podrían esperarse.

### 1. Sin envío automático al cliente

El módulo no tiene integración con correo electrónico ni portal de cliente. El estado "Enviada al Cliente" en el workflow solo cambia el estado interno del sistema — no envía ningún correo ni notificación automática. El envío del PDF al cliente es siempre manual.

### 2. Sin firma digital o registro de aceptación del cliente

No existe mecanismo para registrar la aceptación formal del cliente dentro del sistema. El bloque de firmas en el PDF es solo un espacio visual para imprimir y firmar físicamente.

### 3. Sin correcciones post-rechazo en la misma Cotización

Si una propuesta es rechazada, no es posible regresarla a Borrador para edición en el mismo documento. Usar el botón **"Crear nueva versión"** desde la propuesta Rechazada — crea una nueva Cotización vinculada con trazabilidad completa.

### 5. Sin post-mortem de rentabilidad estimado vs real

El reporte de rentabilidad calcula el margen **estimado** al momento de cotizar. No existe todavía el mecanismo para comparar ese estimado contra los costos reales de ejecución (horas registradas en Timesheets, facturas reales de proveedores). Esta funcionalidad está identificada como trabajo futuro.

### 6. Sin integración con portal de clientes

No hay acceso del cliente al sistema para revisar o aprobar propuestas en línea.

### 7. El alcance no se re-sincroniza al editar el catálogo (Issue #27)

La tabla de alcance de una Cotización es una **copia congelada** del catálogo `Scope Item` al
momento de generarse. Editar un Scope Item del catálogo (horas, título, fase, perfil) **no
actualiza** las cotizaciones que ya lo copiaron — ni siquiera si siguen en **Borrador**.

El botón **"Regenerar alcance"** **solo agrega** combinaciones nuevas; **no actualiza** filas
existentes ni **elimina** las de un Scope Item deshabilitado o borrado. Su nombre no refleja
este comportamiento.

**Cómo refrescar el alcance con los valores actuales del catálogo (en Borrador):**
borrar todas las filas de la tabla de alcance y **Guardar** — al guardar se regeneran desde
cero con los datos vigentes del catálogo.

> El congelamiento definitivo ocurre al pasar a *En Revisión*; a partir de ahí el alcance es
> inmutable por diseño. Mejorar el comportamiento en Borrador está registrado en el Issue #27.

---

## Pasos manuales

Acciones que el sistema no automatiza y que el usuario debe hacer manualmente en cada propuesta.

| Paso | Motivo |
|---|---|
| Completar la pestaña Propuesta (template, título, centro de costo) | El usuario define estos datos por propuesta |
| Revisar y ajustar la tabla de alcance después del guardado | La generación automática puede no cubrir todos los alcances; para refrescar tras editar el catálogo, borrar filas + Guardar (ver Limitación 7) |
| Avanzar cada estado del workflow | El workflow requiere decisión humana en cada paso |
| Descargar y enviar el PDF al cliente por correo | No hay integración de envío automático |
| Submit de la Cotización cuando el cliente acepta | Acción nativa de ERPNext que requiere decisión del usuario |
| Crear el Proyecto desde la Cotización | Requiere confirmación manual antes de crear |
| Asignar fechas, responsables y presupuesto al proyecto | El sistema crea la estructura, el PM completa la planificación |
| Asignar equipo a las tareas del proyecto | El sistema crea las tareas, el PM asigna responsables |

---

## Prerequisitos de configuración

Condiciones que deben estar configuradas en el sistema para que ciertas funcionalidades operen correctamente.

| Requisito | Qué falla si no está | Dónde configurar |
|---|---|---|
| Activity Types con costo por hora | Fallback del reporte de Rentabilidad si no hay datos en la matriz. | ERPNext → Activity Type → campo "Costing Rate" |
| Employees con Designation asignada | La Proposal Cost Matrix no puede derivar costos. El reporte muestra la matriz vacía. | HR → Employee → campo "Designation" |
| Activity Cost configurado por empleado | Sin esto la matriz usa fuentes de menor prioridad (Timesheets o Salary). | Projects → Activity Cost → New |
| Ejecutar "Recalcular Costos" al menos una vez | La Proposal Cost Matrix queda vacía hasta el primer rebuild. | Workspace → Reportes → Costos estimados por Designation |
| Scope Items vinculados a ERPNext Items | La generación automática de alcances al guardar la cotización no produce resultados. La tabla queda vacía. | Módulo → Alcance → campo "Ítem ERPNext" |
| Centro de costo existente | El campo Centro de costo en la pestaña Propuesta no tiene opciones disponibles. | ERPNext → Plan de Cuentas → Cost Center |
| Proposal Templates configurados | No hay opciones en el selector de template de la Cotización. El PDF queda sin secciones narrativas. | Módulo → Template de propuesta |

---

## Supuestos operativos

Condiciones que el módulo asume sin verificarlas explícitamente.

- La Cotización tiene al menos un ítem con precio antes de avanzar el workflow. El sistema verifica que el total neto sea > 0, pero no verifica que los ítems estén completos en otros sentidos.
- Los Scope Items del catálogo están correctamente vinculados a ítems de ERPNext para que la generación automática funcione. Si la vinculación es incorrecta, el alcance generado puede ser incompleto sin que el sistema lo indique.
- La moneda de la cotización coincide con la moneda configurada en la empresa. El sistema advierte cuando no coinciden, pero el reporte de rentabilidad puede tener cálculos inconsistentes si hay diferencia de divisas.
- ERPNext tiene configurados correctamente Company, Chart of Accounts y Activity Types antes de usar el módulo.

---

## Pendientes confirmados para versión siguiente

| Prioridad | Ítem | Notas |
|---|---|---|
| 1 | **Post-mortem de rentabilidad** | Comparar costos estimados de la propuesta vs costos reales de ejecución (Timesheets, facturas). |
| 2 | **Integración con CRM** | Auto-populate `proposal_group` desde Frappe CRM Opportunity. Ver Issue #17. |

Los siguientes ítems **no se implementarán:**
- Margen mínimo configurable como condición de aprobación — descartado
