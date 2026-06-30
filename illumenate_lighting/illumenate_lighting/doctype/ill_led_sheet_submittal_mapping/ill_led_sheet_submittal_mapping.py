# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ilLLEDSheetSubmittalMapping(Document):
	pass


@frappe.whitelist()
def get_doctype_fields(doctype: str) -> list:
	if not doctype:
		return []
	allowed_doctypes = [
		"ilL-Configured-LED-Sheet",
		"ilL-LED-Sheet-Template",
		"ilL-Spec-LED-Sheet",
		"ilL-Project-Fixture-Schedule",
		"ilL-Project",
		"ilL-Child-Fixture-Schedule-Line",
	]
	if doctype not in allowed_doctypes:
		frappe.throw(_("DocType not allowed: {0}").format(doctype))
	meta = frappe.get_meta(doctype)
	excluded_fieldtypes = ["Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading"]
	excluded_fieldnames = ["name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "parent", "parentfield", "parenttype"]
	fields = []
	for field in meta.fields:
		if field.fieldtype in excluded_fieldtypes or field.fieldname in excluded_fieldnames or field.fieldname.startswith("_"):
			continue
		fields.append({"fieldname": field.fieldname, "label": field.label or field.fieldname, "fieldtype": field.fieldtype, "options": field.options if field.fieldtype == "Link" else None})
	fields.sort(key=lambda x: x["label"].lower())
	return fields
