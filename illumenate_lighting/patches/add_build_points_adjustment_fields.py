# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Floor corrections to a Sales Order's build counts (production board order queue).

The counted totals come from the pinned builds. When an order is harder than its
configured builds show (an extra 3C run, another jumper), the floor corrects the
totals from the Command Center queue. The difference is stored here so recounts
keep it; the order's count fields then hold the corrected totals.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	meta = frappe.get_meta("Sales Order")
	after = "ill_build_points_warnings"
	if not meta.has_field(after):
		after = meta.fields[-1].fieldname
	create_custom_fields(
		{
			"Sales Order": [
				{
					"fieldname": "ill_build_points_adjustments",
					"fieldtype": "Code",
					"options": "JSON",
					"label": "Build Count Adjustments",
					"insert_after": after,
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"print_hide": 1,
					"description": "Set from the production board order queue: what was added to (or taken off) the counted totals.",
				},
				{
					"fieldname": "ill_build_points_adjust_note",
					"fieldtype": "Small Text",
					"label": "Why the Build Counts Were Adjusted",
					"insert_after": "ill_build_points_adjustments",
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"print_hide": 1,
				},
			]
		},
		update=True,
	)
