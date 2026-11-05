# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""The template part of the Webflow sync payload (plan 4.16 and 4.19, owner 2026-11-05).

The publication payload (``api/publication.py``) carries the product export as ``product``.
This adds ``template``: the fields the signed-off Webflow mapping takes from the template, read
straight from the template linked to the product. The n8n ``(ilL) Transform to Webflow
Format`` node shapes them into Webflow fields (kit grouping included). Nothing here is sent
for a product without a linked template.
"""

import frappe

CONFIGURATOR_KEYS = ("option_step", "option_label", "is_required", "depends_on_step", "allowed_values_json")
KIT_KEYS = ("component_type", "component_item", "component_image", "component_description")


def _rows(doc, fieldname):
	return sorted(doc.get(fieldname) or [], key=lambda row: row.get("idx") or 0)


def specification_rows(rows):
	"""Pure: label, value and order (the row's position in the table, from 1)."""
	return [
		{"spec_label": row.get("spec_label"), "spec_value": row.get("spec_value"), "order": order}
		for order, row in enumerate(rows, start=1)
	]


def configurator_rows(rows, include):
	"""Pure: the five configurator fields the owner signed off, or [] when the brand gets none."""
	if not include:
		return []
	return [{key: row.get(key) for key in CONFIGURATOR_KEYS} for row in rows]


def certification_rows(rows, codes):
	"""Pure: certification, its code, its badge image (the brand's, set on template save), and
	order (table position, from 1)."""
	rows = [row for row in rows if row.get("certification")]
	return [
		{
			"certification": row.get("certification"),
			"certification_code": codes.get(row.get("certification")) or row.get("certification"),
			"badge_image": row.get("badge_image") or None,
			"order": order,
		}
		for order, row in enumerate(rows, start=1)
	]


def price_per_foot(template):
	"""Pure: Price per Foot (MSRP), else Base Price (MSRP); None when neither is set."""
	for field in ("price_per_ft_msrp", "base_price_msrp"):
		value = template.get(field)
		if value:
			return float(value)
	return None


def template_section(product, include_configurator=True):
	"""The ``template`` part of the payload for a Webflow Product, or None without a template."""
	from illumenate_lighting.illumenate_lighting.webflow_product_rules import linked_template

	doctype, name = linked_template(product)
	if not doctype or not frappe.db.exists(doctype, name):
		return None
	template = frappe.get_doc(doctype, name)
	certifications = _rows(template, "certifications")
	names = [row.certification for row in certifications if row.get("certification")]
	codes = (
		{
			row["name"]: row["certification_code"]
			for row in frappe.get_all(
				"ilL-Attribute-Certification",
				filters={"name": ["in", names]},
				fields=["name", "certification_code"],
			)
		}
		if names
		else {}
	)
	series = template.get("series")
	return {
		"doctype": doctype,
		"name": name,
		"display_name": template.get("display_name") or template.get("template_name") or name,
		"sublabel": template.get("sublabel") or "",
		"dimensions_image": template.get("dimensions_image") or None,
		"spec_sheet_public_url": template.get("spec_sheet_public_url") or None,
		"series_name": (frappe.db.get_value("ilL-Attribute-Series", series, "series_name") or series)
		if series
		else "",
		"price_per_foot_msrp": price_per_foot(template),
		"specifications": specification_rows(_rows(template, "specifications")),
		"configurator": configurator_rows(_rows(template, "part_no_configurator"), include_configurator),
		"kit_components": [
			{key: row.get(key) for key in KIT_KEYS} for row in _rows(template, "kit_components")
		],
		"certifications": certification_rows(certifications, codes),
	}
