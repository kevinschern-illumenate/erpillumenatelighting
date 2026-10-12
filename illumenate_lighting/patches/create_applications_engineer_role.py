# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Create the staff role that reviews and approves System Designer designs (D3).

Runs before model sync so the new DocTypes' permissions reference an existing Role.
"""

import frappe

ROLE = "ilL Applications Engineer"


def execute():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(
			ignore_permissions=True
		)
