"""Fill only unmapped controller answers; preserve all staff mappings."""

import frappe

from illumenate_lighting.illumenate_lighting.portal.quiz_prefill import match_option


def execute():
	for key, doctype in (
		("control_method", "ilL-Attribute-Controller Type"),
		("controller_mounting", "ilL-Attribute-Mounting Type"),
	):
		if not frappe.db.exists("ilL-Finder-Question", key):
			continue
		doc = frappe.get_doc("ilL-Finder-Question", key)
		mapped = {r.option_value for r in doc.value_maps or []}
		candidates = [
			{"value": r.name, "label": r.label} for r in frappe.get_all(doctype, fields=["name", "label"])
		]
		changed = False
		for option in doc.options or []:
			if option.value in mapped or option.is_no_preference:
				continue
			value = match_option(option.value, candidates)
			if value:
				doc.append(
					"value_maps",
					{"option_value": option.value, "attribute_doctype": doctype, "attribute_value": value},
				)
				changed = True
		if changed:
			doc.save(ignore_permissions=True)
