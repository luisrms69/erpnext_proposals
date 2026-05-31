# Propuesta ganada

## Qué significa el estado "Ganada"

**Ganada** es el estado final del workflow de propuesta cuando el cliente acepta la propuesta.
Se activa con la acción **"Marcar como Ganada"** desde una propuesta en estado "Enviada al Cliente".

El estado Ganada habilita:
- El botón **"Crear Proyecto desde Propuesta"**
- El botón **"Crear → Sales Order"** (nativo ERPNext) — solo después de crear el proyecto

---

## Flujo cuando el cliente acepta

### Paso 1 — Confirmar aceptación del cliente

Cuando el cliente comunica que acepta la propuesta:

1. Abrir la Cotización en estado **Enviada al Cliente**
2. Usar el botón de workflow **"Marcar como Ganada"** (parte superior derecha)
3. La Cotización cambia al estado **Ganada**

Este paso es necesario para que aparezcan los botones de proyecto y Sales Order.

### Paso 2 — Crear el proyecto de ejecución

Con la Cotización en estado Ganada:

1. Buscar el botón **"Crear Proyecto desde Propuesta"** en la barra superior (grupo "Propuesta")
2. Confirmar en el diálogo
3. El sistema crea el Proyecto y las Tareas automáticamente
4. Al finalizar, el sistema muestra el nombre del proyecto con un enlace para abrirlo directamente

Si el botón muestra **"Ver / Actualizar Proyecto"**, significa que ya existe un proyecto vinculado.
Al presionarlo, el sistema agrega cualquier tarea nueva sin duplicar las existentes.

Ver detalle en [Proyecto generado](proyecto-generado.md).

### Paso 3 — Crear Sales Order (si el flujo comercial lo requiere)

Una vez que existe el proyecto vinculado, aparece el botón **"Crear → Sales Order"** nativo de ERPNext:

1. Usar el botón **Crear → Sales Order** en la Cotización
2. La Sales Order hereda automáticamente el proyecto y el centro de costo de la propuesta

El proyecto debe existir antes de crear la Sales Order para que la propagación funcione correctamente.

---

## Resumen de acciones al ganar una propuesta

| Paso | Acción | Tipo | Quién |
|---|---|---|---|
| 1 | Acción "Marcar como Ganada" en el workflow | Manual | Proposals Manager |
| 2 | Crear Proyecto desde Propuesta | Manual (botón) | Proposals Manager |
| 3 | Crear Sales Order (si aplica) | Manual (nativo ERPNext) | Proposals Manager o Ventas |
| 4 | Asignar equipo y fechas al proyecto | Manual | PMO / Operaciones |

---

## Qué NO ocurre automáticamente

- El sistema no cambia el estado de la propuesta al recibir aceptación del cliente — ese paso es siempre manual
- El sistema no genera notificaciones cuando el cliente acepta
- No hay integración con correo, portal de cliente ni firma digital
- La aceptación del cliente no queda registrada en el sistema — solo el cambio de estado interno

---

## Si el cliente rechaza la propuesta

Usar la acción **"Rechazar por Cliente"** desde estado "Enviada al Cliente".
La Cotización pasa a estado **Rechazada** y desde ahí se puede crear una nueva versión revisada.

Ver [Flujo operativo](flujo-operativo.md) para la ruta de versionado.
