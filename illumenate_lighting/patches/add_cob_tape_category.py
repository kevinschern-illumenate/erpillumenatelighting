"""Offer COB Tape as a product category alongside LED Tape and LED Neon.

COB Tape templates configure exactly like LED Tape. Configured schedule lines
carry their category onto quotation, order, delivery and invoice rows, so those
rows' Configured Product Type choice needs COB Tape too; the commercial lineage
setup appends any missing choice without discarding site-maintained ones.

The dealer portal's add-line Product Category list is built from Item Groups,
so sites that sell LED Tape also get a COB Tape group beside it.
"""

import frappe


def execute():
	from illumenate_lighting.patches.b2b_commercial_lineage import execute as install_commercial_fields

	install_commercial_fields()
	ensure_cob_tape_item_group()
	frappe.db.commit()


def ensure_cob_tape_item_group():
	if frappe.db.exists("Item Group", "COB Tape") or not frappe.db.exists("Item Group", "LED Tape"):
		return
	parent = frappe.db.get_value("Item Group", "LED Tape", "parent_item_group") or "All Item Groups"
	frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": "COB Tape",
			"parent_item_group": parent,
			"is_group": 0,
		}
	).insert(ignore_permissions=True)
