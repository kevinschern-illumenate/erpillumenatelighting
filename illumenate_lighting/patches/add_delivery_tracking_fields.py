"""Add Delivery Note carrier and tracking number fields (DESK-8).

Staff used Vehicle No for tracking numbers, which nobody thinks to fill in.
The portal and shipment emails read these first and fall back to
vehicle_no / lr_no for older notes.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Delivery Note": [
				{
					"fieldname": "ill_carrier",
					"fieldtype": "Select",
					"options": "\nUPS\nFedEx\nUSPS\nFreight\nOther",
					"label": "Carrier",
					"insert_after": "transporter_name",
					"allow_on_submit": 1,
				},
				{
					"fieldname": "ill_tracking_number",
					"fieldtype": "Data",
					"label": "Tracking Number",
					"insert_after": "ill_carrier",
					"allow_on_submit": 1,
					"description": "Shown to the dealer with a tracking link for UPS, FedEx and USPS.",
				},
			],
		},
		update=True,
	)
	frappe.db.commit()
