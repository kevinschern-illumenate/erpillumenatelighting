# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal Resources Page Controller

Publicly available specification sheets from Webflow products.
"""

import re
from pathlib import Path

import frappe
from frappe import _

no_cache = 1


TOOLKIT_DIR = Path(__file__).resolve().parents[2] / "public" / "cad_toolkit"
TOOLKIT_URL = "/assets/illumenate_lighting/cad_toolkit/"
CATALOG_URL = "/api/method/illumenate_lighting.illumenate_lighting.system_design.api.download_cad_catalog"


def get_context(context):
	"""Get context for the resources portal page."""
	context.spec_sheets = _get_webflow_spec_sheets()
	context.drawing_tools = drawing_tools()
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

	# Plan 2.7: one documents query for every product, grouped in memory.
	docs_by_product = {}
	if products:
		for doc in frappe.get_all(
			"ilL-Child-Webflow-Document",
			filters={
				"parent": ["in", [product.name for product in products]],
				"parenttype": "ilL-Webflow-Product",
				"document_type": "Spec Sheet",
			},
			fields=["parent", "document_file", "document_title", "display_order"],
			order_by="display_order",
			limit_page_length=0,
		):
			docs_by_product.setdefault(doc.parent, []).append(doc)

	spec_sheets = []
	for product in products:
		for doc in docs_by_product.get(product.name, []):
			spec_sheets.append({
				"product_name": product.product_name,
				"title": doc.document_title,
				"description": product.short_description or _("Product specification sheet"),
				"url": doc.document_file,
				"product_slug": product.product_slug,
			})

	return spec_sheets


def drawing_tools():
	"""Draw-to-quote downloads for users the CAD rollout includes (implementation plan WP 1.12)."""
	from illumenate_lighting.illumenate_lighting.system_design.cad_access import enabled_for

	if not enabled_for():
		return None
	toolkit = toolkit_zip(TOOLKIT_DIR)
	return {
		"toolkit": {"url": TOOLKIT_URL + toolkit[0], "version": toolkit[1]} if toolkit else None,
		"catalog_url": CATALOG_URL,
		"checklist_url": TOOLKIT_URL + "ilLumenate-DXF-drafting-checklist.pdf",
	}


def toolkit_zip(folder):
	"""``(file name, version)`` of the newest committed toolkit bundle in ``folder``, or None."""
	found = []
	for path in Path(folder).glob("ilLumenate-cad-toolkit-*.zip"):
		match = re.fullmatch(r"ilLumenate-cad-toolkit-(\d+(?:\.\d+)*)\.zip", path.name)
		if match:
			found.append((tuple(int(part) for part in match.group(1).split(".")), path.name, match.group(1)))
	if not found:
		return None
	_version, name, text = max(found)
	return name, text
