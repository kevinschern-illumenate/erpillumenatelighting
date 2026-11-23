"""Seed the two label rolls and the label templates (labels plan, Phase 1; reel PDR, R1).

Insert-if-missing only: once a record exists, staff own it (printer and paper names are
filled during warehouse setup), so a later migrate never resets their edits.
Light engine and Kit piece are seeded disabled; they turn on in Phase 2.
"""

import frappe

STOCKS = (
	{
		"stock_name": "1.5 x 2.5",
		"width_in": 2.5,
		"height_in": 1.5,
		"orientation": "Landscape",
		"printer_name": "Dymo 1.5x2.5",
		"print_order": 1,
	},
	{
		"stock_name": "4 x 6",
		"width_in": 4,
		"height_in": 6,
		"orientation": "Portrait",
		"printer_name": "Rollo 4x6",
		"print_order": 2,
	},
)

SMALL, LARGE = "1.5 x 2.5", "4 x 6"
TEMPLATES = (
	# name, layout, roll, source, applies to, quantity rule, packet order, auto, enabled
	("Work order", "work_order", SMALL, "Work Order", "All", "Per document", 10, 1, 1),
	("Product", "product", SMALL, "Work Order", "Not light engine", "Per unit", 20, 1, 1),
	("Light engine", "light_engine", SMALL, "Work Order", "Light engine", "Per unit", 20, 1, 0),
	("Kit piece", "kit_piece", SMALL, "Work Order", "Ship-in-pieces line", "Per kit piece", 30, 1, 0),
	("Packet checklist", "packet_4x6", LARGE, "Work Order", "All", "Per document", 90, 1, 1),
	("Reel", "reel", SMALL, "ilL-Reel", "All", "Per document", 50, 0, 1),
	("Reel ID tag", "reel_tag", SMALL, "ilL-Reel", "All", "Per document", 50, 0, 1),
	("Shelf", "location", SMALL, "ilL-Reel-Location", "All", "Per document", 50, 0, 1),
)


def execute():
	frappe.reload_doc("illumenate_lighting", "doctype", "ill_label_stock")
	frappe.reload_doc("illumenate_lighting", "doctype", "ill_label_template")
	for stock in STOCKS:
		if not frappe.db.exists("ilL-Label-Stock", stock["stock_name"]):
			frappe.get_doc({"doctype": "ilL-Label-Stock", "enabled": 1, **stock}).insert(
				ignore_permissions=True
			)
	for name, layout, roll, source, applies, rule, order, auto, enabled in TEMPLATES:
		if frappe.db.exists("ilL-Label-Template", name):
			continue
		frappe.get_doc(
			{
				"doctype": "ilL-Label-Template",
				"template_name": name,
				"layout": layout,
				"label_stock": roll,
				"source_doctype": source,
				"applies_to": applies,
				"quantity_rule": rule,
				"copies": 1,
				"packet_order": order,
				"auto_generate": auto,
				"enabled": enabled,
			}
		).insert(ignore_permissions=True)
