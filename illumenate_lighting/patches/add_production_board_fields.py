# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Floor fields for the Production Board (Command Center Manufacturing view).

Sales Order: a status override (Paint, Held, Waiting for parts) for states the ERP
cannot see yet, and floor notes shown in the board's queue. Delivery Note: why a
shipment was late and whether the warehouse was at fault, for the on-time %. All
are editable after submit.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def _after(doctype, preferred):
	meta = frappe.get_meta(doctype)
	return preferred if meta.has_field(preferred) else meta.fields[-1].fieldname


def execute():
	create_custom_fields(
		{
			"Sales Order": [
				{
					"fieldname": "ill_production_status_override",
					"fieldtype": "Select",
					"label": "Production Status Override",
					"options": "\nPaint\nHeld\nWaiting for parts",
					"insert_after": _after("Sales Order", "ill_estimated_ship_date"),
					"allow_on_submit": 1,
					"no_copy": 1,
					"description": "Leave blank: the board works status out from Work Orders, stock and deliveries.",
				},
				{
					"fieldname": "ill_floor_notes",
					"fieldtype": "Small Text",
					"label": "Floor Notes",
					"insert_after": "ill_production_status_override",
					"allow_on_submit": 1,
					"no_copy": 1,
				},
			],
			"Delivery Note": [
				{
					"fieldname": "ill_shipping_review_section",
					"fieldtype": "Section Break",
					"label": "On-Time Review",
					"collapsible": 1,
					"insert_after": frappe.get_meta("Delivery Note").fields[-1].fieldname,
				},
				{
					"fieldname": "ill_not_warehouse_fault",
					"fieldtype": "Check",
					"label": "Late, Not Warehouse Fault",
					"insert_after": "ill_shipping_review_section",
					"allow_on_submit": 1,
					"no_copy": 1,
					"description": "Counts as on time on the production board.",
				},
				{
					"fieldname": "ill_late_reason",
					"fieldtype": "Small Text",
					"label": "Why Was This Late",
					"insert_after": "ill_not_warehouse_fault",
					"allow_on_submit": 1,
					"no_copy": 1,
				},
			],
		},
		update=True,
	)
