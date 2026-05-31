# Proyecto generado desde la propuesta

## Cómo se crea el proyecto

El proyecto de ejecución se crea usando el botón **"Crear Proyecto desde Propuesta"** que aparece en la Cotización en estado **Ganada**.

El botón está disponible en la barra superior de la Cotización, en el grupo "Propuesta".

**Condiciones para que el botón aparezca:**
- La Cotización debe estar en estado **Ganada** (workflow)
- La Cotización debe estar en docstatus Submitted (ocurre automáticamente al pasar a En Revisión)
- La Cotización debe tener un Template de propuesta asignado
- Debe haber al menos un alcance marcado como "Incluir en propuesta"

Si ya existe un proyecto vinculado, el botón cambia de label a **"Ver / Actualizar Proyecto"**.

Al presionar el botón, el sistema crea el proyecto y las tareas automáticamente y muestra un mensaje con el nombre del proyecto y un enlace para abrirlo.

---

## Qué datos pasan de la propuesta al proyecto

### Datos del Proyecto

| Dato en el Proyecto | Origen en la propuesta |
|---|---|
| Nombre del proyecto | Título de la propuesta. Si no hay título, usa "Proyecto — {nombre del cliente}" |
| Cliente | Cliente de la Cotización |
| Centro de costo | Campo "Centro de costo" de la pestaña Propuesta |
| Estado | Se crea en estado "Abierto" (Open) |

### Tareas creadas

Por cada fila de alcance marcada como **"Incluir en propuesta"**, se crea una Tarea en el proyecto con:

| Campo de la Tarea | Origen |
|---|---|
| Asunto | "{Fase} — {Título de la actividad}" (si hay fase) o solo el título |
| Descripción | Descripción de la actividad + Entregable + Tipo de actividad + Perfil (combinados) |
| Tiempo esperado | Horas estimadas de la actividad |
| Estado | Open |

Las tareas se crean en el mismo orden que aparecen en la tabla de alcance (por fase → secuencia → posición).

---

## Qué NO pasa al proyecto

| Dato | Por qué no pasa |
|---|---|
| Precios e importes de la cotización | El proyecto no es un documento comercial |
| Ítems de la cotización | Los ítems son de la cotización, no del plan de trabajo |
| Condiciones comerciales | Son parte del acuerdo comercial, no de la ejecución |
| Secciones narrativas del template | Son para el PDF comercial, no para la ejecución |
| Estado del workflow (Aprobada, etc.) | El workflow es de revisión interna, no de ejecución |
| Asignación de personas a tareas | Debe hacerse manualmente después de crear el proyecto |
| Fechas de inicio/fin de tareas | Deben asignarse manualmente según la planificación |
| Presupuesto del proyecto | Debe configurarse manualmente en el proyecto si aplica |

---

## Qué debe completar PMO/Operaciones después de crear el proyecto

El proyecto queda con la estructura base lista, pero antes de que el equipo comience a trabajar, Operaciones o el PM debe:

- [ ] Asignar fechas de inicio y fin al proyecto
- [ ] Asignar fechas por tarea
- [ ] Asignar responsables a cada tarea
- [ ] Revisar y ajustar las horas estimadas si difieren de las negociadas
- [ ] Configurar el presupuesto del proyecto si el negocio lo requiere
- [ ] Verificar que el centro de costo sea el correcto
- [ ] Activar el seguimiento de tiempo si el equipo registrará horas

---

## Comportamiento cuando se ejecuta dos veces

Si el botón "Crear Proyecto desde Propuesta" se presiona cuando ya existe un proyecto:

- El sistema **reutiliza el proyecto existente** — no crea uno nuevo
- Solo agrega tareas que no existan todavía (combinaciones nuevas de ítem + actividad)
- No modifica ni elimina tareas existentes

Esto permite usar el botón más de una vez si se agregan actividades a la propuesta después de crear el proyecto inicial.

---

## Vínculo entre propuesta y proyecto

Después de crear el proyecto:

- El campo **"Proyecto de propuesta"** en la Cotización se llena automáticamente con el nombre del proyecto
- Desde ese campo se puede abrir el proyecto directamente con un clic
- Si se crea una Sales Order desde la Cotización, hereda automáticamente el proyecto y el centro de costo

---

## Sales Order y el proyecto

El proyecto se crea siempre desde la **Cotización** — no desde la Sales Order.

Cuando se crea una Sales Order a partir de la Cotización, ERPNext propaga automáticamente
el proyecto y el centro de costo al nuevo documento. El campo `Proyecto` de la Sales Order
queda vinculado al mismo proyecto creado desde la propuesta.
