import frappe

from illumenate_lighting.illumenate_lighting.portal.quotes import detail

no_cache = 1


def get_context(context):
	context.request = detail(frappe.form_dict.get("request"))
	context.title = context.request["name"]
	return context
