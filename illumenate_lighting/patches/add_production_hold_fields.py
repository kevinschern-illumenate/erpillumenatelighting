# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Hold, release and order-type fields for the Production Board (phase 3).

Hold Reason takes an order off the build queue: Hold for Release and Hold for
Confirmation are not released to production yet (the workbook's ESPR sheet, dated
by Likely Ship Date); Hold for Ship is built or buildable but the customer asked us
to hold it (HFS sheet, dated by the estimated ship date). Proforma / Will Call marks
orders that are paid before shipping or picked up. All are editable after submit.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	meta = frappe.get_meta("Sales Order")
	after = "ill_floor_notes" if meta.has_field("ill_floor_notes") else meta.fields[-1].fieldname
	create_custom_fields(
		{
			"Sales Order": [
				{
					"fieldname": "ill_hold_reason",
					"fieldtype": "Select",
					"label": "Hold Reason",
					"options": "\nHold for Release\nHold for Confirmation\nHold for Ship",
					"insert_after": after,
					"allow_on_submit": 1,
					"no_copy": 1,
					"in_standard_filter": 1,
				},
				{
					"fieldname": "ill_likely_ship_date",
					"fieldtype": "Date",
					"label": "Likely Ship Date",
					"insert_after": "ill_hold_reason",
					"allow_on_submit": 1,
					"no_copy": 1,
					"depends_on": "eval:in_list(['Hold for Release','Hold for Confirmation'], doc.ill_hold_reason)",
					"description": "When a held release is expected to ship; used for monthly release projections.",
				},
				{
					"fieldname": "ill_proforma_will_call",
					"fieldtype": "Select",
					"label": "Proforma / Will Call",
					"options": "\nProforma\nWill Call",
					"insert_after": "ill_likely_ship_date",
					"allow_on_submit": 1,
					"no_copy": 0,
				},
			],
		},
		update=True,
	)
