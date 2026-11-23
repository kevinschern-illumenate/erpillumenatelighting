# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Move custom fields that sit above a doctype's first tab into its main tab.

These fields were created without ``insert_after``, so Frappe placed them before the
doctype's first Tab Break. Frappe then shows them in an extra, implicit "Details"
tab, which on Item and Customer sits next to the real "Details" tab.
"""

import frappe

# (doctype, fieldname, insert_after): each anchor is a standard field in the main tab.
MOVES = (
	("Item", "ill_cable_assembly_length_mm", "stock_uom"),  # Details tab
	("Customer", "ill_purchasing_contact", "territory"),  # Details tab
	("Work Order", "ill_configured_group", "sales_order"),  # Production Item tab
)


def execute():
	for doctype, fieldname, anchor in MOVES:
		name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname})
		if not name or not frappe.get_meta(doctype).has_field(anchor):
			continue
		field = frappe.get_doc("Custom Field", name)
		if field.insert_after == anchor:
			continue
		field.insert_after = anchor
		field.save(ignore_permissions=True)
	frappe.db.commit()
