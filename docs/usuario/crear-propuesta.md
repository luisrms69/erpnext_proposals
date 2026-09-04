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

**Secciones opcionales** *(opcional)*

Algunos templates incluyen **secciones opcionales** que **no** aparecen por defecto y se activan solo
cuando corresponde a esa propuesta (por ejemplo, una cláusula que indica que la nueva propuesta
sustituye acuerdos o contratos anteriores). El campo **Secciones opcionales** deja elegir cuáles de
esas secciones incluir en **esta** cotización:

- Solo tienen efecto las secciones que el template define como opcionales; elegir otra no la agrega.
- Las secciones normales del template siempre aparecen — este selector **no** las quita.
- Se puede ajustar solo en **Borrador**. Al pasar la propuesta a **En Revisión**, la selección queda
  **congelada** dentro de la cotización: cambiarla después ya no afecta el PDF emitido.
- Si ya iniciaste el Borrador y cambias la selección, usa **"Sincronizar alcance desde catálogo"** para
  que se refleje en el contenido congelado.

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

1. Busca en el catálogo de alcances las actividades vinculadas a los ítems cotizados (relación Item ↔
   Scope Item; ver [Scope Items reutilizables](scope-items-reutilizables.md))
2. Agrega las filas encontradas a la tabla de alcance **solo para los ítems nuevos** (los que no
   estaban en el guardado anterior)
3. Marca cada fila como "generada automáticamente"

**Importante:** un guardado normal **no repuebla** el alcance. Si eliminas una fila y guardas, **no
reaparece**; editar precio/cantidad tampoco vuelve a agregar filas. Solo una **fila de ítem nueva** genera su
alcance al guardar. Para recuperar faltantes existe una acción manual explícita (ver abajo).

**Ítems repetidos:** el alcance se genera **por cada fila** de la cotización, no por código de ítem. Si el
mismo ítem aparece en **dos filas** distintas, cada fila genera sus propias actividades de alcance (y, al
crear el Proyecto, sus propias Tasks); las dependencias entre actividades se mantienen dentro de cada
ocurrencia. La **cantidad** de una fila **no** multiplica el alcance (una fila con `qty=5` genera una
actividad de cada tipo, no cinco). Repetir el mismo ítem en varias filas requiere habilitar en ERPNext
*Configuración de ventas → Permitir agregar el ítem varias veces en una transacción*.

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

### Botones de alcance (grupo Propuesta, solo en Borrador)

En la Cotización guardada, en la barra de botones superior (grupo **Propuesta**), hay dos acciones
distintas que operan sobre el alcance. Ambas solo están disponibles en estado **Borrador**.

**Agregar Scope Items desde Items** — recupera faltantes:
- Revisa todos los Items de la Cotización y agrega a la tabla de alcance las combinaciones que falten
- No duplica filas existentes ni elimina nada
- Útil cuando se agregaron ítems después del primer guardado, o para reponer filas eliminadas por error

**Sincronizar alcance desde catálogo** — refresca contenido:
- Actualiza el contenido de las filas existentes contra el catálogo maestro (título, horas, etc.)
- Elimina filas cuyo Scope Item ya no tiene respaldo en el catálogo
- **No vuelve a agregar** filas eliminadas — reponer faltantes es exclusivamente *Agregar Scope Items
  desde Items*

Ver [Scope Items reutilizables](scope-items-reutilizables.md) para el detalle de la relación Item ↔
Scope Item que alimenta estas acciones.

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
