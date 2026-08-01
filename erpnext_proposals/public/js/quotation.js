// Patch ERPNext's QuotationController to suppress native buttons on proposals.
// ERPNext adds these buttons inside its own controller.refresh(), which runs before
// frappe.ui.form.on handlers. Patching here ensures removal after they are added.
frappe.ui.form.on("Quotation", "onload", function (frm) {
	const ctrl = frm.cscript;
	if (!ctrl || ctrl.__proposal_patch_applied) return;
	const _origRefresh = ctrl.refresh.bind(ctrl);
	ctrl.refresh = function (...args) {
		_origRefresh(...args);
		if (frm.doc.proposal_group && frm.doc.docstatus === 1) {
			frm.remove_custom_button(__("Update Items"));
			frm.remove_custom_button(__("Set as Lost"));
			// Sales Order only after client accepts (Ganada) and project exists
			if (frm.doc.workflow_state !== "Ganada" || !frm.doc.proposal_project) {
				frm.remove_custom_button(__("Sales Order"), __("Create"));
			}
		}
	};
	ctrl.__proposal_patch_applied = true;
});

frappe.ui.form.on("Quotation", {
	onload(frm) {
		// Reload attachments when server signals PDFs are ready (after_commit)
		frappe.realtime.on("erpnext_proposals_pdfs_attached", (data) => {
			if (frm.doctype === data.doctype && frm.docname === data.name) {
				frm.attachments.refresh();
				frm.reload_doc();
			}
		});
	},

	// Reload after workflow transition so PDF attachments appear immediately
	after_workflow_action(frm) {
		if (frm.doc.proposal_group) {
			frm.reload_doc();
		}
	},

	refresh(frm) {
		// proposal_version and proposal_group are server-assigned — lock UI editing
		frm.set_df_property("proposal_version", "read_only", 1);
		if (frm.doc.proposal_version >= 1) {
			frm.set_df_property("proposal_group", "read_only", 1);
		}

		// Submitted proposals: hide Cancel button
		// Update Items: blocked in backend (before_update_after_submit). UI hide pending —
		// button origin unknown without runtime inspection; see TODO in PR.
		// Sales Order: left visible — Aprobada → SO is an accepted flow.
		if (frm.doc.docstatus === 1 && frm.doc.proposal_group) {
			frm.page.btn_secondary.hide();
		}

		if (frm.fields_dict.quotation_scope_items) {
			frm.fields_dict.quotation_scope_items.grid.get_field("scope_item").get_query = () => ({
				filters: { enabled: 1 },
			});
		}

		// Sincronizar alcance desde catálogo: solo en Borrador (docstatus=0) — documento editable
		if (
			!frm.is_new() &&
			frm.doc.proposal_template &&
			frm.doc.docstatus === 0 &&
			frm.doc.workflow_state === "Borrador"
		) {
			frm.add_custom_button(
				__("Sincronizar alcance desde catálogo"),
				() => {
					frappe.confirm(
						__(
							"¿Sincronizar el alcance con el catálogo? Las filas generadas desde catálogo se actualizarán a sus valores vigentes (horas, título, fase, perfil), se eliminarán las de alcances deshabilitados o de ítems ya no cotizados, y se agregarán las nuevas. Las filas agregadas manualmente no se modifican — para personalizaciones permanentes, usa filas manuales."
						),
						() => {
							const _resync = () =>
								frappe.call({
									method: "erpnext_proposals.erpnext_proposals.utils.quotation.resync_scope_from_catalog",
									args: { quotation_name: frm.doc.name },
									freeze: true,
									freeze_message: __("Sincronizando alcance…"),
									callback(r) {
										if (r.message) {
											const { updated, added, removed } = r.message;
											frappe.show_alert({
												message: __(
													"Alcance sincronizado — {0} actualizadas, {1} agregadas, {2} eliminadas",
													[updated, added, removed]
												),
												indicator: "green",
											});
											frm.reload_doc();
										}
									},
								});
							// Guardar primero si hay cambios pendientes, para sincronizar sobre los Items ya guardados
							if (frm.is_dirty()) {
								frm.save().then(_resync);
							} else {
								_resync();
							}
						}
					);
				},
				__("Propuesta")
			);
		}

		// PDF buttons — available in all states (including Borrador for preview)
		if (!frm.is_new()) {
			frm.add_custom_button(
				__("Imprimir Propuesta Comercial"),
				() => {
					frappe
						.call({
							method: "erpnext_proposals.erpnext_proposals.utils.print_format.get_effective_commercial_print_format",
							args: { quotation: frm.doc.name },
						})
						.then((r) => {
							const fmt = r.message || "Propuesta Comercial";
							const url = `/printview?doctype=Quotation&name=${encodeURIComponent(
								frm.doc.name
							)}&format=${encodeURIComponent(fmt)}&no_letterhead=0`;
							window.open(url, "_blank");
						});
				},
				__("Propuesta")
			);

			frm.add_custom_button(
				__("Imprimir Rentabilidad Estimada"),
				() => {
					const url = `/printview?doctype=Quotation&name=${encodeURIComponent(
						frm.doc.name
					)}&format=Rentabilidad%20Estimada&no_letterhead=0`;
					window.open(url, "_blank");
				},
				__("Propuesta")
			);

			// Mostrar el Print Format comercial efectivo que se usará.
			frappe
				.call({
					method: "erpnext_proposals.erpnext_proposals.utils.print_format.get_effective_commercial_print_format",
					args: { quotation: frm.doc.name },
				})
				.then((r) => {
					if (r.message && frm.get_field("proposal_print_format")) {
						frm.set_df_property(
							"proposal_print_format",
							"description",
							__("Formato efectivo actual: {0}", [r.message])
						);
					}
				});

			// Show attached PDFs if they exist
			frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "File",
					filters: {
						attached_to_doctype: "Quotation",
						attached_to_name: frm.doc.name,
						file_name: ["like", "%.pdf"],
					},
					fields: ["file_name", "file_url"],
					limit: 10,
				},
				callback(r) {
					if (r.message && r.message.length) {
						r.message.forEach((f) => {
							frm.add_custom_button(
								__("↓ {0}", [f.file_name]),
								() => window.open(f.file_url),
								__("Propuesta")
							);
						});
					}
				},
			});
		}

		// Button: Nueva versión — submitted + Rechazada + not yet superseded
		if (
			frm.doc.docstatus === 1 &&
			frm.doc.workflow_state === "Rechazada" &&
			frm.doc.proposal_group &&
			!frm.doc.superseded_by_proposal
		) {
			frm.add_custom_button(
				__("Crear nueva versión"),
				() => {
					const fields = [
						{
							fieldname: "reason",
							label: __("Motivo de revisión"),
							fieldtype: "Small Text",
							reqd: 1,
						},
						{
							fieldname: "summary",
							label: __("Resumen de cambios"),
							fieldtype: "Small Text",
						},
					];
					frappe.prompt(
						fields,
						({ reason, summary }) => {
							frappe.call({
								method: "erpnext_proposals.erpnext_proposals.utils.proposal_versioning.create_new_proposal_version",
								args: {
									quotation_name: frm.doc.name,
									reason,
									summary: summary || "",
								},
								freeze: true,
								freeze_message: __("Creando nueva versión…"),
								callback(r) {
									if (r.message) {
										frappe.set_route("Form", "Quotation", r.message);
									}
								},
							});
						},
						__("Nueva versión de propuesta"),
						__("Crear versión")
					);
				},
				__("Propuesta")
			);
		}

		// Button: Create Project — submitted + Ganada (client accepted)
		const _projectStates = ["Ganada"];
		if (
			frm.doc.docstatus === 1 &&
			_projectStates.includes(frm.doc.workflow_state) &&
			frm.doc.proposal_template &&
			frm.doc.quotation_scope_items &&
			frm.doc.quotation_scope_items.length > 0
		) {
			const label = frm.doc.proposal_project
				? __("Ver / Actualizar Proyecto")
				: __("Crear Proyecto desde Propuesta");

			frm.add_custom_button(
				label,
				() => {
					frappe.confirm(
						__("¿Crear Proyecto y Tasks desde los Scope Items de esta propuesta?"),
						() => {
							frappe.call({
								method: "erpnext_proposals.erpnext_proposals.utils.project.create_project_from_quotation",
								args: { quotation_name: frm.doc.name },
								callback(r) {
									if (r.message) {
										const { project, tasks_created, tasks_skipped } =
											r.message;
										frappe.msgprint(
											__(
												"Proyecto: {0}<br>Tasks nuevas: {1} | Omitidas: {2}",
												[
													`<a href="/app/project/${project}">${project}</a>`,
													tasks_created,
													tasks_skipped,
												]
											)
										);
										frm.reload_doc();
									}
								},
							});
						}
					);
				},
				__("Propuesta")
			);
		}
	},
});

