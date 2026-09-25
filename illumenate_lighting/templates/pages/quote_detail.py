import frappe

from illumenate_lighting.illumenate_lighting.portal.offers import detail

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/portal/quotes"
		raise frappe.Redirect
	context.offer = detail(frappe.form_dict.get("offer"))
	context.title = context.offer["name"]
	return context
