# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Add Company.custom_invoice_payment_instructions, read by the ilL Sales Invoice print format.

The field was only listed in the module-level custom_field.json, which Frappe's
fixture sync never reads, so sites never got the column.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Company": [
				{
					"fieldname": "custom_invoice_payment_instructions",
					"fieldtype": "Small Text",
					"label": "Invoice Payment Instructions",
					"insert_after": "tax_id",
					"description": "Remittance instructions displayed on sales invoices",
				},
			],
		},
		update=True,
	)
	frappe.db.commit()
