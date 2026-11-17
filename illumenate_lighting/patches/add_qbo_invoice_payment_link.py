# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Add the QuickBooks payment link to Sales Invoice.

The n8n invoice workflow reads the Invoice's shareable pay-now link from
QuickBooks (``include=invoiceLink``) and sends it with the id write-back, so
email templates and print formats can use ``{{ doc.custom_qbo_payment_link }}``.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Invoice": [
				{
					"fieldname": "custom_qbo_payment_link",
					"fieldtype": "Data",
					"options": "URL",
					"length": 500,
					"label": "QuickBooks Payment Link",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "custom_synced_from",
				}
			]
		},
		update=True,
	)
	frappe.db.commit()
