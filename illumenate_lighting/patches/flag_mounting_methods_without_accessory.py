# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Flag the mounting methods that ship without a separate mounting accessory.

Drywall is mudded in and Direct Surface Mount screws through the profile, so
neither has an accessory kit. Runs after model sync adds the
``no_accessory_required`` field. Only sets the flag; staff clear it by hand.
"""

import frappe

DOCTYPE = "ilL-Attribute-Mounting Method"
# Matched case-insensitively against the label (the record name).
METHODS_WITHOUT_ACCESSORY = ("drywall", "direct surface mount")


def execute():
	if not frappe.get_meta(DOCTYPE).has_field("no_accessory_required"):
		return
	for name in frappe.get_all(DOCTYPE, pluck="name"):
		if str(name).strip().lower() in METHODS_WITHOUT_ACCESSORY:
			frappe.db.set_value(DOCTYPE, name, "no_accessory_required", 1, update_modified=False)
