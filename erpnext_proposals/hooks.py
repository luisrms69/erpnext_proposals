app_name = "erpnext_proposals"
app_title = "ERPNext Proposals"
app_publisher = "Consultoria en Negocios y Aplicaciones"
app_description = "Propuestas comerciales profesionales sobre ERPNext Quotation"
app_email = "it@buzola.mx"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

# Jinja
# ------------------

jinja = {
	"methods": [
		"erpnext_proposals.erpnext_proposals.report.profitability_estimate.profitability_estimate.get_profitability_data",
		"erpnext_proposals.erpnext_proposals.utils.printing.render_section_content",
		"erpnext_proposals.erpnext_proposals.utils.printing.parse_json",
		"erpnext_proposals.erpnext_proposals.utils.printing.get_logo_url",
	]
}

# Fixtures
# ------------------

fixtures = [
	{
		"doctype": "Custom Field",
		"filters": [
			["dt", "=", "Quotation"],
			[
				"fieldname",
				"in",
				[
					"proposal_details_section",
					"proposal_template",
					"proposal_title",
					"quotation_scope_items",
					"proposal_project",
					"proposal_cost_center",
					"proposal_reviewed_by",
					"proposal_reviewed_on",
					"proposal_approved_by",
					"proposal_approved_on",
					"proposal_section_row1",
					"proposal_col_break_1",
					"proposal_section_row2",
					"proposal_col_break_2",
					"proposal_section_row3",
					"proposal_col_break_3",
					"proposal_sections_snapshot",
					"proposal_group",
					"proposal_version",
					"previous_proposal",
					"superseded_by_proposal",
					"proposal_revision_reason",
					"proposal_revision_summary",
				],
			],
		],
	},
	{
		"doctype": "Role",
		"filters": [["name", "=", "Proposals Manager"]],
	},
	{
		"doctype": "Workflow",
		"filters": [["name", "=", "Propuesta Comercial"]],
	},
	{
		"doctype": "Workflow State",
		"filters": [
			[
				"workflow_state_name",
				"in",
				["Borrador", "En Revision", "Aprobada", "Rechazada", "Enviada al Cliente"],
			]
		],
	},
]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "erpnext_proposals",
# 		"logo": "/assets/erpnext_proposals/logo.png",
# 		"title": "ERPNext Proposals",
# 		"route": "/erpnext_proposals",
# 		"has_permission": "erpnext_proposals.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/erpnext_proposals/css/erpnext_proposals.css"
# app_include_js = "/assets/erpnext_proposals/js/erpnext_proposals.js"

# include js, css files in header of web template
# web_include_css = "/assets/erpnext_proposals/css/erpnext_proposals.css"
# web_include_js = "/assets/erpnext_proposals/js/erpnext_proposals.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "erpnext_proposals/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Quotation": "public/js/quotation.js",
	"Sales Order": "public/js/sales_order.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "erpnext_proposals/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "erpnext_proposals.utils.jinja_methods",
# 	"filters": "erpnext_proposals.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "erpnext_proposals.install.before_install"
after_install = "erpnext_proposals.erpnext_proposals.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "erpnext_proposals.uninstall.before_uninstall"
# after_uninstall = "erpnext_proposals.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "erpnext_proposals.utils.before_app_install"
# after_app_install = "erpnext_proposals.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "erpnext_proposals.utils.before_app_uninstall"
# after_app_uninstall = "erpnext_proposals.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "erpnext_proposals.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "erpnext_proposals.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Quotation": {
		"before_insert": "erpnext_proposals.erpnext_proposals.utils.quotation.on_quotation_before_insert",
		"validate": [
			"erpnext_proposals.erpnext_proposals.utils.quotation.on_quotation_validate",
			"erpnext_proposals.erpnext_proposals.utils.workflow_validations.on_quotation_validate_workflow",
		],
		"before_submit": "erpnext_proposals.erpnext_proposals.utils.quotation.on_quotation_before_submit",
		"before_update_after_submit": "erpnext_proposals.erpnext_proposals.utils.workflow_validations.on_quotation_validate_workflow",
	},
	"Sales Order": {
		"validate": "erpnext_proposals.erpnext_proposals.utils.sales_order.on_sales_order_validate",
		"on_submit": "erpnext_proposals.erpnext_proposals.utils.sales_order.on_sales_order_submit",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"erpnext_proposals.erpnext_proposals.utils.cost_matrix.rebuild_cost_matrix",
	],
}

# Testing
# -------

# before_tests = "erpnext_proposals.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "erpnext_proposals.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "erpnext_proposals.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "erpnext_proposals.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["erpnext_proposals.utils.before_request"]
# after_request = ["erpnext_proposals.utils.after_request"]

# Job Events
# ----------
# before_job = ["erpnext_proposals.utils.before_job"]
# after_job = ["erpnext_proposals.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"erpnext_proposals.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
