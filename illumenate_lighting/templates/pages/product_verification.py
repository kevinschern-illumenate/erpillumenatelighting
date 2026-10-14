"""Dealer-readable verification decision and its scoped conversation."""

import frappe

from illumenate_lighting.illumenate_lighting.portal.web_guard import require_login

no_cache = 1


def get_context(context):
	require_login()
	from illumenate_lighting.illumenate_lighting.portal.product_finder.verification import DOCTYPE, can_access

	name = frappe.form_dict.get("name") or frappe.form_dict.get("request_name")
	doc = frappe.get_doc(DOCTYPE, name)
	if not can_access(doc):
		frappe.throw("Verification request unavailable", frappe.PermissionError)
	from illumenate_lighting.illumenate_lighting.portal.status import verification_status

	label, css = verification_status(doc.state)
	context.update(
		{"title": doc.name, "verification": doc, "status_label": label, "status_class": css, "no_cache": 1}
	)
	return context
