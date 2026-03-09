# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Resources Page Controller

Publicly available specification sheets from Webflow products.
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	"""Get context for the resources portal page."""
	context.spec_sheets = _get_webflow_spec_sheets()
	context.title = _("Specification Sheets")
	context.no_cache = 1
	return context


def _get_webflow_spec_sheets():
	"""Fetch all Spec Sheet documents linked to active Webflow products."""
	if not frappe.db.exists("DocType", "ilL-Webflow-Product"):
		return []

	products = frappe.get_all(
		"ilL-Webflow-Product",
		filters={"is_active": 1},
		fields=["name", "product_name", "product_slug", "short_description"],
		order_by="product_name",
	)

	spec_sheets = []
	for product in products:
		docs = frappe.get_all(
			"ilL-Child-Webflow-Document",
			filters={
				"parent": product.name,
				"parenttype": "ilL-Webflow-Product",
				"document_type": "Spec Sheet",
			},
			fields=["document_file", "document_title", "display_order"],
			order_by="display_order",
		)
		for doc in docs:
			spec_sheets.append({
				"product_name": product.product_name,
				"title": doc.document_title,
				"description": product.short_description or _("Product specification sheet"),
				"url": doc.document_file,
				"product_slug": product.product_slug,
			})

	return spec_sheets