// ─────────────────────────────────────────────────────────────────────────────
// Composer de Email (envío de propuestas) — ajustes SOLO para Quotations de propuesta.
//
// Se parchea el prototipo de frappe.views.CommunicationComposer SIN modificar Frappe core.
// Todos los overrides delegan primero en el método original y luego actúan únicamente cuando
// `is_proposal_composer()` es verdadero (Quotation con campos de propuesta). Para el resto de
// documentos/DocTypes el comportamiento nativo queda intacto.
//
// Problemas corregidos en Frappe v16 (apps/frappe/.../views/communication.js):
//   A. check_email_template_html(): si el Email Template tiene use_html=1, el composer solo MUESTRA
//      la casilla "Use HTML" pero NO la activa → el HTML del template se inserta en el editor Quill
//      (fieldname "content") y se degrada. Aquí además ACTIVAMOS use_html y movemos el contenido
//      actual (incluida la firma nativa ya agregada) al editor HTML (fieldname "html_content").
//   B. setup_email()/form.js abren el composer con attach_document_print=true → en Quotation puede
//      adjuntar el Print Format "Standard" (interno). Aquí lo iniciamos DESMARCADO y, cuando el
//      usuario lo active manualmente, preseleccionamos el formato de propuesta válido (efectivo →
//      configurado) en lugar de "Standard"/primer formato.
// La firma (C) NO se reimplementa: sigue viniendo del mecanismo nativo (User.email_signature o, en su
// defecto, Email Account.signature con add_signature=1). Solo se garantiza que el modo HTML no la pierda.
(function patch_communication_composer_for_proposals() {
	const CC = frappe.views && frappe.views.CommunicationComposer;
	if (!CC || CC.prototype.__erpnext_proposals_patched) return;
	CC.prototype.__erpnext_proposals_patched = true;

	// Una Quotation "manejada por erpnext_proposals": tiene template o algún formato de propuesta.
	function is_proposal_composer(self) {
		const doc = self && self.frm && self.frm.doc;
		return !!(
			doc &&
			self.frm.doctype === "Quotation" &&
			(doc.proposal_template ||
				doc.proposal_effective_print_format ||
				doc.proposal_print_format)
		);
	}

	// Formato de propuesta a usar si el usuario adjunta el print: efectivo → configurado.
	// Se valida que exista y corresponda a Quotation (vía la lista de formatos de la meta).
	function proposal_print_format(self) {
		const doc = self.frm.doc;
		const valid = frappe.meta.get_print_formats("Quotation") || [];
		for (const candidate of [doc.proposal_effective_print_format, doc.proposal_print_format]) {
			if (candidate && valid.indexOf(candidate) !== -1) {
				return candidate;
			}
		}
		return null;
	}

	// A. Email Template con use_html=1 → activar "Use HTML" automáticamente y preservar contenido/firma.
	const _check_email_template_html = CC.prototype.check_email_template_html;
	CC.prototype.check_email_template_html = async function (email_template) {
		await _check_email_template_html.call(this, email_template);
		if (!is_proposal_composer(this) || !email_template) return;

		const r = await frappe.db.get_value("Email Template", email_template, "use_html");
		if (!(r && r.message && r.message.use_html === 1)) return;

		const use_html_field = this.dialog.fields_dict.use_html;
		use_html_field.toggle(true); // mantener visible (el nativo ya lo mostró)

		if (!this.dialog.get_value("use_html")) {
			// Contenido actual (Quill) — incluye la firma nativa ya agregada por set_content().
			const current = this.dialog.get_value("content") || "";
			await this.dialog.set_value("use_html", 1); // activar el valor real, no solo mostrar
			// on_use_html_toggle nativo solo mueve el contenido ante un evento DOM real; al fijar el
			// valor por código, movemos nosotros el contenido al editor HTML si aún está vacío.
			if (!this.dialog.get_value("html_content") && current) {
				await this.dialog.set_value("html_content", current);
			}
		}
	};

	// B. Attach Document Print: iniciar DESMARCADO en propuestas y preseleccionar el formato de propuesta.
	const _setup_print = CC.prototype.setup_print;
	CC.prototype.setup_print = function () {
		_setup_print.call(this);
		if (!is_proposal_composer(this)) return;

		const fields = this.dialog.fields_dict;
		// form.js abre el composer con attach_document_print=true; setup_email() lo auto-marca después
		// de este método. Al ponerlo en 0 aquí, ese auto-marcado no ocurre y arranca OFF.
		this.attach_document_print = 0;
		fields.attach_document_print.set_input(0);
		$(fields.select_print_format.wrapper).toggle(false);

		// Preseleccionar el formato de propuesta (para cuando el usuario active el checkbox
		// manualmente); si no hay uno válido, se conserva el valor nativo (no se fuerza "Standard").
		const fmt = proposal_print_format(this);
		if (fmt) {
			$(fields.select_print_format.input).val(fmt);
			if (typeof this.guess_language === "function") {
				this.guess_language();
			}
		}
	};
})();
