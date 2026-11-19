# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Let the Tape/Neon template show the layout in its doctype file (owner, 2026-11-19).

A field order saved through Customize Form (a Property Setter) kept Specifications &
Certifications, Spec Gallery and Configurator in the Details tab instead of Product Data.
The saved order and any saved field placements of this doctype are removed; other
customizations (labels, hidden fields and the like) stay.
"""

import frappe

DOCTYPE = "ilL-Tape-Neon-Template"
LAYOUT_PROPERTIES = ("field_order", "insert_after")


def execute():
	names = frappe.get_all(
		"Property Setter",
		filters={"doc_type": DOCTYPE, "property": ["in", LAYOUT_PROPERTIES]},
		pluck="name",
	)
	for name in names:
		frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)
	frappe.reload_doc("illumenate_lighting", "doctype", "ill_tape_neon_template", force=True)
	frappe.clear_cache(doctype=DOCTYPE)
