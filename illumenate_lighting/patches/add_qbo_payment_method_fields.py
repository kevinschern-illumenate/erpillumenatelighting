# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Add the QuickBooks payment method and reference number to Payment Entry.

The QBO payment sync fills them from the QBO Payment's PaymentMethodRef and
PaymentRefNum, and the ilL Sales Invoice print lists them in its payment history.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Payment Entry": [
				{
					"fieldname": "custom_qbo_payment_method",
					"fieldtype": "Data",
					"label": "QBO Payment Method",
					"description": "Payment method recorded in QuickBooks (e.g. Check, ACH, Visa). Shown on the invoice print.",
					"read_only": 1,
					"no_copy": 1,
					"allow_on_submit": 1,
					"depends_on": "custom_qbo_id",
					"insert_after": "custom_qbo_sync_note",
				},
				{
					"fieldname": "custom_qbo_payment_ref_num",
					"fieldtype": "Data",
					"label": "QBO Reference No",
					"description": "Reference number recorded on the QuickBooks payment (check or confirmation number). Shown on the invoice print.",
					"read_only": 1,
					"no_copy": 1,
					"allow_on_submit": 1,
					"depends_on": "custom_qbo_id",
					"insert_after": "custom_qbo_payment_method",
				},
			],
		},
		update=True,
	)
	frappe.db.commit()
