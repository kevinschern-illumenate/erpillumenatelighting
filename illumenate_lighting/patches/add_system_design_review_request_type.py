# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Seed the "System Design Review" request type (plan H4.2, WP-4.2, D3).

Runs after model sync; the ``ilL Applications Engineer`` role exists from the pre-model-sync patch.
An existing record keeps any edits staff made to it.
"""

import frappe

TYPE_NAME = "System Design Review"


def execute():
	if frappe.db.exists("ilL-Request-Type", TYPE_NAME):
		return
	frappe.get_doc(
		{
			"doctype": "ilL-Request-Type",
			"type_name": TYPE_NAME,
			"category": "Technical",
			"is_active": 1,
			"portal_label": "System design review",
			"portal_description": "An ilLumenate Applications Engineer reviews a System Designer design.",
			"default_priority": "Normal",
			"sla_hours_normal": 16,
			"sla_hours_high": 8,
			"sla_hours_rush": 4,
			"default_assignee_role": "ilL Applications Engineer",
			"show_project_field": 1,
			"show_fixture_field": 0,
		}
	).insert(ignore_permissions=True)
