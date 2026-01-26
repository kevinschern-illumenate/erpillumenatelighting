# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ilLSpecSubmittalMapping(Document):
	pass


@frappe.whitelist()
def get_doctype_fields(doctype: str) -> list:
	"""
	Get all fields for a given DocType, excluding system fields.
	
	Returns a list of dicts with fieldname, label, and fieldtype.
	
	Args:
		doctype: The DocType name to get fields for
	
	Returns:
		list: List of field dicts
	"""
	if not doctype:
		return []
	
	# Validate doctype exists and is in allowed list
	allowed_doctypes = [
		"ilL-Configured-Fixture",
		"ilL-Fixture-Template",
		"ilL-Rel-Tape Offering",
		"ilL-Spec-Profile",
		"ilL-Spec-Lens",
		"ilL-Spec-Driver",
		"ilL-Project-Fixture-Schedule",
		"ilL-Project"
	]
	
	if doctype not in allowed_doctypes:
		frappe.throw(_("DocType not allowed: {0}").format(doctype))
	
	# Get DocType meta
	meta = frappe.get_meta(doctype)
	
	# Filter out system/internal fields
	excluded_fieldtypes = [
		"Section Break", "Column Break", "Tab Break", 
		"HTML", "Button", "Fold", "Heading"
	]
	
	excluded_fieldnames = [
		"name", "owner", "creation", "modified", "modified_by",
		"docstatus", "idx", "parent", "parentfield", "parenttype"
	]
	
	fields = []
	for field in meta.fields:
		if field.fieldtype in excluded_fieldtypes:
			continue
		if field.fieldname in excluded_fieldnames:
			continue
		if field.fieldname.startswith("_"):
			continue
		
		fields.append({
			"fieldname": field.fieldname,
			"label": field.label or field.fieldname,
			"fieldtype": field.fieldtype,
			"options": field.options if field.fieldtype == "Link" else None
		})
	
	# Sort by label
	fields.sort(key=lambda x: x["label"].lower())
	
	return fields
