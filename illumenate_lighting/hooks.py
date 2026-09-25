app_name = "illumenate_lighting"
app_title = "ilLumenate Lighting"
app_publisher = "ilLumenate Lighting"
app_description = "Custom code for ilLumenate Lighting ERPNext"
app_email = "hi@illumenate.lighting"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "illumenate_lighting",
# 		"logo": "/assets/illumenate_lighting/logo.png",
# 		"title": "ilLumenate Lighting",
# 		"route": "/illumenate_lighting",
# 		"has_permission": "illumenate_lighting.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# Bundles (public/js/*.bundle.js, public/css/*.bundle.scss) are built by
# `bench build` into content-hashed files so browsers never serve a stale copy
# (plain /assets paths are cached for a year with `immutable`).
app_include_css = ["illumenate_desk.bundle.css"]
# shared_configurator + fixture_steps + tape_neon_steps + desk/desk_dialog
# ("Configure & Add Fixture" dialog for Quotation / Sales Order).
app_include_js = ["illumenate_desk.bundle.js"]

# include js, css files in header of web template
web_include_css = [
	"https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css",
	"illumenate_web.bundle.css",
]
# portal + shared_configurator + fixture_steps + tape_neon_steps
web_include_js = ["illumenate_web.bundle.js"]

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "illumenate_lighting/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"ilL-Portal-Delivery": "public/js/portal_delivery.js", "Issue": "public/js/desk_conversation.js", "ilL-Document-Request": "public/js/desk_conversation.js", "ilL-Quote-Request": "public/js/quote_request.js", "Sales Order": "public/js/sales_order.js", "Quotation": "public/js/quotation.js",
    "ilL-Webflow-Product": "public/js/product_publication.js", "ilL-Publish-Job": "public/js/product_publication.js"}
doctype_list_js = {"Item": "public/js/item_list.js"}
doctype_js.update({name: "public/js/authoring_readiness.js" for name in (
    "ilL-Fixture-Template", "ilL-Tape-Neon-Template", "ilL-LED-Sheet-Template",
    "ilL-Driver-Template", "ilL-Controller-Template",
)})
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "illumenate_lighting/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# Brand logo in website navbar (replaces default "Home" text)
brand_html = '<img src="/assets/illumenate_lighting/images/nav-logo.png" alt="ilLumenate Lighting" class="ill-nav-logo">'

# website user home page (by Role)
role_home_page = {
	"Dealer": "portal",
	"Website User": "portal",
	"Customer": "portal",
}

# Website Route Rules
# -------------------
website_route_rules = [
	# Portal main pages
	{"from_route": "/portal", "to_route": "portal"},
	{"from_route": "/portal/", "to_route": "portal"},

	# Projects
	{"from_route": "/portal/projects", "to_route": "ill_projects"},
	{"from_route": "/portal/projects/<project>", "to_route": "project"},
	{"from_route": "/portal/projects/<project>/collaborators", "to_route": "collaborators"},
	{"from_route": "/portal/projects/<project>/schedules/new", "to_route": "schedule"},

	# Schedules
	{"from_route": "/portal/schedules/<schedule>", "to_route": "schedule"},

	# Configurator
	{"from_route": "/portal/configure", "to_route": "configure"},
	{"from_route": "/portal/configure/<template>", "to_route": "configure"},
	{"from_route": "/portal/request-dealer-access", "to_route": "request_dealer_access"},
	{"from_route": "/portal/configure-tape", "to_route": "configure_tape"},
	{"from_route": "/portal/configure-neon", "to_route": "configure_tape"},
	{"from_route": "/portal/configure-sheet", "to_route": "configure_sheet"},
	{"from_route": "/configure-sheet", "to_route": "configure_sheet"},
	{"from_route": "/portal/configure-kit", "to_route": "configure_kit"},
	{"from_route": "/portal/configure-kit/<template>", "to_route": "configure_kit"},
	{"from_route": "/portal/edit_fixture", "to_route": "edit_fixture"},

	# Product Catalog (System Manager only)
	{"from_route": "/portal/products", "to_route": "products_catalog"},
	{"from_route": "/portal/products/<slug>", "to_route": "product_detail"},

	# Issued commercial offers
	{"from_route": "/portal/quotes", "to_route": "quotes"},
	{"from_route": "/portal/quotes/<offer>", "to_route": "quote_detail"},
	{"from_route": "/portal/quote-requests/<request>", "to_route": "quote_request_detail"},

	# Orders
	{"from_route": "/portal/orders", "to_route": "orders"},
	{"from_route": "/portal/orders/<order>", "to_route": "order_detail"},

	# Drawings
	{"from_route": "/portal/drawings", "to_route": "drawings"},
	{"from_route": "/portal/drawings/<request>", "to_route": "drawing_detail"},

	# Resources
	{"from_route": "/portal/resources", "to_route": "resources"},

	# Support
	{"from_route": "/portal/support", "to_route": "ill_support"},
	{"from_route": "/portal/support/faq", "to_route": "ill_support"},
	{"from_route": "/portal/support/<ticket_name>", "to_route": "support_detail"},

	# Account
	{"from_route": "/portal/account", "to_route": "account"},
	{"from_route": "/portal/accept-invitation", "to_route": "accept_invitation"},
	{"from_route": "/portal/account/notifications", "to_route": "account"},
]

