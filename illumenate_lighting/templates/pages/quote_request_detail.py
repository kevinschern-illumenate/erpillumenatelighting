import frappe

from illumenate_lighting.illumenate_lighting.portal.quotes import detail
from illumenate_lighting.illumenate_lighting.portal.web_guard import require_login

no_cache = 1


def get_context(context):
	require_login()
	context.request = detail(frappe.form_dict.get("request"))
	context.title = context.request["name"]
	return context
