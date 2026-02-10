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
# app_include_css = "/assets/illumenate_lighting/css/illumenate_lighting.css"
# app_include_js = "/assets/illumenate_lighting/js/illumenate_lighting.js"

# include js, css files in header of web template
web_include_css = "/assets/illumenate_lighting/css/portal.css"
web_include_js = "/assets/illumenate_lighting/js/portal.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "illumenate_lighting/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"Sales Order": "public/js/sales_order.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
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
	{"from_route": "/portal/configure-webflow", "to_route": "configure_webflow"},
	{"from_route": "/portal/configure-webflow/<template>", "to_route": "configure_webflow"},
	{"from_route": "/portal/edit_fixture", "to_route": "edit_fixture"},

	# Orders
	{"from_route": "/portal/orders", "to_route": "orders"},
	{"from_route": "/portal/orders/<order>", "to_route": "order_detail"},

	# Drawings
	{"from_route": "/portal/drawings", "to_route": "drawings"},
	{"from_route": "/portal/drawings/<request>", "to_route": "drawing_detail"},

	# Resources
	{"from_route": "/portal/resources", "to_route": "resources"},

	# Support
	{"from_route": "/portal/support", "to_route": "support"},
	{"from_route": "/portal/support/faq", "to_route": "support"},

	# Account
	{"from_route": "/portal/account", "to_route": "account"},
	{"from_route": "/portal/account/notifications", "to_route": "account"},
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
	# Job Title Master for CRM Lead integration
	{"dt": "ilL-Job-Title-Master", "filters": [["is_active", "=", 1]]},
	# Custom fields for CRM Lead and other DocTypes
	{"dt": "Custom Field"},
	# Email campaign fixtures for newsletter automation
	{"dt": "Campaign", "filters": [["name", "in", ["Newsletter Welcome"]]]},
	{"dt": "Email Template", "filters": [["name", "in", ["Newsletter Welcome Email"]]]},
	{"dt": "Campaign Email Schedule", "filters": [["email_template", "in", ["Newsletter Welcome Email"]]]},
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
	"ilL-Project": "illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project.get_permission_query_conditions",
	"ilL-Project-Fixture-Schedule": "illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule.get_permission_query_conditions",
	"ilL-Document-Request": "illumenate_lighting.illumenate_lighting.doctype.ill_document_request.ill_document_request.get_permission_query_conditions",
}

has_permission = {
	"ilL-Project": "illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project.has_permission",
	"ilL-Project-Fixture-Schedule": "illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule.has_permission",
	"ilL-Document-Request": "illumenate_lighting.illumenate_lighting.doctype.ill_document_request.ill_document_request.has_permission",
}

# Website/Portal Permissions
has_website_permission = {
	"ilL-Project": "illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project.has_website_permission",
}

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Sales Order": {
		"on_submit": "illumenate_lighting.illumenate_lighting.api.manufacturing_generator.on_sales_order_submit",
	},
	# CRM Lead events for newsletter automation
	"CRM Lead": {
		"after_insert": "illumenate_lighting.illumenate_lighting.server_scripts.auto_enroll_newsletter_lead.auto_enroll_lead_in_newsletter_campaign",
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
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"hourly": [
		"erpnext.crm.doctype.email_campaign.email_campaign.send_email_to_leads_or_contacts",
	],
	"daily": [
		"erpnext.crm.doctype.email_campaign.email_campaign.send_email_to_leads_or_contacts",
	],
}

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
# after_request = ["illumenate_lighting.utils.after_request"]

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
# Configure CORS for Webflow domains
website_cors = {
	"allowed_origins": [
		"https://www.illumenatelighting.com",
		"https://illumenatelighting.webflow.io",
	],
	"allowed_methods": ["GET", "POST", "OPTIONS"],
	"allowed_headers": ["Content-Type", "Authorization"],
	"expose_headers": ["Content-Length"],
	"max_age": 86400,
}

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
