import frappe

from illumenate_lighting.illumenate_lighting.portal.offers import detail
from illumenate_lighting.illumenate_lighting.portal.web_guard import require_login

no_cache = 1


def get_context(context):
	require_login()
	context.offer = detail(frappe.form_dict.get("offer"))
	context.title = context.offer["name"]
	return context
