# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Purchase Invoice "Vendor Order / Ack #", carried from the Purchase Order.

The Purchase Order field is no_copy, so ERPNext's Make Purchase Invoice never maps it;
``api.purchasing.fill_invoice_vendor_order`` fills it on validate instead. This adds the
field next to the supplier invoice number and fills it on existing invoices.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from illumenate_lighting.illumenate_lighting.api.purchasing import VENDOR_ORDER_FIELD, vendor_order_numbers


def _after(doctype, preferred):
	meta = frappe.get_meta(doctype)
	return preferred if meta.has_field(preferred) else meta.fields[-1].fieldname


def execute():
	create_custom_fields(
		{
			"Purchase Invoice": [
				{
					"fieldname": VENDOR_ORDER_FIELD,
					"fieldtype": "Data",
					"label": "Vendor Order / Ack #",
					"insert_after": _after("Purchase Invoice", "bill_date"),
					"description": "From the Purchase Order when left blank.",
					"allow_on_submit": 1,
					"no_copy": 1,
					"in_standard_filter": 1,
				}
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Purchase Invoice")
	if not frappe.get_meta("Purchase Order").has_field(VENDOR_ORDER_FIELD):
		return

	invoices = frappe.get_all(
		"Purchase Invoice",
		filters={"docstatus": ["<", 2], VENDOR_ORDER_FIELD: ["is", "not set"]},
		pluck="name",
	)
	for name in invoices:
		orders = frappe.get_all(
			"Purchase Invoice Item",
			filters={"parent": name, "parenttype": "Purchase Invoice"},
			pluck="purchase_order",
			order_by="idx asc",
		)
		value = vendor_order_numbers(orders)
		if value:
			frappe.db.set_value("Purchase Invoice", name, VENDOR_ORDER_FIELD, value, update_modified=False)
	frappe.db.commit()
