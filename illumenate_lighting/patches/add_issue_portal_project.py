"""Add Issue.ill_project: the portal project a support ticket is about (DESK-6).

ERPNext's own Issue.project links to its Project DocType, not the portal's
ilL-Project, so portal tickets get a separate link that staff can filter on.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Issue": [
				{
					"fieldname": "ill_project",
					"fieldtype": "Link",
					"options": "ilL-Project",
					"label": "Portal Project",
					"insert_after": "customer",
					"search_index": 1,
					"in_standard_filter": 1,
				},
			],
		},
		update=True,
	)
	frappe.db.commit()
