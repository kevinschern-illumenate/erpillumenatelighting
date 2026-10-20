# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Mark the QuickBooks id fields on Sales Invoice and Purchase Invoice "no copy".

Without it an amended invoice copies its cancelled original's QuickBooks id:
the hourly bill resend skips it and linking it fails with ``qbo_id_conflict``.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def _fields(party_field):
	return [
		{
			"fieldname": "custom_qbo_id",
			"fieldtype": "Data",
			"label": "QBO ID",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": party_field,
		},
		{
			"fieldname": "custom_synced_from",
			"fieldtype": "Data",
			"label": "Synced From",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "custom_qbo_id",
		},
	]


def execute():
	create_custom_fields(
		{
			"Sales Invoice": _fields("customer"),
			"Purchase Invoice": _fields("supplier"),
		},
		update=True,
	)
	frappe.db.commit()