# Website Redirects
# ------------------
# /portal/configure-webflow was retired in favor of the "Guided Wizard" mode
# of the unified /portal/configure page (same fixture_steps.js / webflow_configurator.py
# backend, just merged into one page). Redirect old links/bookmarks/embeds.
website_redirects = [
	{"source": r"/portal/configure-webflow/(.*)", "target": r"/portal/configure?template=\1&category=Linear Fixture&mode=wizard"},
	{"source": r"/portal/configure-webflow", "target": r"/portal/configure?category=Linear Fixture&mode=wizard"},
]

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "illumenate_lighting.utils.jinja_methods",
# 	"filters": "illumenate_lighting.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "illumenate_lighting.install.before_install"
after_install = "illumenate_lighting.illumenate_lighting.install.after_install"
before_migrate = "illumenate_lighting.portal_workspace.before_migrate"
after_migrate = "illumenate_lighting.portal_workspace.after_migrate"

# Fixtures
# --------
# Fixtures are records that get inserted during app installation
fixtures = [
	{"dt": "Role", "filters": [["name", "in", ["Dealer"]]]},
	{"dt": "Workflow", "filters": [["name", "in", ["ILL Document Request Workflow"]]]},
	{"dt": "ILL Request Type"},
	# Webflow integration fixtures (Phase 1)
	{"dt": "ilL-Attribute-Certification"},
	{"dt": "ilL-Webflow-Category"},
	# Webflow configurator fixtures (Phase 2)
	{"dt": "ilL-Attribute-Feed-Direction"},
	# LED Sheet seed data (Snowfield; Analog RGBW intentionally excluded pending series code)
	{"dt": "ilL-Spec-Driver", "filters": [["item", "in", ["LED-SNF-DRIVER-60W", "LED-SNF-DRIVER-300W"]]]},
	{"dt": "ilL-Rel-Driver-Eligibility", "filters": [["template_type", "=", "ilL-LED-Sheet-Template"]]},
	{"dt": "ilL-Spec-LED-Sheet"},
	{"dt": "ilL-LED-Sheet-Template"},
	{
		"dt": "Item",
		"filters": [["item_code", "in", ["LED-SNF-JUMPER", "LED-SNF-LEADER", "LED-SNF-DRIVER-60W", "LED-SNF-DRIVER-300W"]]],
	},
	# Job Title Master for CRM Lead integration
	{"dt": "ilL-Job-Title-Master", "filters": [["is_active", "=", 1]]},
	# Custom fields for CRM Lead and other DocTypes
	{"dt": "Custom Field"},
	# Workspace for sidebar navigation
	{"dt": "Workspace", "filters": [["module", "=", "ilLumenate Lighting"]]},
	# Dashboard number cards for the ilLumenate Lighting workspace
	{"dt": "Number Card", "filters": [["module", "=", "ilLumenate Lighting"]]},
]

# Uninstallation
# ------------

