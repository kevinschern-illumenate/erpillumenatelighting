"""Add Item.ill_configured_group: the group a multi-run group bundle Item orders.

A schedule line's readable group part number becomes a non-stock bundle Item at
conversion. This link lets manufacturing, approval and reconversion recognise it.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Item": [
				{
					"fieldname": "ill_configured_group",
					"fieldtype": "Link",
					"options": "ilL-Configured-Group",
					"label": "Configured Group",
					"description": "The multi-run group this bundle Item orders.",
					"insert_after": "ill_build_id",
					"read_only": 1,
					"no_copy": 1,
					"search_index": 1,
				},
			],
		},
		update=True,
	)
	frappe.db.commit()
