# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Seed ilL-Desk-Settings once: owner = Kevin's user, enabled, a fresh random link slug.

Insert-if-missing: an owner already set is never changed. The slug is generated on the site
(secrets.token_urlsafe), so it never appears in the repo or the deploy log.
"""

import frappe

OWNER_PREFIX = "kevins"


def execute():
	if not frappe.db.exists("DocType", "ilL-Desk-Settings"):
		return
	doc = frappe.get_single("ilL-Desk-Settings")
	if doc.desk_owner:
		return
	owner = frappe.db.get_value(
		"User",
		{"name": ["like", OWNER_PREFIX + "@%"], "enabled": 1, "user_type": "System User"},
		"name",
	)
	if not owner:
		print(
			"Kevin's Desk: no enabled System User named kevins@...; set the Desk Owner in ilL-Desk-Settings"
		)
		return
	doc.desk_owner = owner
	doc.enabled = 1
	doc.save(ignore_permissions=True)
	print(f"Kevin's Desk: owner set to {owner}; open ilL-Desk-Settings for the link")
