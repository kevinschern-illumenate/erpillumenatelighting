"""Seed the Terms and Conditions records and default print formats the ilL formats use.

Insert-only: a record or default that already exists is left as staff set it, so this
can run again without discarding edits.

- Terms and Conditions: "ilL Sales Terms" (quotes, orders, invoices), "ilL Retail Terms"
  (the MSRP formats) and "ilL Purchase Terms" (purchase orders, RFQs). The print formats
  fall back to these when a document has no terms of its own.
- Default print format for each DocType that has an ilL format and no default yet.
"""

import frappe

from illumenate_lighting.illumenate_lighting.print_terms import RECORDS

# DocType -> the ilL print format to make its default when it has none.
DEFAULT_FORMATS = {
	"Quotation": "ilL Quotation",
	"Sales Order": "ilL Sales Order",
	"Sales Invoice": "ilL Sales Invoice",
	"Delivery Note": "ilL Delivery Note",
	"Packing Slip": "ilL Packing List",
	"Pick List": "ilL Pick List",
	"Payment Entry": "ilL Payment Receipt",
	"Purchase Order": "ilL Purchase Order",
	"Request for Quotation": "ilL Request for Quotation",
	"Purchase Receipt": "ilL Receiving Report",
	"Purchase Invoice": "ilL Purchase Invoice",
	"Material Request": "ilL Material Request",
	"Work Order": "ilL Work Order Traveler",
	"ilL-Project-Fixture-Schedule": "ilL Fixture Schedule",
}


def execute():
	for name, (terms, selling, buying) in RECORDS.items():
		if frappe.db.exists("Terms and Conditions", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Terms and Conditions",
				"title": name,
				"terms": terms,
				"selling": selling,
				"buying": buying,
				"disabled": 0,
			}
		).insert(ignore_permissions=True)

	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for doctype, print_format in DEFAULT_FORMATS.items():
		if not frappe.db.exists("DocType", doctype) or not frappe.db.exists("Print Format", print_format):
			continue
		current = frappe.db.get_value(
			"Property Setter",
			{"doc_type": doctype, "property": "default_print_format", "doctype_or_field": "DocType"},
			"value",
		)
		if current and frappe.db.exists("Print Format", current):
			continue
		make_property_setter(doctype, None, "default_print_format", print_format, "Data", for_doctype=True)
	frappe.db.commit()
