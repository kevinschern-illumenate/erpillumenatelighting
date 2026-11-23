"""Reel tracking fields on Item (reel PDR, R1 count kit).

Defaults are the agreed ones (Nov 22): scrap line 2 ft, smallest useful piece 4 ft,
remnant line 10 ft. The standard reel length is set per item during count setup:
100 ft for indoor tape, 50 ft for outdoor (no Item field says indoor or outdoor yet).
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

SHOWN = "eval:doc.ill_reel_tracked"


def execute():
	create_custom_fields(
		{
			"Item": [
				{
					"fieldname": "ill_reel_section",
					"fieldtype": "Section Break",
					"label": "Reel Tracking (tape and neon)",
					"insert_after": "valuation_method",
					"collapsible": 1,
				},
				{
					"fieldname": "ill_reel_tracked",
					"fieldtype": "Check",
					"label": "Reel Tracked",
					"insert_after": "ill_reel_section",
					"description": "Each reel of this item has an ID and a tracked length (ilL-Reel). Turn on as its reels are counted.",
				},
				{
					"fieldname": "ill_standard_reel_length_mm",
					"fieldtype": "Float",
					"label": "Standard Reel Length (mm)",
					"insert_after": "ill_reel_tracked",
					"depends_on": SHOWN,
					"description": "A sealed supplier reel: 30480 for 100 ft (indoor), 15240 for 50 ft (outdoor). Used by Full at the count and by receiving.",
				},
				{
					"fieldname": "ill_reel_scrap_line_mm",
					"fieldtype": "Float",
					"label": "Scrap Line (mm)",
					"default": "610",
					"insert_after": "ill_standard_reel_length_mm",
					"depends_on": SHOWN,
					"description": "Pieces shorter than this are offered for scrap (610 = 2 ft).",
				},
				{
					"fieldname": "ill_reel_min_useful_mm",
					"fieldtype": "Float",
					"label": "Smallest Useful Piece (mm)",
					"default": "1219",
					"insert_after": "ill_reel_scrap_line_mm",
					"depends_on": SHOWN,
					"description": "Top of the dead zone the planner avoids leaving (1219 = 4 ft).",
				},
				{
					"fieldname": "ill_reel_remnant_line_mm",
					"fieldtype": "Float",
					"label": "Remnant Line (mm)",
					"default": "3048",
					"insert_after": "ill_reel_min_useful_mm",
					"depends_on": SHOWN,
					"description": "Below this a reel is a Remnant, used first (3048 = 10 ft).",
				},
				{
					"fieldname": "ill_reel_column_break",
					"fieldtype": "Column Break",
					"insert_after": "ill_reel_remnant_line_mm",
				},
				{
					"fieldname": "ill_reel_cut_allowance_mm",
					"fieldtype": "Float",
					"label": "Cut Allowance (mm)",
					"default": "0",
					"insert_after": "ill_reel_column_break",
					"depends_on": SHOWN,
					"description": "Added to every cut.",
				},
				{
					"fieldname": "ill_reel_start_waste_mm",
					"fieldtype": "Float",
					"label": "Start Waste (mm)",
					"default": "0",
					"insert_after": "ill_reel_cut_allowance_mm",
					"depends_on": SHOWN,
					"description": "Lost when a sealed reel is opened (the factory leader).",
				},
				{
					"fieldname": "ill_reel_weight_g_per_m",
					"fieldtype": "Float",
					"label": "Weight per Metre (g)",
					"insert_after": "ill_reel_start_waste_mm",
					"depends_on": SHOWN,
					"description": "With the core weight, lets the count weigh an open reel instead of measuring it.",
				},
				{
					"fieldname": "ill_reel_core_weight_g",
					"fieldtype": "Float",
					"label": "Empty Reel Weight (g)",
					"insert_after": "ill_reel_weight_g_per_m",
					"depends_on": SHOWN,
				},
			]
		}
	)
