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

// Issue #17: en una Quotation NUEVA creada desde Frappe CRM, copiar `crm_deal` a `proposal_group`
// cuando este está vacío (espejo cliente del respaldo de servidor en on_quotation_before_insert, que
// no alcanza a correr porque el formulario valida los obligatorios en el navegador antes de insertar).
// Solo en Draft nuevo (frm.is_new()); nunca sobrescribe un grupo capturado manualmente; copia exacta.
function autofill_proposal_group_from_crm_deal(frm) {
	if (frm.is_new() && !frm.doc.proposal_group && frm.doc.crm_deal) {
		frm.set_value("proposal_group", frm.doc.crm_deal);
	}
}

// Secciones opcionales: la ÚNICA fuente es el Proposal Template. El selector
// `proposal_optional_sections` solo ofrece las Sections opcionales (include_by_default=0) de ese
// Template; se oculta si el Template no tiene opcionales; y al cambiar de Template se podan las
// selecciones que dejaron de ser válidas (evita estados inconsistentes).
function refresh_optional_sections(frm) {
	const field = "proposal_optional_sections";
	if (!frm.doc.proposal_template) {
		frm._optional_sections = [];
		frm.set_df_property(field, "hidden", 1);
		if (frm.doc.docstatus === 0 && (frm.doc[field] || []).length) {
			frm.clear_table(field);
			frm.refresh_field(field);
		}
		return;
	}
	frappe.call({
		method: "erpnext_proposals.erpnext_proposals.utils.quotation.get_template_optional_sections",
		args: { template: frm.doc.proposal_template },
		callback: (r) => {
			const opts = r.message || [];
			const names = opts.map((o) => o.name);
			frm._optional_sections = names;
			// Ocultar el campo si el Template no define ninguna Section opcional.
			frm.set_df_property(field, "hidden", names.length ? 0 : 1);
			// Podar selecciones que ya no pertenecen al Template o dejaron de ser opcionales.
			if (frm.doc.docstatus === 0) {
				const rows = frm.doc[field] || [];
				const keep = rows.filter((row) => names.includes(row.proposal_section));
				if (keep.length !== rows.length) {
					frm.clear_table(field);
					keep.forEach((row) => {
						frm.add_child(field, { proposal_section: row.proposal_section });
					});
					frm.refresh_field(field);
				}
			}
		},
	});
}

// ── Sincronización de alcance con catálogo (aviso + resync) ────────────────────
// Texto ÚNICO del aviso (centralizado): lo usan tanto la acción manual como la
// sincronización que antecede a una generación/preview de PDF en Borrador.
function proposal_resync_message() {
	return `
<div style="line-height:1.5">
  <p><b>¿Sincronizar la propuesta con el catálogo vigente?</b></p>
  <p>Esta acción actualizará el contenido de la propuesta con la información actualmente registrada en el catálogo.</p>
  <p style="margin:8px 0 2px"><b>Se actualizará</b></p>
  <ul style="margin:0 0 8px">
    <li>Título, descripción, entregable, horas, fase, perfil y demás datos de las actividades generadas desde catálogo.</li>
    <li>Descripción, metodología, resultado esperado y límites de alcance de los servicios cotizados.</li>
    <li>Secciones de la propuesta conforme al Template y a las secciones opcionales seleccionadas.</li>
    <li>Se agregarán nuevas actividades disponibles para los servicios cotizados.</li>
    <li>Se eliminarán actividades generadas desde catálogo deshabilitadas, eliminadas o que ya no correspondan a los servicios cotizados.</li>
  </ul>
  <p style="margin:8px 0 2px"><b>Se conservará</b></p>
  <ul style="margin:0 0 8px">
    <li>Actividades agregadas manualmente.</li>
    <li>Alcance específico capturado para esta propuesta.</li>
    <li>Selección de actividades incluidas en la propuesta.</li>
    <li>Tarifas y costos propios de la cotización.</li>
  </ul>
  <div style="border:1px solid var(--border-color,#d1d8dd);border-radius:4px;padding:6px 10px;margin:8px 0">
    <b>Importante:</b> si modificaste manualmente una actividad generada desde catálogo, sus campos
    controlados por catálogo serán reemplazados por los valores vigentes.
  </div>
  <p><b>Después de sincronizar, revisa nuevamente la propuesta antes de enviarla a revisión.</b></p>
</div>`;
}

