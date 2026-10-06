# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Make the QBO link fields safe for the n8n sync.

- allow_on_submit on the submittable doctypes: n8n writes custom_qbo_id back
  after the Sales Invoice is submitted, and Frappe rejects changing any other
  field on a submitted document ("Not allowed to change QBO ID after submission").
- no_copy everywhere: Duplicate / Amend must not carry the QBO ID, or two
  ERPNext documents point at one QBO record and payments land on the wrong one.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

SUBMITTABLE = {
	"Sales Invoice": "customer",
	"Purchase Invoice": "supplier",
	"Payment Entry": "payment_type",
}
MASTERS = {
	"Customer": "customer_name",
	"Supplier": "supplier_name",
}


def _fields(insert_after, submittable):
	extra = {"no_copy": 1, "read_only": 1}
	if submittable:
		extra["allow_on_submit"] = 1
	return [
		{
			"fieldname": "custom_qbo_id",
			"fieldtype": "Data",
			"label": "QBO ID",
			"insert_after": insert_after,
			**extra,
		},
		{
			"fieldname": "custom_synced_from",
			"fieldtype": "Data",
			"label": "Synced From",
			"insert_after": "custom_qbo_id",
			**extra,
		},
	]


def execute():
	custom_fields = {dt: _fields(after, True) for dt, after in SUBMITTABLE.items()}
	custom_fields.update({dt: _fields(after, False) for dt, after in MASTERS.items()})
	create_custom_fields(custom_fields, update=True)
	frappe.db.commit()
