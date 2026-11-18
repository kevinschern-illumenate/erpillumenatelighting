"""The Light Source row of a fixture template's Components (owner, 2026-11-13).

On every save the fixture template's Components table starts with one "Light Source" row per
LED tape it uses: the Template Name of the Tape/Neon template whose allowed tape specs hold the
tape specs of the fixture's allowed tape offerings (for ILL-SH01-SW, "High Density Static White
LED Tape"). When several Tape/Neon templates hold them, the ones for the fixture's own target
brand are used; the same name is listed once. The name goes in the row's Description (and
Webflow Title); the row has no Component Item. Rows typed by hand keep their order after it.
"""

import frappe

DOCTYPE = "ilL-Fixture-Template"
FIELD = "kit_components"
LIGHT_SOURCE = "Light Source"


def _brands(template):
	return [
		row.get("brand")
		for row in template.get("target_brands") or []
		if row.get("enabled") and row.get("brand")
	]


def names(template):
	"""The Light Source names for ``template``, sorted."""
	offerings = [
		row.get("tape_offering")
		for row in template.get("allowed_tape_offerings") or []
		if row.get("tape_offering")
	]
	if not offerings:
		return []
	specs = sorted(
		{
			spec
			for spec in frappe.get_all(
				"ilL-Rel-Tape Offering", filters={"name": ["in", offerings]}, pluck="tape_spec"
			)
			if spec
		}
	)
	if not specs:
		return []
	parents = sorted(
		set(
			frappe.get_all(
				"ilL-Child-Tape-Neon-Allowed-Spec",
				filters={"tape_spec": ["in", specs], "parenttype": "ilL-Tape-Neon-Template"},
				pluck="parent",
			)
		)
	)
	if not parents:
		return []
	brands = _brands(template)
	if brands:
		same_brand = set(
			frappe.get_all(
				"ilL-Child-Webflow-Brand-Target",
				filters={
					"parent": ["in", parents],
					"parenttype": "ilL-Tape-Neon-Template",
					"brand": ["in", brands],
					"enabled": 1,
				},
				pluck="parent",
			)
		)
		if same_brand:
			parents = sorted(same_brand)
	rows = frappe.get_all(
		"ilL-Tape-Neon-Template",
		filters={"name": ["in", parents]},
		fields=["name", "template_name"],
	)
	return sorted({(row.get("template_name") or row.get("name")).strip() for row in rows})


def refresh(template):
	"""Put the Light Source rows first. Called from template_listing.refresh_template."""
	meta = getattr(template, "meta", None)
	if template.doctype != DOCTYPE or (meta is not None and not meta.has_field(FIELD)):
		return
	others = [row for row in template.get(FIELD) or [] if row.get("component_type") != LIGHT_SOURCE]
	light_sources = [
		{"component_type": LIGHT_SOURCE, "component_description": name, "webflow_title": name}
		for name in names(template)
	]
	template.set(FIELD, light_sources + others)
	for idx, row in enumerate(template.get(FIELD) or [], 1):
		row.idx = idx
