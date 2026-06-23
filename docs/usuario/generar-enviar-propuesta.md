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
