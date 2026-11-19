# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Spec & Power fields on Quotation / Sales Order rows, and the panel under the Items grid.

A catalog LED Tape, Neon or Sheet row carries its spec (voltage, W/ft or W/sq ft, max
run), its length or area and its load (``api/line_power.py``). The values are derived on
every save, so they are read-only and allowed after submit (Sales Order "Update Items"
and the backfill rewrite them). The custom print formats render ``ill_lp_summary``
themselves, so every field is hidden from the standard print.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CHILD_DOCTYPES = ("Quotation Item", "Sales Order Item")
PARENT_DOCTYPES = ("Quotation", "Sales Order")


def _row_fields(insert_after):
	fields = [
		{
			"fieldname": "ill_lp_section",
			"fieldtype": "Section Break",
			"label": "Spec & Power",
			"collapsible": 1,
			"insert_after": insert_after,
		},
		{"fieldname": "ill_lp_summary", "fieldtype": "Small Text", "label": "Spec & Power"},
		{"fieldname": "ill_lp_note", "fieldtype": "Data", "label": "Spec Note"},
		{
			"fieldname": "ill_lp_watts",
			"fieldtype": "Float",
			"label": "Load (W)",
			"precision": "1",
			"in_list_view": 1,
			"columns": 1,
		},
		{"fieldname": "ill_lp_length_ft", "fieldtype": "Float", "label": "Length (ft)", "precision": "2"},
		{"fieldname": "ill_lp_area_sqft", "fieldtype": "Float", "label": "Area (sq ft)", "precision": "2"},
		{"fieldname": "ill_lp_column", "fieldtype": "Column Break"},
		{
			"fieldname": "ill_lp_family",
			"fieldtype": "Select",
			"label": "Spec Family",
			"options": "\nTape\nSheet",
		},
		{"fieldname": "ill_lp_input_voltage", "fieldtype": "Data", "label": "Input Voltage"},
		{"fieldname": "ill_lp_watts_per_ft", "fieldtype": "Float", "label": "W/ft"},
		{"fieldname": "ill_lp_max_run_ft", "fieldtype": "Float", "label": "Max Run (ft)"},
		{"fieldname": "ill_lp_max_run_double_ft", "fieldtype": "Float", "label": "Max Run, Double Feed (ft)"},
		{"fieldname": "ill_lp_watts_per_sqft", "fieldtype": "Float", "label": "W/sq ft"},
		{"fieldname": "ill_lp_watts_per_sheet", "fieldtype": "Float", "label": "W/Sheet"},
		{"fieldname": "ill_lp_max_sqft_per_100w", "fieldtype": "Float", "label": "Max sq ft per 100 W"},
		{
			"fieldname": "ill_lp_spec_doctype",
			"fieldtype": "Link",
			"label": "Spec DocType",
			"options": "DocType",
			"hidden": 1,
		},
		{
			"fieldname": "ill_lp_spec",
			"fieldtype": "Dynamic Link",
			"label": "Spec",
			"options": "ill_lp_spec_doctype",
		},
	]
	previous = None
	for field in fields:
		if previous:
			field["insert_after"] = previous
		previous = field["fieldname"]
		field["print_hide"] = 1
		if field["fieldtype"] not in ("Section Break", "Column Break"):
			field.update({"read_only": 1, "allow_on_submit": 1, "no_copy": 0})
	return fields


def _row_anchor(doctype):
	meta = frappe.get_meta(doctype)
	if meta.has_field("ill_schedule_line_id"):
		return "ill_schedule_line_id"
	ours = {field["fieldname"] for field in _row_fields("x")}
	return [field.fieldname for field in meta.fields if field.fieldname not in ours][-1]


def execute():
	fields = {doctype: _row_fields(_row_anchor(doctype)) for doctype in CHILD_DOCTYPES}
	for doctype in PARENT_DOCTYPES:
		fields[doctype] = [
			{
				"fieldname": "ill_lp_panel",
				"fieldtype": "HTML",
				"label": "Tape / Neon / Sheet Power",
				"insert_after": "items",
				"print_hide": 1,
			}
		]
	create_custom_fields(fields, update=True)
	frappe.clear_cache()
