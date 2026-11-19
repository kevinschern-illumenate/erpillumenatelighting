# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Supplier Part Number and Supplier Description on Purchase Order and RFQ lines.

ERPNext keeps ``supplier_part_no`` on both line doctypes but hides it and makes it read-only.
It is shown and made editable, and ``ill_supplier_description`` is added beside it. Line values
are saved to the Item's Supplier Items row for the document's supplier (api/supplier_parts.py).
On an RFQ that lists more than one supplier both are read-only: the Supplier Parts button sets
them per supplier.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

LINE_DOCTYPES = ("Purchase Order Item", "Request for Quotation Item")
SEVERAL_SUPPLIERS = "eval:(parent.suppliers || []).length > 1"
DESCRIPTIONS = {
	"Purchase Order Item": "Saved to the Item for this supplier when the purchase order is saved.",
	"Request for Quotation Item": (
		"Saved to the Item for this RFQ's supplier. With more than one supplier, use Supplier Parts."
	),
}


def _description_field(doctype):
	field = {
		"fieldname": "ill_supplier_description",
		"fieldtype": "Small Text",
		"label": "Supplier Description",
		"insert_after": "supplier_part_no",
		"description": DESCRIPTIONS[doctype],
	}
	if doctype == "Request for Quotation Item":
		field["read_only_depends_on"] = SEVERAL_SUPPLIERS
		# ERPNext prints an RFQ per supplier from the Item; the line copy is not printed.
		field["print_hide"] = 1
	return field


def execute():
	fields = {}
	for doctype in LINE_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype, cached=False)
		if meta.has_field("supplier_part_no"):
			make_property_setter(doctype, "supplier_part_no", "hidden", "0", "Check")
			make_property_setter(doctype, "supplier_part_no", "read_only", "0", "Check")
			make_property_setter(doctype, "supplier_part_no", "description", DESCRIPTIONS[doctype], "Text")
			if doctype == "Request for Quotation Item":
				make_property_setter(
					doctype, "supplier_part_no", "read_only_depends_on", SEVERAL_SUPPLIERS, "Code"
				)
		fields[doctype] = [_description_field(doctype)]
	if fields:
		create_custom_fields(fields, update=True)
	frappe.clear_cache()
