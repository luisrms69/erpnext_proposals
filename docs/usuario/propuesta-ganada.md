# Propuesta ganada

## Qué significa "propuesta ganada"

El módulo no tiene un estado propio llamado "Ganada". El indicador de que una propuesta fue aceptada por el cliente es el **Submit (Envío) de la Cotización** en ERPNext. Este es el mecanismo nativo de ERPNext para cerrar una cotización.

El estado "Enviada al Cliente" del workflow de aprobación interna solo indica que el documento fue enviado al cliente para su revisión — no que el cliente lo haya aceptado.

---

## Flujo cuando el cliente acepta

### Paso 1 — Submit de la Cotización

Cuando el cliente confirma la aceptación de la propuesta:

1. Abrir la Cotización en ERPNext
2. Hacer clic en **Enviar** (Submit) en la barra superior

Este paso:
- Cambia el estado de la Cotización a "Submitted" (enviada/cerrada)
- Bloquea la edición de la cotización
- Habilita el botón **"Crear Proyecto desde Propuesta"** en la barra de botones

> El Submit de la Cotización es un prerequisito para poder crear el proyecto desde el módulo.

### Paso 2 — Crear Sales Order (opcional)

Si el flujo comercial del negocio requiere una Orden de Venta (Sales Order):

1. Desde la Cotización enviada, usar el botón **"Crear → Sales Order"** (nativo ERPNext)
2. La Sales Order hereda automáticamente el proyecto y el centro de costo de la propuesta

Ver nota sobre la propagación automática en [Proyecto generado](proyecto-generado.md).

La Sales Order es parte del flujo comercial nativo de ERPNext. No es un requisito del módulo para crear el proyecto — el proyecto se puede crear directamente desde la Cotización submitted.

### Paso 3 — Crear el proyecto de ejecución

Con la Cotización en estado Submitted:

1. Buscar el botón **"Crear Proyecto desde Propuesta"** en la barra superior de la Cotización (grupo "Propuesta")
2. Hacer clic en el botón
3. El sistema crea el Proyecto y las Tareas automáticamente
4. Al finalizar, el sistema muestra el nombre del proyecto y un enlace para abrirlo directamente

Ver detalle en [Proyecto generado](proyecto-generado.md).

---

## Resumen de acciones al ganar una propuesta

| Paso | Acción | Tipo | Quién |
|---|---|---|---|
| 1 | Submit de la Cotización | Manual | Proposals Manager |
| 2 | Crear Sales Order (si aplica) | Manual | Proposals Manager o Ventas |
| 3 | Crear Proyecto desde Propuesta | Manual (botón) | Proposals Manager |
| 4 | Asignar equipo al proyecto | Manual | PMO / Operaciones |

---

## Qué NO ocurre automáticamente

- El sistema no cambia ningún estado de propuesta al recibir aceptación del cliente
- El sistema no genera ninguna notificación cuando el cliente acepta
- No hay integración con correo, portal de cliente ni firma digital
- La aprobación del cliente no queda registrada en el sistema — solo el estado del workflow interno

---

## Nota sobre el workflow y el Submit

El workflow de aprobación interna (Borrador → En Revisión → Aprobada → Enviada al Cliente) y el Submit de la Cotización son dos mecanismos independientes:

- El **workflow** controla el proceso de revisión interna antes de enviar al cliente
- El **Submit** de ERPNext marca la cotización como cerrada/ganada

Se pueden hacer en cualquier orden, pero el flujo recomendado es:

```
Workflow: Aprobada → Enviada al Cliente
    ↓
Cliente acepta
    ↓
Submit de la Cotización
    ↓
Crear Proyecto desde Propuesta
```
