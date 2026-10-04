"""Compatibility wrappers for existing logged-in quiz links."""

import frappe
from frappe.rate_limiter import rate_limit

from illumenate_lighting.illumenate_lighting.portal.product_finder import sessions


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60)
def save_session(product_type, recommended_template, quiz_answers):
	from illumenate_lighting.illumenate_lighting.portal.access import require_catalog_access

	sessions.require_user()
	require_catalog_access()
	return sessions.start(quiz_answers)


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=60, seconds=60)
def get_latest_session():
	from illumenate_lighting.illumenate_lighting.portal.access import require_catalog_access

	sessions.require_user()
	require_catalog_access()
	rows = frappe.get_all(sessions.DOCTYPE, filters={"user": frappe.session.user, "status": "Active"}, fields=["name", "session_token", "product_type", "recommended_template", "quiz_answers", "creation"], order_by="creation desc", limit=1)
	return rows[0] if rows else None
