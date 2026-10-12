# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Add Customer.dealer_logo, the dealer's logo on System Designer title blocks (WP-3.7, plan H4.3).

Safe to run again: ``create_custom_fields(update=True)`` updates the field in place.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Customer": [
				{
					"fieldname": "dealer_logo",
					"fieldtype": "Attach Image",
					"label": "Dealer Logo",
					"description": "PNG or JPEG shown beside the ilLumenate logo on System Designer drawings.",
					"insert_after": "customer_group",
				},
			],
		},
		update=True,
	)
	frappe.db.commit()
