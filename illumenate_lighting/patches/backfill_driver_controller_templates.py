# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Backfill single-variant Driver/Controller templates for existing products.

Driver and Controller Webflow products historically pointed at a single
``driver_spec`` / ``controller_spec``. The configurator introduced
``ilL-Driver-Template`` / ``ilL-Controller-Template``, which hold a table of
selectable variants.

This patch creates a one-variant template for every existing Driver/Controller
product that has a spec but no template yet, and links it via the new
``driver_template`` / ``controller_template`` field. The original ``*_spec``
link is deliberately left in place so Webflow spec enrichment keeps behaving
exactly as before; nothing becomes configurable until someone ticks
``is_configurable`` and adds allowed options.

Idempotent: products that already have a template link are skipped, and an
existing template with the derived code is reused rather than recreated.
"""

import re

import frappe

KINDS = {
	"Driver": {
		"product_field": "driver_template",
		"spec_field": "driver_spec",
		"template_doctype": "ilL-Driver-Template",
		"variant_spec_field": "driver_spec",
	},
	"Controller": {
		"product_field": "controller_template",
		"spec_field": "controller_spec",
		"template_doctype": "ilL-Controller-Template",
		"variant_spec_field": "controller_spec",
	},
}


def execute():
	for kind, cfg in KINDS.items():
		if not frappe.db.has_column("ilL-Webflow-Product", cfg["product_field"]):
			continue

		products = frappe.get_all(
			"ilL-Webflow-Product",
			filters={
				"product_type": kind,
				cfg["spec_field"]: ["is", "set"],
				# "is not set" -> ifnull(col, '') = '', which also matches NULL.
				# An `in ['', None]` filter renders as `IN ('', NULL)` and silently
				# skips every NULL row.
				cfg["product_field"]: ["is", "not set"],
			},
			fields=["name", "product_name", "product_slug", "series", cfg["spec_field"]],
		)

		for product in products:
			try:
				_backfill_product(kind, cfg, product)
			except Exception as exc:
				frappe.log_error(
					title=f"Backfill {kind} template failed",
					message=f"Product {product.name}: {type(exc).__name__}: {exc}",
				)


def _backfill_product(kind: str, cfg: dict, product: dict) -> None:
	spec_name = product.get(cfg["spec_field"])
	if not spec_name:
		return

	template_code = _derive_template_code(product)
	if not template_code:
		return

	if frappe.db.exists(cfg["template_doctype"], template_code):
		template_name = template_code
	else:
		template = frappe.get_doc({
			"doctype": cfg["template_doctype"],
			"template_code": template_code,
			"template_name": product.get("product_name") or template_code,
			"is_active": 1,
			"series": product.get("series"),
			"webflow_product": product["name"],
			"variants": [{
				cfg["variant_spec_field"]: spec_name,
				"is_default": 1,
				"is_active": 1,
			}],
		})
		template.insert(ignore_permissions=True)
		template_name = template.name

	frappe.db.set_value(
		"ilL-Webflow-Product",
		product["name"],
		cfg["product_field"],
		template_name,
		update_modified=False,
	)


def _derive_template_code(product: dict) -> str:
	"""Build a stable, unique-per-product template code from the product slug."""
	source = product.get("product_slug") or product.get("name") or ""
	code = re.sub(r"[^A-Za-z0-9]+", "-", source).strip("-").upper()
	return code[:140]
