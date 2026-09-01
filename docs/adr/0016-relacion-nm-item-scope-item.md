# ADR-0016: Relación N:M Item ↔ Scope Item

**Fecha:** 2026-09-01
**Status:** Cerrado — implementado (rama `feat/loader-manage-scope-enabled`; feature en commit `106578b`)
**Rama:** feat/loader-manage-scope-enabled → version-16

---

## Contexto

`Scope Item` se ligaba a ERPNext mediante un único Link `erpnext_item` (un Scope Item → un Item). La
generación de alcance en la Quotation copiaba, por cada línea de Item, los Scope Items cuyo
`erpnext_item` coincidía.

Ese modelo 1:1 no soporta el caso real: un mismo servicio (Item) agrupa **muchas** actividades del
catálogo, y una misma actividad puede aplicar a **varios** servicios. Con un solo Link había que
elegir un único Item por Scope Item, forzando duplicar Scope Items o partir artificialmente el
catálogo. El caso que lo detonó (un Item de PMO que debía arrastrar 21 Scope Items, repartidos además
entre variantes del servicio) no era expresable.

---

## Decisión

- **Relación N:M** entre `Item` y `Scope Item` mediante child table **`Scope Item.erpnext_items`**
  (DocType `Scope Item ERPNext Item`, con un único campo `item` Link → `Item`). Un Scope Item puede
  listar varios Items; un Item puede aparecer en varios Scope Items.
- **Resolver central único** `utils/scope_item_links.py:resolve_scope_items_for_item(item)`: une la
  child table nueva **con** el Link legacy `erpnext_item`, deduplica y (opcional) filtra `enabled=1`.
  **Todo el app resuelve la relación por aquí** — no se repiten consultas child/legacy en otros
  archivos (generación de alcance, resync, acción manual).
- **Administración desde el Item:** botón *Scope Items* en el formulario Item →
  `get_scope_items_for_item` / `set_scope_items_for_item` (whitelisted). El diálogo solo **selecciona**
  Scope Items **habilitados**, no los crea ni edita su contenido. Al quitar un Scope Item desde un
  Item se afecta **solo** la relación con ese Item (aislamiento); las relaciones con otros Items
  quedan intactas.
- **Soporte en el loader de catálogos:** `catalog_loader.py` acepta `"erpnext_items": [...]` por Scope
  Item (lista de Item codes). Clave **ausente** = no toca; **presente** = sincroniza el set exacto;
  **vacía** = limpia. Valida duplicados dentro del set y reporta Items inexistentes en `pending`.
- **Migración solo de lectura, sin backfill ni patch:** el Link legacy `erpnext_item` se conserva y
  sigue siendo válido en lectura vía el resolver. No se migran datos históricos a la child table; las
  relaciones legacy y nuevas conviven indefinidamente.

---

## Consecuencias

- La generación de alcance ahora resuelve por el union child+legacy, de modo que un Item ya asociado
  por cualquiera de las dos vías arrastra sus Scope Items.
- Consumidores que resuelven la relación: generación de alcance (solo líneas de Item nuevas), acción
  manual *Agregar Scope Items desde Items* y el diálogo del formulario Item. El resync **no** usa la
  relación para agregar (ver ADR-0003 y su ajuste: resync ya no agrega).
- **Despliegue:** requiere `bench migrate` (crea el DocType child y el campo Table). No requiere patch
  ni recarga de Print Formats. Los Scope Items con `erpnext_item` legacy siguen funcionando sin
  intervención.
- El catálogo privado puede expresar la relación por set con `"erpnext_items"`, lo que permite dividir
  un servicio en variantes y asignar cada bloque de Scope Items a su Item correspondiente sin duplicar
  actividades.

---

## Alternativas descartadas

- **Mantener el Link 1:1 y duplicar Scope Items** por cada Item: descartado — infla el catálogo,
  desincroniza contenido idéntico y no expresa "una actividad en varios servicios".
- **Backfill/patch del legacy a la child table:** descartado — el resolver que une ambas fuentes hace
  innecesaria la migración; evita un patch de datos y mantiene compatibilidad de lectura indefinida
  (mismo criterio de corte que ADR-0004).
- **Reemplazar `erpnext_item` por la child table (corte duro):** descartado — rompería catálogos y
  datos existentes que usan el Link; se prefiere conservación en lectura.

---

## Fuera de alcance

- Cambios en costos, workflow, templates, Project o Rentabilidad Estimada.
- Gestión de `enabled` del Scope Item desde el loader (el loader no administra `enabled`).
- Reponer filas de alcance en el resync (sigue siendo *update + remove*; reponer es la acción manual).
