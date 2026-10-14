# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Projects no dealer team can see because they have no owner company (REL-5).

Listed for staff to fix by hand on the project form; nothing is changed here.
"""

import frappe
from frappe import _


def execute(filters=None):
	return get_columns(), get_data()


def get_columns():
	return [
		{
			"label": _("Project"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "ilL-Project",
			"width": 160,
		},
		{"label": _("Project Name"), "fieldname": "project_name", "fieldtype": "Data", "width": 220},
		{
			"label": _("End Client"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 180,
		},
		{
			"label": _("Created By"),
			"fieldname": "owner",
			"fieldtype": "Link",
			"options": "User",
			"width": 200,
		},
		{"label": _("Created On"), "fieldname": "creation", "fieldtype": "Datetime", "width": 160},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
	]


def get_data():
	return frappe.get_all(
		"ilL-Project",
		filters={"owner_customer": ["is", "not set"]},
		fields=["name", "project_name", "customer", "owner", "creation", "status"],
		order_by="creation desc",
	)
