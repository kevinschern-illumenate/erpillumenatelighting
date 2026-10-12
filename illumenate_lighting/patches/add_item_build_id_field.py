# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Add Item.ill_build_id, the content-addressed build identity of a configured Item.

LED sheet saves look Items up by this field. It was only listed in the module-level
custom_field.json, which Frappe's fixture sync never reads, so sites never got the
column and every sheet save failed with "Unknown column 'ill_build_id'".
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Item": [
				{
					"fieldname": "ill_build_id",
					"fieldtype": "Data",
					"label": "Configured Build ID",
					"description": "Content-addressed identity of the immutable configured build this Item manufactures.",
					"insert_after": "custom_ill_configured_tape_neon",
					"read_only": 1,
					"no_copy": 1,
					"search_index": 1,
				},
			],
		},
		update=True,
	)
	frappe.db.commit()
