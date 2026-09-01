# Scope Items reutilizables entre Items

Un mismo **Scope Item** (actividad del catálogo de alcances) puede pertenecer a **varios Items** de
ERPNext. Antes cada Scope Item se ligaba a un único Item; ahora la relación es **N:M**: un Item puede
tener muchos Scope Items y un Scope Item puede aplicar a muchos Items.

La relación se **administra de forma natural desde el Item** (botón *Scope Items*) y se **almacena** en
el propio Scope Item (tabla *ERPNext Items*).

---

## Administrar Scope Items desde un Item

En el formulario de un **Item ya guardado** aparece, directamente en la barra de acciones, el botón
**Scope Items**.

1. Abre el Item y pulsa **Scope Items**.
2. El diálogo muestra los Scope Items actualmente asociados a ese Item.
3. Para **agregar**: elige un Scope Item existente (solo se ofrecen los **habilitados**). El mismo no
   puede quedar duplicado.
4. Para **quitar**: usa *Quitar* junto al Scope Item.
5. Pulsa **Guardar**.

El diálogo solo **selecciona** Scope Items existentes: no crea Scope Items ni edita su fase, horas,
tipo de actividad, designación ni secuencia (eso vive en el Scope Item maestro).

**Aislamiento por Item:** al quitar un Scope Item desde un Item, solo se elimina la relación con **ese**
Item; las relaciones de ese Scope Item con **otros** Items permanecen intactas. Ejemplo: si un Scope
Item está asociado a `ITEM-1` e `ITEM-2` y lo quitas desde `ITEM-1`, sigue asociado a `ITEM-2`.

---

## La relación en el Scope Item

En el **Scope Item** existe la tabla **ERPNext Items**: cada fila es un Item al que aplica ese Scope
Item. Es la vista administrativa inversa de lo que editas desde el Item; el botón del Item es la vía
principal de trabajo.

> El campo antiguo **ERPNext Item** (un solo Item) se conserva por compatibilidad. Sigue funcionando en
> lectura, pero la relación vigente es la tabla **ERPNext Items**.

---

## Cómo se refleja en la Cotización (alcance)

Al armar una propuesta, el alcance se genera a partir de los Scope Items asociados a los Items cotizados:

- **Al agregar un Item nuevo** a la Cotización y guardar, se copian a la tabla de alcance los Scope
  Items asociados a ese Item.
- **Un guardado normal no repuebla el alcance.** Si eliminas una fila de alcance y guardas, esa fila
  **no reaparece**; editar precio/cantidad/otros datos tampoco vuelve a agregar filas. Después de la
  captura inicial, la tabla de alcance es de la propuesta.
- Para **recuperar** Scope Items faltantes, usa el botón **Agregar Scope Items desde Items** (grupo
  *Propuesta*, solo en Borrador): revisa todos los Items de la Cotización y agrega únicamente las
  combinaciones faltantes, sin duplicar y sin eliminar nada.
- **Sincronizar alcance desde catálogo** (solo Borrador) actualiza el contenido de las filas existentes
  y elimina las que ya no tienen respaldo, pero **no vuelve a agregar** filas eliminadas. Reponer
  faltantes es exclusivamente la acción manual *Agregar Scope Items desde Items*.
