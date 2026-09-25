import frappe

from illumenate_lighting.illumenate_lighting.portal.offers import list_offers

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/portal/quotes"
		raise frappe.Redirect
	context.update(list_offers(after=frappe.form_dict.get("after")))
	from illumenate_lighting.illumenate_lighting.portal.quotes import list_requests

	page = max(1, int(frappe.form_dict.get("requests_page") or 1))
	requests = list_requests(page=page)
	context.requests, context.requests_page, context.more_requests = requests[:20], page, len(requests) > 20
	context.title = "My Quotes"
	return context
