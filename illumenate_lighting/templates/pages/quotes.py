import frappe

from illumenate_lighting.illumenate_lighting.portal.offers import OFFER_FILTERS, list_offers
from illumenate_lighting.illumenate_lighting.portal.quotes import REQUEST_FILTERS, list_requests

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/portal/quotes"
		raise frappe.Redirect
	form = frappe.form_dict
	status = form.get("status") if form.get("status") in OFFER_FILTERS else "all"
	search = str(form.get("search") or "").strip()[:140]
	context.update(list_offers(after=form.get("after"), status=status, search=search))
	context.status, context.search = status, search
	request_status = form.get("requests") if form.get("requests") in REQUEST_FILTERS else "open"
	page = max(1, frappe.utils.cint(form.get("requests_page")) or 1)
	requests = list_requests(page=page, status=request_status)
	context.requests, context.requests_page, context.more_requests = requests[:20], page, len(requests) > 20
	context.request_status = request_status
	context.title = "My Quotes"
	return context
