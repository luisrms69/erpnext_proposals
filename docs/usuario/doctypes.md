# DocTypes del módulo

Los documentos del módulo se dividen en dos grupos: **catálogo** (configuración reutilizable) y **operativos** (trabajo diario por propuesta).

---

## Documentos de catálogo

Estos documentos se configuran una sola vez y se reutilizan en todas las propuestas.

### Sección de propuesta (Proposal Section)

**Propósito:** Bloque de texto reutilizable que representa una sección narrativa de la propuesta (Objetivo del Proyecto, Metodología, Exclusiones, etc.).

**Cuándo se usa:**
- Al configurar el catálogo inicial
- Cuando se quiere agregar o modificar una sección disponible para los templates

**Relación con otros documentos:**
- Las secciones se agrupan dentro de los **Templates de propuesta**
- El contenido de las secciones aparece en el PDF de Propuesta Comercial

**Catálogo incluido al instalar:**
El sistema crea 10 secciones base: Resumen Ejecutivo, Objetivo del Proyecto, Modalidad de Trabajo, Metodología, Criterios de Aceptación, Responsabilidades del Cliente, Supuestos, Exclusiones, Control de Cambios, Cierre del Proyecto.

---

### Template de propuesta (Proposal Template)

**Propósito:** Agrupa secciones narrativas en un orden definido. Representa el esquema de una propuesta para un tipo de proyecto (implementación, integración, soporte, etc.).

**Cuándo se usa:**
- Al configurar los esquemas de propuesta del negocio
- Se selecciona en cada Cotización para definir qué secciones aparecen en el PDF

**Relación con otros documentos:**
- Contiene una lista ordenada de **Secciones de propuesta**
- Se asigna a la **Cotización** en la pestaña Propuesta
- Determina las secciones narrativas del PDF "Propuesta Comercial"

**Templates incluidos al instalar:**
- Implementacion ERPNext
- Integracion API
- Bolsa de Horas Soporte

---

### Alcance (Scope Item)

**Propósito:** Registro maestro de una actividad o tarea reutilizable del catálogo de servicios. No tiene precio — describe el trabajo, el perfil y el esfuerzo estimado.

**Cuándo se usa:**
- Al construir el catálogo de servicios de la empresa
- El sistema lo consulta automáticamente al guardar una Cotización para poblar la tabla de alcance

**Relación con otros documentos:**
- Se vincula a un **Item de ERPNext** para relacionar actividad con precio
- Al guardar una Cotización, el sistema busca alcances vinculados a los Items cotizados y los copia a la tabla de alcance de la propuesta

---

## Documentos operativos

Estos documentos se generan o editan en el trabajo diario de cada propuesta.

### Cotización con propuesta (Quotation + campos Propuesta)

**Propósito:** La Cotización de ERPNext ampliada con una pestaña "Propuesta" que contiene el template, el título, el centro de costo y la tabla de alcance.

**Cuándo se usa:**
- Es el documento central de trabajo. Toda la gestión de propuesta ocurre aquí.
- El workflow de aprobación interna opera sobre este documento
- Desde aquí se genera el PDF y se crea el proyecto

**Relación con otros documentos:**
- Usa un **Template de propuesta** para definir las secciones narrativas del PDF
- Contiene una tabla de **Alcances de propuesta** (filas copiadas del catálogo)
- Al convertirse en Sales Order, propaga el centro de costo y el proyecto
- Genera un **Proyecto** al usar el botón correspondiente

**Campos adicionales que agrega el módulo:**
- Pestaña "Propuesta" con template, título, centro de costo, tabla de alcance y referencia al proyecto generado

---

### Alcance de propuesta (Quotation Scope Item)

**Propósito:** Fila de la tabla de alcance dentro de una Cotización específica. Es una copia del catálogo adaptada a esa propuesta en particular.

**Cuándo se usa:**
- Se genera automáticamente al guardar la Cotización (si hay coincidencias en el catálogo)
- Se puede agregar, editar o eliminar manualmente en la tabla de alcance de la Cotización

**Importante:** Los cambios hechos en esta tabla son independientes del catálogo. Modificar el catálogo después no afecta las propuestas ya creadas.

**Relación con otros documentos:**
- Referencia al **Alcance** del catálogo de donde fue copiado
- Genera una **Tarea** en el proyecto cuando se usa el botón "Crear Proyecto desde Propuesta"

---

## Documentos de resultado

Estos documentos son generados por el módulo como resultado del proceso.

### Proyecto (Project)

**Propósito:** El proyecto de ejecución creado automáticamente desde la propuesta aprobada.

**Cuándo se crea:**
- Cuando el usuario presiona el botón "Crear Proyecto desde Propuesta" en la Cotización Submitted

**Qué viene de la propuesta:**
- Nombre del proyecto (desde el Título de propuesta o el nombre del cliente)
- Cliente
- Centro de costo
- Tareas (una por cada alcance marcado "Incluir en propuesta")

Ver detalle en [Proyecto generado](proyecto-generado.md).
