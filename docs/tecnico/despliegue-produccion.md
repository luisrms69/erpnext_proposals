# Despliegue a producción — ERPNext Proposals

Metodología para instalar y configurar la app en un site nuevo (staging primero, luego producción).
Todos los comandos se corren desde el **bench root** del servidor destino, reemplazando `<site>`
por el nombre real del site.

> **Regla del ecosistema:** los servidores de producción se operan según el procedimiento del MSP.
> Esta guía describe **qué** debe quedar configurado y **cómo verificarlo**, no sustituye el control
> de cambios de infraestructura.

---

## Resumen de orden

1. Verificar dependencias (ERPNext + HRMS)
2. Instalar la app (`install-app`)
3. Aplicar fixtures y esquema (`migrate`)
4. Compilar assets (`build`)
5. Cargar los Print Formats
6. Configurar PDF generator de los Print Formats
7. Habilitar scheduler
8. Asignar roles a usuarios reales
9. Verificación final

---

## 1. Dependencias (bloqueantes)

| App | Requisito |
|---|---|
| `erpnext` | **Requerida** (`required_apps`) — la app no instala sin ella |
| `hrms` | **Requerida** (`required_apps`) — fuente salarial de la matriz de costos / Rentabilidad Estimada |

```bash
bench --site <site> list-apps
# Deben aparecer: frappe, erpnext, hrms
# Si falta hrms:
bench --site <site> install-app hrms
```

---

## 2. Instalar la app

```bash
bench --site <site> install-app erpnext_proposals
```

En la **primera instalación**, el hook `after_install`:

- Crea el **catálogo base**: 10 Proposal Sections + 3 Proposal Templates (no se sobreescribe en migrate).
- Sincroniza el **Desktop Icon** de la app automáticamente (no requiere `sync-desktop-icons` manual).

---

## 3. Aplicar fixtures y esquema

```bash
bench --site <site> migrate
```

`migrate` aplica:

- Custom Fields en Quotation (pestaña Propuesta)
- Roles `Proposals Manager`, `Proposals User`
- Workflow "Propuesta Comercial" + Workflow States
- Workspace Sidebar (incluye el item **Inicio** que aterriza en el Workspace de tarjetas)
- **Print Formats** del módulo (ver paso 5)

> `migrate` **escribe en la base de datos** del site. Es el paso obligatorio del flujo Frappe
> (código → migrate → export-fixtures) y debe correrlo el operador del site.

---

## 4. Compilar assets

```bash
bench build --app erpnext_proposals
```

Compila los client scripts (`quotation.js`, `sales_order.js`). `install-app` no siempre los deja construidos.

---

## 5. Cargar los Print Formats

Los Print Formats **no son archivos que se suban por separado**. Su fuente vive **dentro del código
de la app** ya desplegada:

```
apps/erpnext_proposals/erpnext_proposals/print_format/propuesta_comercial/propuesta_comercial.json
apps/erpnext_proposals/erpnext_proposals/print_format/rentabilidad_estimada/rentabilidad_estimada.json
```

Frappe los convierte en registros `Print Format` en la BD del site durante `bench migrate`.
No son archivos que el usuario navegue: aparecen en el **selector de impresión** de la Quotation.

**Verificar que quedaron cargados:**

```bash
bench --site <site> execute frappe.client.get_list \
  --kwargs "{'doctype':'Print Format','filters':{'module':'ERPNext Proposals'},'fields':['name','disabled']}"
```

- Si devuelve `Propuesta Comercial` y `Rentabilidad Estimada` → cargados.
- Si devuelve `[]` → forzar la carga:

```bash
bench --site <site> execute "frappe.reload_doc('ERPNext Proposals','Print Format','Propuesta Comercial', force=True)"
bench --site <site> execute "frappe.reload_doc('ERPNext Proposals','Print Format','Rentabilidad Estimada', force=True)"
```

**En la UI** se encuentran en: barra de búsqueda → "Print Format" → lista; o al abrir una Quotation →
**Imprimir** → selector de formato.

---

## 6. PDF generator de los Print Formats

Cada Print Format tiene un campo **`pdf_generator`** (`wkhtmltopdf` o `chrome`). Si no está
seleccionado, el site usa su generador por defecto, que puede no renderizar correctamente el formato.

Verificar / definir el generador antes de validar visualmente el PDF en el site destino.

> **Pendiente conocido:** a la fecha de este documento, el `pdf_generator` de los Print Formats de la
> app no viene fijado en el JSON. Confirmar el generador correcto en cada site hasta que quede definido
> en el código.

---

## 7. Scheduler

La app tiene un job diario (`rebuild_cost_matrix`). El scheduler debe estar habilitado:

```bash
bench --site <site> scheduler enable
bench --site <site> clear-cache
```

---

## 8. Asignar roles (manual, en la UI)

Los fixtures **crean** los roles `Proposals Manager` y `Proposals User`, pero **no los asignan**.
Asignarlos a los usuarios reales desde **User** en la UI.

---

## 9. Verificación final

```bash
# Custom fields presentes en Quotation
bench --site <site> execute frappe.client.get_list \
  --kwargs "{'doctype':'Custom Field','filters':{'dt':'Quotation','fieldname':['like','proposal_%']},'fields':['fieldname'],'limit_page_length':0}"

# Catálogo base (solo si fue install nuevo)
bench --site <site> execute "frappe.db.count" --kwargs "{'doctype':'Proposal Section'}"
bench --site <site> execute "frappe.db.count" --kwargs "{'doctype':'Proposal Template'}"

# Workflow activo
bench --site <site> execute frappe.client.get_value \
  --kwargs "{'doctype':'Workflow','filters':{'name':'Propuesta Comercial'},'fieldname':'is_active'}"
```

Validación visual en la UI:

- El **Desktop Icon** abre el Workspace de tarjetas (no salta directo a Quotation).
- El selector de **Imprimir** en Quotation muestra los dos formatos.
- El PDF de **Propuesta Comercial** se genera y renderiza correctamente.

---

## Checklist de despliegue

- [ ] `erpnext` y `hrms` instalados en el site
- [ ] `install-app erpnext_proposals` ejecutado (catálogo base + desktop icon)
- [ ] `migrate` limpio
- [ ] `build --app erpnext_proposals` ejecutado
- [ ] Print Formats verificados / cargados
- [ ] `pdf_generator` definido en cada Print Format
- [ ] Scheduler habilitado
- [ ] Roles asignados a usuarios reales
- [ ] Verificación visual del Desktop Icon y del PDF
