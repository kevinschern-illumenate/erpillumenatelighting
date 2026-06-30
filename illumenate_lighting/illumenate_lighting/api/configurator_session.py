# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe


@frappe.whitelist()
def save_session(product_type, recommended_template, quiz_answers):
	"""Save quiz session for a logged-in dealer. Returns session_token."""
	doc = frappe.get_doc({
		"doctype": "ilL-Configurator-Session",
		"product_type": product_type,
		"recommended_template": recommended_template,
		"quiz_answers": quiz_answers,
		"status": "Active",
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc.session_token


@frappe.whitelist()
def get_latest_session():
	"""Return the most recent Active session for the current user."""
	rows = frappe.get_all(
		"ilL-Configurator-Session",
		filters={"user": frappe.session.user, "status": "Active"},
		fields=["name", "session_token", "product_type", "recommended_template", "quiz_answers", "creation"],
		order_by="creation desc",
		limit=1,
	)
	return rows[0] if rows else None
