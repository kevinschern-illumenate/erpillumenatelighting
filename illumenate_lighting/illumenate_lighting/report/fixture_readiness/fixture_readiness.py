# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""What each Linear Fixture template still needs for its spec sheet and Webflow sync.

Production's catalog data sits on the Webflow Product; the spec sheet and the sync read the
template (docs/superpowers/specs/2026-11-24-production-fixture-readiness-design.md). Each row
splits a template's gaps into what staff fill in, what ``web_listing_migration.
carry_listing_fields`` (or the link report) can copy from the product, and what the template's
save calculates (``template_listing.refresh_all_templates``). Read-only.
"""

import frappe
from frappe import _

TEMPLATE = "ilL-Fixture-Template"
PRODUCT = "ilL-Webflow-Product"
IN_SCOPE_STATUSES = ("Active", "Active + Live")


def _has(value):
	if isinstance(value, str):
		return bool(value.strip())
	return bool(value)


def _enabled_brand(rows):
	return any(row.get("enabled") for row in rows or [])


# (label, template has it, product has it): the product side says what can be copied.
# Target Brand and Product Category are seeded by the link report; the rest by
# carry_listing_fields. The hero image comes from the featured image, to be checked (owner).
HAND = (
	(
		"Target Brand",
		lambda t: _enabled_brand(t.get("target_brands")),
		lambda p: _enabled_brand(p.get("target_brands")),
	),
	("Display or Template Name", lambda t: _has(t.get("display_name")) or _has(t.get("template_name")), None),
	("Sublabel", lambda t: _has(t.get("sublabel")), lambda p: _has(p.get("sublabel"))),
	("Hero Image", lambda t: _has(t.get("hero_image")), lambda p: _has(p.get("featured_image"))),
	(
		"Dimensions Image",
		lambda t: _has(t.get("dimensions_image")),
		lambda p: _has(p.get("dimensions_image")),
	),
	(
		"Product Category",
		lambda t: _has(t.get("product_category")),
		lambda p: _has(p.get("product_category")),
	),
	("Certifications", lambda t: _has(t.get("certifications")), lambda p: _has(p.get("certifications"))),
)
COPIED_LABEL = {"Hero Image": "Hero Image (check)"}

# (label, template has it, inputs it is calculated from)
CALCULATED = (
	(
		"Specifications",
		lambda t: any(_has(r.get("spec_value")) for r in t.get("specifications") or []),
		("allowed_options",),
	),
	("Part No. Configurator", lambda t: _has(t.get("part_no_configurator")), ("allowed_options",)),
	("Output Options", lambda t: _has(t.get("output_options")), ("allowed_tape_offerings",)),
	("Delivered Lumens", lambda t: _has(t.get("delivered_lumens")), ("allowed_tape_offerings",)),
	(
		"Compatible Power Supplies",
		lambda t: _has(t.get("compatible_power_supplies")),
		("allowed_tape_offerings",),
	),
)
INPUT_LABELS = {"allowed_options": "Allowed Options", "allowed_tape_offerings": "Allowed Tape Offerings"}
OPTIONAL = (("Spec Gallery", lambda t: _has(t.get("spec_gallery"))),)


def readiness(template, listing):
	"""Pure: the gaps of one template (dict), given its Webflow Product (dict) or None."""
	fill_in, from_product, calculated, optional = [], [], [], []
	if not listing:
		fill_in.append("Webflow Product link")
	for label, has, product_has in HAND:
		if has(template):
			continue
		if listing and product_has and product_has(listing):
			from_product.append(COPIED_LABEL.get(label, label))
		else:
			fill_in.append(label)
	# The link is listed first; keep the rest in field order.
	fill_in.sort(key=lambda label: label != "Webflow Product link")
	for label, has, inputs in CALCULATED:
		if has(template):
			continue
		missing = [INPUT_LABELS[field] for field in inputs if not _has(template.get(field))]
		calculated.append(f"{label} (needs {', '.join(missing)})" if missing else label)
	optional = [label for label, has in OPTIONAL if not has(template)]
	return {
		"fill_in": fill_in,
		"from_product": from_product,
		"calculated": calculated,
		"optional": optional,
		"ready": not (fill_in or from_product or calculated),
	}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"label": _("Template"),
			"fieldname": "template",
			"fieldtype": "Link",
			"options": TEMPLATE,
			"width": 150,
		},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
		{
			"label": _("Webflow Product"),
			"fieldname": "webflow_product",
			"fieldtype": "Link",
			"options": PRODUCT,
			"width": 140,
		},
		{"label": _("Ready"), "fieldname": "ready", "fieldtype": "Check", "width": 70},
		{"label": _("Fill In"), "fieldname": "fill_in", "fieldtype": "Data", "width": 260},
		{"label": _("From the Product"), "fieldname": "from_product", "fieldtype": "Data", "width": 260},
		{"label": _("Calculated on Save"), "fieldname": "calculated", "fieldtype": "Data", "width": 300},
		{"label": _("Optional"), "fieldname": "optional", "fieldtype": "Data", "width": 120},
		{"label": _("Spec Sheet Check"), "fieldname": "spec_sheet_check", "fieldtype": "Data", "width": 260},
	]


def get_data(filters):
	from illumenate_lighting.illumenate_lighting.spec_sheet_check import check

	rows = frappe.get_all(
		TEMPLATE,
		fields=["name", "product_status", "webflow_product"],
		order_by="name asc",
		limit_page_length=0,
	)
	data = []
	for row in rows:
		if row.product_status not in IN_SCOPE_STATUSES and not row.webflow_product:
			continue
		doc = frappe.get_doc(TEMPLATE, row.name)
		listing = None
		if row.webflow_product and frappe.db.exists(PRODUCT, row.webflow_product):
			listing = frappe.get_doc(PRODUCT, row.webflow_product).as_dict()
		result = readiness(doc.as_dict(), listing)
		# The spec sheet's own check, as a cross-check of "Ready".
		spec_missing = check(doc)["missing"]
		ready = result["ready"] and not spec_missing
		if filters.get("not_ready_only") and ready:
			continue
		data.append(
			{
				"template": row.name,
				"status": row.product_status,
				"webflow_product": row.webflow_product,
				"ready": 1 if ready else 0,
				"fill_in": ", ".join(result["fill_in"]),
				"from_product": ", ".join(result["from_product"]),
				"calculated": ", ".join(result["calculated"]),
				"optional": ", ".join(result["optional"]),
				"spec_sheet_check": "; ".join(spec_missing),
			}
		)
	return data