# before_uninstall = "illumenate_lighting.uninstall.before_uninstall"
# after_uninstall = "illumenate_lighting.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "illumenate_lighting.utils.before_app_install"
# after_app_install = "illumenate_lighting.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "illumenate_lighting.utils.before_app_uninstall"
# after_app_uninstall = "illumenate_lighting.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "illumenate_lighting.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"ilL-Order-Change": "illumenate_lighting.illumenate_lighting.portal.order_changes.get_permission_query_conditions",
	"ilL-Account-Request": "illumenate_lighting.illumenate_lighting.portal.accounts.query_conditions",
	"ilL-Line-Document": "illumenate_lighting.illumenate_lighting.portal.line_documents.query_conditions",
	"ilL-Configured-Group": "illumenate_lighting.illumenate_lighting.doctype.ill_configured_group.ill_configured_group.get_permission_query_conditions",
	"ilL-Portal-Message": "illumenate_lighting.illumenate_lighting.portal.conversations.get_permission_query_conditions",
	"ilL-Quote-Offer": "illumenate_lighting.illumenate_lighting.portal.offers.get_permission_query_conditions",
	"ilL-Quote-Request": "illumenate_lighting.illumenate_lighting.portal.quotes.get_permission_query_conditions",
	"ilL-Export-Job": "illumenate_lighting.illumenate_lighting.doctype.ill_export_job.ill_export_job.get_permission_query_conditions",
	"ilL-Project": "illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project.get_permission_query_conditions",
	"ilL-Project-Fixture-Schedule": "illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule.get_permission_query_conditions",
	"ilL-Document-Request": "illumenate_lighting.illumenate_lighting.doctype.ill_document_request.ill_document_request.get_permission_query_conditions",
	"ilL-Portal-User-Settings": "illumenate_lighting.illumenate_lighting.doctype.ill_portal_user_settings.ill_portal_user_settings.get_permission_query_conditions",
	"Sales Order": "illumenate_lighting.illumenate_lighting.dealer_permissions.sales_order_query_conditions",
}

has_permission = {
	"ilL-Order-Change": "illumenate_lighting.illumenate_lighting.portal.order_changes.has_permission",
	"ilL-Account-Request": "illumenate_lighting.illumenate_lighting.portal.accounts.has_permission",
	"ilL-Line-Document": "illumenate_lighting.illumenate_lighting.portal.line_documents.has_permission",
	"ilL-Configured-Group": "illumenate_lighting.illumenate_lighting.doctype.ill_configured_group.ill_configured_group.has_permission",
	"ilL-Portal-Message": "illumenate_lighting.illumenate_lighting.portal.conversations.has_permission",
	"ilL-Quote-Offer": "illumenate_lighting.illumenate_lighting.portal.offers.has_permission",
	"ilL-Export-Job": "illumenate_lighting.illumenate_lighting.doctype.ill_export_job.ill_export_job.has_permission",
	"File": "illumenate_lighting.illumenate_lighting.portal.private_file.portal_file_permission",
	"ilL-Portal-Upload": "illumenate_lighting.illumenate_lighting.portal.files.has_permission",
	"ilL-Quote-Request": "illumenate_lighting.illumenate_lighting.portal.quotes.has_permission",
	"ilL-Project": "illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project.has_permission",
	"ilL-Project-Fixture-Schedule": "illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule.has_permission",
	"ilL-Document-Request": "illumenate_lighting.illumenate_lighting.doctype.ill_document_request.ill_document_request.has_permission",
	"ilL-Portal-User-Settings": "illumenate_lighting.illumenate_lighting.doctype.ill_portal_user_settings.ill_portal_user_settings.has_permission",
	"Sales Order": "illumenate_lighting.illumenate_lighting.dealer_permissions.sales_order_has_permission",
}

