# Campos principales

Referencia de campos por documento, en lenguaje de usuario.

---

## Cotización — pestaña Propuesta

Estos campos se agregan a la Cotización nativa de ERPNext en la pestaña "Propuesta".

| Campo | Nombre visible | Tipo | Obligatorio para workflow | Descripción |
|---|---|---|---|---|
| Template de propuesta | Template de propuesta | Lista desplegable | Sí | El esquema narrativo que define qué secciones aparecen en el PDF. Se selecciona uno de los templates configurados. |
| Título de la propuesta | Título de la propuesta | Texto libre | No | Título personalizado que aparece en la portada del PDF. Si se deja vacío, el PDF puede mostrar el folio de la cotización. |
| Centro de costo | Centro de costo | Lista desplegable | Sí | Centro de costo del proyecto. Se propaga automáticamente al Proyecto y a la Sales Order. |
| Alcance (tabla) | — | Tabla | No | Tabla de actividades del alcance técnico. Se puebla automáticamente al guardar si hay coincidencias en el catálogo. |
| Proyecto de propuesta | Proyecto | Referencia | Solo lectura | Se llena automáticamente cuando se crea el proyecto desde la propuesta. No se edita manualmente. |
| Revisado por | Revisado por | Usuario | Solo lectura | Se llena automáticamente cuando un Proposals Manager ejecuta "Aprobar" o "Rechazar". |
| Fecha de revisión | Fecha de revisión | Fecha/hora | Solo lectura | Fecha y hora en que se tomó la decisión de aprobación o rechazo. |
| Aprobado por | Aprobado por | Usuario | Solo lectura | Se llena automáticamente solo cuando se ejecuta "Aprobar". Queda vacío si la propuesta fue rechazada. |
| Fecha de aprobación | Fecha de aprobación | Fecha/hora | Solo lectura | Fecha y hora de la aprobación. Solo se llena cuando la propuesta es aprobada. |

### Cuándo llenar estos campos

- **Template de propuesta:** Al crear la propuesta, antes de guardar por primera vez. Sin él no se pueden generar los alcances automáticamente ni avanzar el workflow.
- **Título de la propuesta:** Al crear o en cualquier momento antes de generar el PDF. Recomendado para dar contexto en la portada.
- **Centro de costo:** Al crear la propuesta. Requerido para avanzar cualquier estado del workflow.

---

## Alcance de propuesta (fila en la tabla)

Cada fila de la tabla de alcance en la Cotización tiene estos campos editables.

| Campo | Nombre visible | Tipo | Descripción |
|---|---|---|---|
| Alcance | Alcance | Referencia | Actividad del catálogo. Al seleccionar, se copian automáticamente todos los demás campos de esa fila. |
| Título | Título | Texto | Nombre de la actividad. Aparece en el Plan de Trabajo del PDF. |
| Fase | Fase | Texto | Etiqueta de agrupación. Actividades con la misma fase se agrupan en el PDF. Ej: "Fase 1 — Análisis". |
| Secuencia | Secuencia | Número | Orden dentro de la fase. Números menores aparecen primero. |
| Incluir en propuesta | Incluir en propuesta | Sí/No | Controla si la actividad aparece en el PDF y si se convierte en tarea al crear el proyecto. |
| Descripción | Descripción | Texto enriquecido | Descripción del trabajo. Aparece en el PDF debajo del título de la actividad. |
| Entregable | Entregable | Texto enriquecido | Qué se entrega al completar esta actividad. Aparece en la sección de Entregables del PDF. |
| Horas estimadas | Horas estimadas | Número | Esfuerzo esperado. Usado en el cálculo de rentabilidad y en la tarea del proyecto. |
| Tipo de actividad | Tipo de actividad | Referencia | Tipo de trabajo (Desarrollo, Consultoría, etc.). Se usa para calcular el costo por hora en el reporte de rentabilidad. |
| Perfil | Perfil | Referencia | Designación o perfil del profesional que ejecuta. Aparece en el Plan de Trabajo del PDF. |

### Campos internos de costo (solo lectura, no visibles en PDF comercial)

Estos campos se llenan automáticamente al **Enviar (Submit)** la Cotización. Registran el costo que se usó para calcular la rentabilidad en el momento de aprobar la propuesta. No se muestran al cliente.

| Campo | Descripción |
|---|---|
| Tasa de costo | Costo/hora congelado al momento del submit. Viene de la Proposal Cost Matrix según el Perfil y Tipo de actividad. |
| Fuente de tasa | De dónde provino el costo: `matrix` (tasa exacta), `matrix_general` (promedio del perfil), `activity_type` (fallback legacy), `sin_datos`. |
| Costo congelado | Marcado automáticamente al submitir. Indica que la tasa ya no se recalcula aunque cambie la matriz. |
| Congelado el | Fecha y hora en que se congeló el costo. |

### Notas sobre el alcance

- Las filas generadas automáticamente están marcadas internamente como "generadas automáticamente". Se pueden editar sin restricción.
- El campo **ítem de cotización** (referencia al ítem de la cotización que originó la fila) es de solo lectura. Lo llena el sistema.
- Si se regenera el alcance usando el botón "Regenerar alcance", solo se agregan filas nuevas. Las existentes no se modifican ni se duplican.

