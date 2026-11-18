"""Add Item.ill_light_engine_of and Item.ill_light_engine_key.

A ship-in-pieces linear fixture is a Product Bundle of stock extrusion parts and one
configured light engine per run. Each light engine is its own Item with a BOM; these
links let manufacturing, pick lists and build points find the fixture it belongs to.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = [
	{
		"fieldname": "ill_light_engine_of",
		"fieldtype": "Link",
		"options": "ilL-Configured-Fixture",
		"label": "Light Engine Of",
		"description": "The ship-in-pieces fixture build this light engine is made for.",
		"insert_after": "ill_configured_group",
		"read_only": 1,
		"no_copy": 1,
		"search_index": 1,
	},
	{
		"fieldname": "ill_light_engine_key",
		"fieldtype": "Data",
		"label": "Light Engine Key",
		"description": "Which light engine of the fixture build this Item is (LE1, LE2, ...).",
		"insert_after": "ill_light_engine_of",
		"read_only": 1,
		"no_copy": 1,
	},
]


def execute():
	create_custom_fields({"Item": FIELDS}, update=True)
	frappe.db.commit()
