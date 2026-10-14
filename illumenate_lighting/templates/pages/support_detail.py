import frappe

from illumenate_lighting.illumenate_lighting.portal.web_guard import require_login

no_cache = 1


def get_context(context):
	require_login()
	from illumenate_lighting.illumenate_lighting.portal.support import detail

	context.ticket = detail(frappe.form_dict.get("ticket_name"))
	context.thread_type, context.thread_name = "Issue", context.ticket["name"]
	context.title = context.ticket["subject"]
	context.no_cache = 1
