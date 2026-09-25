import frappe

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect
	from illumenate_lighting.illumenate_lighting.portal.support import detail

	context.ticket = detail(frappe.form_dict.get("ticket_name"))
	context.thread_type, context.thread_name = "Issue", context.ticket["name"]
	context.title = context.ticket["subject"]
	context.no_cache = 1