---

## Alcance específico por servicio contratado

Cada **servicio cotizado** (fila de la tabla de ítems de la Cotización) tiene un campo
**Alcance específico** para escribir a mano qué se contrató exactamente de ese servicio en esta
propuesta (por ejemplo: número de compañías, usuarios, entregables acotados o meses de
acompañamiento). Es distinto de la descripción, la metodología o el resultado esperado, que son
genéricos y vienen del catálogo.

| Campo | Nombre visible | Tipo | Descripción |
|---|---|---|---|
| Alcance específico | Alcance específico | Texto enriquecido | Alcance concreto de la contratación de ese servicio. Se escribe a mano en la fila expandida del ítem. Opcional. |

### Cómo funciona

- **Se edita en Borrador**, abriendo la fila del servicio en la tabla de ítems. Es opcional: si un
  servicio no lo necesita, se deja vacío.
- **No viene del catálogo** y **no se pierde al "Regenerar alcance"**: lo que se escribe se conserva.
- **Se congela al Enviar (Submit)** la Cotización: a partir de ahí ya no se edita, igual que el resto
  del contenido de la propuesta.
- **Se hereda al crear una nueva versión** (desde una propuesta rechazada) y vuelve a ser editable en
  el Borrador de la nueva versión, sin cambiar la anterior.
- Si el mismo servicio aparece en dos filas, cada una puede tener su propio alcance específico.
- **En el PDF** aparece como un bloque "Alcance específico" bajo cada servicio, **solo si tiene
  contenido**; si se deja vacío, no aparece título ni espacio.

---

## Sección de propuesta (Proposal Section)

| Campo | Nombre visible | Descripción | Cuándo editar |
|---|---|---|---|
| Nombre de sección | Nombre | Identificador único. Usado para vincular la sección a los templates. | Al crear. No cambiar después si ya está en templates. |
| Tipo de sección | Tipo | Clasificación informativa (Objetivo, Metodología, etc.). No afecta comportamiento. | Al crear o cuando se reorganice el catálogo. |
| Título | Título | Texto que aparece como encabezado en el PDF. Si se deja vacío, usa el nombre de sección. | Al crear o cuando se quiera mostrar un texto diferente. |
| Activa | Activa | Si está desactivada, no aparece disponible para agregar a templates. | Cuando una sección deja de usarse pero no se quiere eliminar. |
| Contenido | Contenido | Texto de la sección con formato. Aparece en el cuerpo de la propuesta PDF. **Limitación RC:** el formato HTML puede no renderizarse correctamente en el PDF. Usar texto plano para mayor compatibilidad. | Al personalizar el contenido base al estilo del negocio. |

---

## Template de propuesta (Proposal Template)

| Campo | Nombre visible | Descripción | Cuándo editar |
|---|---|---|---|
| Nombre del template | Nombre | Identificador del template. Aparece en el selector de la Cotización. | Al crear. |
| Descripción | Descripción | Texto libre para describir para qué tipo de proyecto aplica. | Opcional, para orientar al usuario. |
| Secciones | Secciones (tabla) | Lista ordenada de secciones que incluye este template. | Al crear o cuando se quieran agregar/quitar secciones. |

### Campos de cada fila de sección en el template

| Campo | Descripción |
|---|---|
| Sección | La sección del catálogo a incluir |
| Secuencia | Orden en el PDF (se asigna automáticamente en múltiplos de 10 si se deja vacío) |
| Título personalizado | Si se quiere mostrar un título diferente al de la sección original, solo en este template |
| Usar contenido personalizado | Si está marcado, usa el contenido del campo siguiente en lugar del contenido de la sección |
| Contenido personalizado | Texto alternativo solo para este template |

---

## Alcance del catálogo (Scope Item)

| Campo | Nombre visible | Descripción | Cuándo llenar |
|---|---|---|---|
| Código | Código | Identificador único. Ej: SEI-001. | Al crear. |
| Título | Título | Nombre de la actividad. Aparece en el Plan de Trabajo del PDF. | Al crear. |
| Fase | Fase | Etiqueta de agrupación para el PDF. Ej: "Fase 1 — Análisis". | Al crear. Se puede dejar vacío. |
| Activo | Activo | Si está desactivado, no aparece disponible al agregar alcances manualmente. | Cuando una actividad deja de ofrecerse. |
| Visible en propuesta | Visible en propuesta | Controla si aparece en el PDF por defecto. | Al crear. |
| Descripción | Descripción | Descripción del trabajo. | Al crear. |
| Entregable | Entregable | Qué se entrega. | Al crear. |
| Horas estimadas | Horas estimadas | Esfuerzo típico en horas. Puede ajustarse por propuesta. | Al crear. |
| Tipo de actividad | Tipo de actividad | Categoría de trabajo para cálculo de costo. | Necesario para rentabilidad. |
| Perfil | Perfil | Designación del profesional. | Opcional, aparece en el PDF. |
| Ítem ERPNext | Ítem ERPNext | El ítem de precio en ERPNext al que corresponde este alcance. Este vínculo permite al sistema generar el alcance automáticamente cuando ese ítem aparece en una cotización. | Al crear. Requerido para generación automática. |
