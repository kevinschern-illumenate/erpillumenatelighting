"""Create the staff role that manages Product Finder content.

Runs before model sync so the new DocTypes' permissions reference an existing Role.
"""

import frappe

ROLE = "ilL Product Finder Manager"


def execute():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(
			ignore_permissions=True
		)
