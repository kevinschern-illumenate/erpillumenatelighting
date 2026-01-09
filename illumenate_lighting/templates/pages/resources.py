# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Resources Page Controller

Technical documentation, product catalogs, and downloadable resources.
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	"""Get context for the resources portal page."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	# Get spec sheets from fixture templates if available
	context.spec_sheets = []

	# Try to get product list from fixture templates
	if frappe.db.table_exists("ilL-Fixture-Template"):
		templates = frappe.get_all(
			"ilL-Fixture-Template",
			filters={"is_active": 1},
			fields=["template_code", "template_name", "description"],
			order_by="template_code",
			limit=20,
		)
		for t in templates:
			context.spec_sheets.append({
				"name": f"{t.template_code} - {t.template_name}",
				"description": t.description or _("Product specification sheet"),
				"url": f"/resources/specs/{t.template_code}",
				"size": "1.2 MB",
			})

	context.title = _("Resources")
	context.no_cache = 1

	return context