# Website/Portal Permissions
has_website_permission = {
	"ilL-Project": "illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project.has_website_permission",
}

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"File": "illumenate_lighting.illumenate_lighting.portal.private_file.PortalFile",
	"Email Queue": "illumenate_lighting.illumenate_lighting.portal.email_queue.PortalEmailQueue",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Issue": {"validate": "illumenate_lighting.illumenate_lighting.portal.support.validate_owner"},
	"ilL-Project-Fixture-Schedule": {"on_update": "illumenate_lighting.illumenate_lighting.portal.drawing_impact.on_build_update"},
	"Work Order": {"before_submit": "illumenate_lighting.illumenate_lighting.portal.drawing_review.before_work_order_submit"},
	"Quotation": {
		# Only a submitted Quotation linked to an intake creates a portal offer.
		"before_submit": "illumenate_lighting.illumenate_lighting.portal.offers.before_submit",
		"on_submit": "illumenate_lighting.illumenate_lighting.portal.offers.on_submit",
		"on_cancel": ["illumenate_lighting.illumenate_lighting.portal.offers.on_cancel",
			"illumenate_lighting.illumenate_lighting.api.desk_configurator.on_quotation_cancel"],
	},
	"Sales Order": {
		"validate": "illumenate_lighting.illumenate_lighting.portal.order_review.validate_order",
		"before_update_after_submit": "illumenate_lighting.illumenate_lighting.portal.order_review.validate_order",
		"on_update": "illumenate_lighting.illumenate_lighting.portal.drawing_impact.on_build_update",
		"on_update_after_submit": "illumenate_lighting.illumenate_lighting.portal.drawing_impact.on_build_update",
		"before_submit": "illumenate_lighting.illumenate_lighting.portal.order_review.before_submit",
		"on_submit": [
			"illumenate_lighting.illumenate_lighting.portal.order_review.on_submit",
			"illumenate_lighting.illumenate_lighting.api.manufacturing_generator.on_sales_order_submit",
			"illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule.on_sales_order_submit",
		],
		"on_cancel": "illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule.on_sales_order_cancel",
		"on_trash": "illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule.on_sales_order_trash",
	},
	"Delivery Note": {
		"validate": "illumenate_lighting.illumenate_lighting.portal.commercial_lineage.validate",
		"on_submit": "illumenate_lighting.illumenate_lighting.portal.notifications.on_delivery_note_submit",
	},
	"Sales Invoice": {
		"validate": "illumenate_lighting.illumenate_lighting.portal.commercial_lineage.validate",
	},
	"Purchase Order": {
		"before_validate": "illumenate_lighting.illumenate_lighting.api.purchase_order.allow_blank_schedule_date",
	},
	# Webflow sync events for attribute doctypes
	"ilL-Attribute-CCT": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-CRI": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Certification": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Dimming Protocol": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Endcap Color": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Endcap Style": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Environment Rating": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Feed-Direction": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Finish": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-IP Rating": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Joiner Angle": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Joiner System": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Lead Time Class": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Leader Cable": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-LED Package": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Lens Appearance": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Lens Interface Type": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Mounting Method": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Output Level": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Output Voltage": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Power Feed Type": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Pricing Class": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-SDCM": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	"ilL-Attribute-Series": {
		"after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
	},
	# Webflow product and category sync events
	"ilL-Webflow-Product": {
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_product_update",
	},
	"ilL-Webflow-Category": {
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_category_update",
	},
	# Per-brand cache invalidation
	"ilL-Webflow-Brand": {
		"on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_brand_update",
		"on_trash": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_brand_update",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {"cron": {"*/5 * * * *": ["illumenate_lighting.illumenate_lighting.portal.outbox.dispatch", "illumenate_lighting.illumenate_lighting.portal.packet_jobs.recover"]}}

# Testing
# -------

# before_tests = "illumenate_lighting.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "illumenate_lighting.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "illumenate_lighting.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["illumenate_lighting.utils.before_request"]
after_request = ["illumenate_lighting.illumenate_lighting.utils.after_request"]

# Job Events
# ----------
# before_job = ["illumenate_lighting.utils.before_job"]
# after_job = ["illumenate_lighting.utils.after_job"]

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
# 	"illumenate_lighting.auth.validate"
# ]

# CORS Configuration
# ------------------
# CORS headers are injected by the after_request hook in
# illumenate_lighting.illumenate_lighting.utils.after_request
# Allowed origins are defined in ALLOWED_ORIGINS in that module.

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
