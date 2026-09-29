# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Add User.ill_document_initials, printed after the date in spec sheet footers (e.g. 092926KS)."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"User": [
				{
					"fieldname": "ill_document_initials",
					"fieldtype": "Data",
					"label": "Document Initials",
					"insert_after": "last_name",
					"length": 8,
					"description": "Printed after the date code in spec sheet footers. "
					"Leave blank to use the initials of the full name.",
				},
			],
		},
		update=True,
	)
	frappe.db.commit()
