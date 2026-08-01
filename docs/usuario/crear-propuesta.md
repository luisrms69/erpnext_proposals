# Cómo crear una propuesta

## Prerequisitos

Antes de crear la primera propuesta, verificar que existan:

- Al menos un **Template de propuesta** configurado
- El **Centro de costo** del proyecto disponible en ERPNext
- Opcionalmente, el catálogo de **Alcances** con actividades vinculadas a ítems

Si el catálogo no está configurado, la propuesta se puede crear igualmente, pero la tabla de alcance quedará vacía y deberá llenarse manualmente.

---

## Paso 1 — Crear la Cotización base

1. Ir a **ERPNext Proposals** en el menú principal (ícono en el Desk) o navegar a Cotizaciones
2. Crear una nueva **Cotización**
3. Completar los campos estándar de la cotización:
   - Cliente
   - Fecha de vigencia
   - Ítems/servicios cotizados con cantidades y precios
   - Condiciones comerciales si aplica

No guardar todavía.

---

## Paso 2 — Completar la pestaña Propuesta

Con la Cotización abierta, hacer clic en la pestaña **"Propuesta"**.

### Campos a completar

**Template de propuesta** *(requerido para workflow)*

Seleccionar el template que corresponde al tipo de proyecto. Determina qué secciones narrativas aparecerán en el PDF.

- Implementacion ERPNext — para proyectos de configuración o implementación
- Integracion API — para desarrollos de integración o conectores
- Bolsa de Horas Soporte — para contratos de soporte o asesoría
- O cualquier template personalizado que se haya creado

**Título de la propuesta** *(recomendado)*

Texto que aparece en la portada del PDF como título principal de la propuesta. Ejemplos:
- "Propuesta de Implementación — Módulo de Manufactura"
- "Propuesta de Integración SAT — eCommerce"

Si se deja vacío, el PDF puede mostrar el folio de la cotización como referencia.

**Centro de costo** *(requerido para workflow)*

Seleccionar el centro de costo al que se asignará el proyecto. Este dato se propaga automáticamente al Proyecto y a la Sales Order.

**Grupo de propuesta** *(requerido)*

Identificador que agrupa las versiones de una misma propuesta (normalmente el ID del deal en tu CRM).

- **Autocompletado desde Frappe CRM:** cuando la Cotización se crea desde **Frappe CRM** y el campo **Frappe CRM Deal** tiene valor, **Grupo de propuesta** se completa **automáticamente** con ese mismo valor al crear la Cotización.
- Si ya capturaste un **Grupo de propuesta** manualmente, **no se sobrescribe**.
- La automatización aplica al **crear** la Cotización. Un respaldo del lado servidor cubre además la creación por **API e integraciones** (no solo desde el formulario).

---

## Paso 3 — Guardar

Hacer clic en **Guardar**.

Al guardar, el sistema:

1. Busca en el catálogo de alcances las actividades vinculadas a los ítems cotizados
2. Agrega automáticamente las filas encontradas a la tabla de alcance
3. Marca cada fila como "generada automáticamente"

Si no hay coincidencias en el catálogo (porque los ítems no tienen alcances vinculados), la tabla queda vacía. Esto es normal si el catálogo no está configurado todavía.

---

## Paso 4 — Revisar y ajustar el alcance

Después de guardar, revisar la tabla **Alcance** en la pestaña Propuesta.

### Qué revisar

- **Filas generadas:** Confirmar que corresponden al trabajo real de la propuesta
- **Incluir en propuesta:** Marcar o desmarcar según qué actividades deben aparecer en el PDF
- **Fase y secuencia:** Ajustar el orden y agrupación si es necesario
- **Horas estimadas:** Verificar o ajustar las horas por actividad para el cálculo de rentabilidad

### Cómo agregar actividades manualmente

Si la tabla quedó vacía o falta alguna actividad:

1. En la tabla de Alcance, hacer clic en **Agregar fila**
2. En el campo **Alcance**, buscar y seleccionar una actividad del catálogo
3. El sistema copia automáticamente todos los datos de esa actividad
4. Ajustar los campos que difieran para esta propuesta específica

### Cómo editar una fila existente

Hacer clic en la fila para expandirla. Todos los campos son editables directamente en la tabla.

Los cambios hechos aquí son propios de esta propuesta y no modifican el catálogo maestro.

### Cómo usar el botón "Regenerar alcance"

El botón **"Regenerar alcance"** reaparece en la Cotización guardada (en la barra de botones superior, grupo Propuesta).

Al presionarlo:
- El sistema vuelve a buscar alcances en el catálogo para los ítems cotizados
- Solo agrega filas que no existan ya en la tabla
- No modifica ni elimina filas existentes
- Pide confirmación antes de ejecutar

Útil cuando se agregan ítems a la cotización después del primer guardado.

---

## Validaciones que puede encontrar

### Al avanzar el workflow (no al guardar)

Los siguientes errores aparecen al intentar cambiar el estado del workflow, no al guardar la cotización:

| Error | Causa | Solución |
|---|---|---|
| "No se puede avanzar: falta template de propuesta" | El campo Template de propuesta está vacío | Asignar un template en la pestaña Propuesta |
| "No se puede avanzar: falta centro de costo" | El campo Centro de costo está vacío | Asignar un centro de costo en la pestaña Propuesta |
| "No se puede avanzar: total neto es cero" | La cotización no tiene ítems o tienen precio 0 | Revisar y completar los ítems cotizados |

### Advertencias (no bloquean)

Al avanzar el workflow también pueden aparecer advertencias que no bloquean el avance:

| Advertencia | Qué significa |
|---|---|
| Actividades sin tipo de actividad | Algunas filas de alcance no tienen "Tipo de actividad" asignado. El cálculo de rentabilidad estará incompleto. |
| Tipos de actividad sin costo por hora | Los tipos de actividad usados no tienen configurado el costo por hora en ERPNext. |
| Moneda diferente a moneda base | La cotización está en una moneda distinta a la configurada en la empresa. El cálculo de rentabilidad puede tener inconsistencias. |

---

## Qué verificar antes de enviar a revisión

- [ ] Template de propuesta asignado
- [ ] Título de propuesta escrito (recomendado)
- [ ] Centro de costo asignado
- [ ] Total neto mayor a cero
- [ ] Tabla de alcance revisada y ajustada
- [ ] Actividades marcadas como "Incluir en propuesta" correctamente
- [ ] Horas estimadas completas (para rentabilidad)
- [ ] Tipos de actividad asignados a cada fila de alcance (para rentabilidad)