// Muestra el aviso; si el usuario confirma: guarda pendientes → ejecuta el MISMO resync real
// (resync_scope_from_catalog) → recarga → ejecuta on_done (p. ej. abrir el PDF). Si cancela: nada.
function confirm_and_resync(frm, on_done) {
	frappe.confirm(proposal_resync_message(), () => {
		const _resync = () =>
			frappe.call({
				method: "erpnext_proposals.erpnext_proposals.utils.quotation.resync_scope_from_catalog",
				args: { quotation_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Sincronizando alcance…"),
				callback(r) {
					if (!r.message) return;
					const { updated, added, removed } = r.message;
					frappe.show_alert({
						message: __(
							"Alcance sincronizado — {0} actualizadas, {1} agregadas, {2} eliminadas",
							[updated, added, removed]
						),
						indicator: "green",
					});
					frm.reload_doc().then(() => {
						if (on_done) on_done();
					});
				},
			});
		if (frm.is_dirty()) frm.save().then(_resync);
		else _resync();
	});
	// Cancelar (No / cerrar): no sincroniza y no ejecuta on_done → no se genera el PDF.
}

// Solo un Borrador con template puede sincronizarse. En otros estados el contenido ya está congelado.
function is_proposal_borrador(frm) {
	return (
		frm.doc.docstatus === 0 &&
		frm.doc.workflow_state === "Borrador" &&
		!!frm.doc.proposal_template
	);
}

// Generación de PDF solicitada por el usuario: en Borrador antecede el aviso+resync; fuera de Borrador
// (contenido ya congelado) genera directo. NUNCA se usa en el freeze (ese es server-side, sin JS).
function generate_pdf_with_resync(frm, generate_fn) {
	if (is_proposal_borrador(frm)) confirm_and_resync(frm, generate_fn);
	else generate_fn();
}

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

	// Issue #17: al cambiar el Frappe CRM Deal, autocompletar proposal_group en la Quotation nueva.
	crm_deal(frm) {
		autofill_proposal_group_from_crm_deal(frm);
	},

	// Al cambiar el Proposal Template, recalcular las opciones del selector de Sections opcionales.
	proposal_template(frm) {
		refresh_optional_sections(frm);
	},

	refresh(frm) {
		// Issue #17: cubre las Quotations nuevas creadas desde Frappe CRM con crm_deal ya poblado.
		autofill_proposal_group_from_crm_deal(frm);

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
			// Acción manual: mismo aviso y misma lógica real de resync (centralizados).
			frm.add_custom_button(
				__("Sincronizar alcance desde catálogo"),
				() => confirm_and_resync(frm),
				__("Propuesta")
			);

			// Acción manual EXPLÍCITA para recuperar/agregar Scope Items faltantes desde los Items de la
			// cotización. Distinta del guardado (que nunca repuebla) y del resync (que nunca agrega).
			frm.add_custom_button(
				__("Agregar Scope Items desde Items"),
				() => {
					frappe
						.call({
							method: "erpnext_proposals.erpnext_proposals.utils.quotation.add_missing_scope_items_from_items",
							args: { quotation_name: frm.doc.name },
						})
						.then((r) => {
							const m = r.message || {};
							frappe.show_alert({
								message: __("Scope Items agregados: {0}.", [m.added || 0]),
								indicator: "green",
							});
							frm.reload_doc();
						});
				},
				__("Propuesta")
			);
		}

		// PDF buttons — available in all states (including Borrador for preview)
		if (!frm.is_new()) {
			// Acciones que RE-GENERAN una nueva representación desde el Print Format. Una vez que el
			// sistema generó y adjuntó el documento oficial correspondiente (comprobación REAL de los
			// adjuntos vía get_proposal_documents_status), se ocultan para evitar reimprimir/generar
			// accidentalmente una versión distinta tras formalizar la propuesta. Los botones de
			// descarga de abajo (acceso a lo YA generado) permanecen intactos.
			frappe.call({
				method: "erpnext_proposals.erpnext_proposals.utils.quotation.get_proposal_documents_status",
				args: { quotation: frm.doc.name },
				callback(r) {
					const st = r.message || {};

					if (!st.commercial) {
						frm.add_custom_button(
							__("Vista previa comercial"),
							() =>
								// En Borrador: aviso + resync antes de abrir el PDF (cada preview refleja el catálogo vigente).
								generate_pdf_with_resync(frm, () => {
									frappe
										.call({
											method: "erpnext_proposals.erpnext_proposals.utils.print_format.get_effective_commercial_print_format",
											args: { quotation: frm.doc.name },
										})
										.then((r2) => {
											const fmt = r2.message || "Propuesta Comercial";
											const url = `/printview?doctype=Quotation&name=${encodeURIComponent(
												frm.doc.name
											)}&format=${encodeURIComponent(fmt)}&no_letterhead=0`;
											window.open(url, "_blank");
										});
								}),
							__("Propuesta")
						);
					}

					if (!st.rentabilidad) {
						frm.add_custom_button(
							__("Vista previa rentabilidad"),
							() =>
								generate_pdf_with_resync(frm, () => {
									const url = `/printview?doctype=Quotation&name=${encodeURIComponent(
										frm.doc.name
									)}&format=Rentabilidad%20Estimada&no_letterhead=0`;
									window.open(url, "_blank");
								}),
							__("Propuesta")
						);
					}
				},
			});

			// Solo en Borrador: descargar un PDF de BORRADOR (no oficial) para revisión externa. Genera con
			// el renderer configurado en servidor (render_proposal_pdf, ADR-0015) y descarga con un nombre
			// prefijado "BORRADOR". NO adjunta, NO congela, NO cambia estado ni invoca el flujo formal: el
			// documento oficial se genera aparte al pasar a En Revisión. El filename lo pone el servidor.
			if (frm.doc.docstatus === 0 && frm.doc.workflow_state === "Borrador") {
				frm.add_custom_button(
					__("Descargar PDF comercial"),
					() =>
						// Aviso + resync antes de generar, para que el borrador refleje el catálogo vigente.
						generate_pdf_with_resync(frm, () => {
							open_url_post(
								"/api/method/erpnext_proposals.erpnext_proposals.utils.print_format.download_commercial_draft_pdf",
								{ quotation: frm.doc.name }
							);
						}),
					__("Propuesta")
				);
				// Descargar PDF de la Rentabilidad Estimada (mismo render_proposal_pdf, PF interno).
				frm.add_custom_button(
					__("Descargar PDF rentabilidad"),
					() =>
						generate_pdf_with_resync(frm, () => {
							open_url_post(
								"/api/method/erpnext_proposals.erpnext_proposals.utils.print_format.download_rentabilidad_draft_pdf",
								{ quotation: frm.doc.name }
							);
						}),
					__("Propuesta")
				);
			}

			// Solo en Borrador: generar/descargar el SOW (otra representación del mismo contenido). Mismo
			// mecanismo que el borrador comercial (render_proposal_pdf), variando solo el Print Format SOW.
			// Solo se muestra si la plantilla configura un Print Format de SOW.
			if (frm.doc.docstatus === 0 && frm.doc.workflow_state === "Borrador") {
				frappe
					.call({
						method: "erpnext_proposals.erpnext_proposals.utils.print_format.get_effective_sow_print_format",
						args: { quotation: frm.doc.name },
					})
					.then((r) => {
						if (r.message) {
							const sowFmt = r.message;
							// Vista previa SOW → HTML (mismo /printview que el comercial, con el PF SOW).
							frm.add_custom_button(
								__("Vista previa SOW"),
								() =>
									generate_pdf_with_resync(frm, () => {
										const url = `/printview?doctype=Quotation&name=${encodeURIComponent(
											frm.doc.name
										)}&format=${encodeURIComponent(sowFmt)}&no_letterhead=0`;
										window.open(url, "_blank");
									}),
								__("Propuesta")
							);
							// Descargar PDF SOW → PDF (mismo render_proposal_pdf que el comercial).
							frm.add_custom_button(
								__("Descargar PDF SOW"),
								() =>
									generate_pdf_with_resync(frm, () => {
										open_url_post(
											"/api/method/erpnext_proposals.erpnext_proposals.utils.print_format.download_sow_draft_pdf",
											{ quotation: frm.doc.name }
										);
									}),
								__("Propuesta")
							);
						}
					});
			}

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

		// Selector de secciones opcionales (Table MultiSelect). Va AL FINAL y PROTEGIDO: un fallo aquí
		// nunca debe impedir construir el grupo `Propuesta`. (Regresión previa: set_query con forma de
		// child table lanzaba TypeError en un Table MultiSelect y abortaba todo el refresh.)
		try {
			// Table MultiSelect (ControlLink) → forma 2-arg de set_query, NO la de child table (.grid).
			frm.set_query("proposal_optional_sections", () => ({
				filters: [["name", "in", frm._optional_sections || []]],
			}));
			refresh_optional_sections(frm);
		} catch (e) {
			console.error("proposal_optional_sections selector error:", e);
		}

		// Campo Link `proposal_print_format`: MISMA query central de elegibilidad que Proposal Template
		// (solo Print Formats de Quotation, no deshabilitados). No se toca el selector estándar de impresión.
		erpnext_proposals.print_format.set_query(frm, "proposal_print_format");
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
