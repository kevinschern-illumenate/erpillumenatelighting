# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Seed ilL-Desk-Settings once: owner = Kevin's user, enabled, a fresh random link slug.

Insert-if-missing: an owner already set is never changed. The slug is generated on the site
(secrets.token_urlsafe), so it never appears in the repo or the deploy log.
"""

import frappe

OWNER_PREFIX = "kevins"


def company_domain():
	"""The company's mail domain: the "Sales" Email Account's, else the default outgoing account's."""
	email = frappe.db.get_value("Email Account", "Sales", "email_id") or frappe.db.get_value(
		"Email Account", {"default_outgoing": 1}, "email_id"
	)
	return email.rsplit("@", 1)[1].lower() if email and "@" in email else ""


def find_owner():
	"""Kevin's user. Several users can start with "kevins@" (another company's account too), so prefer the
	one on the company's mail domain, then the most recently active."""
	users = frappe.get_all(
		"User",
		filters={"name": ["like", OWNER_PREFIX + "@%"], "enabled": 1, "user_type": "System User"},
		fields=["name"],
		order_by="last_active desc",
	)
	domain = company_domain()
	for u in users:
		if domain and u.name.lower().endswith("@" + domain):
			return u.name
	return users[0].name if users else None


def execute():
	if not frappe.db.exists("DocType", "ilL-Desk-Settings"):
		return
	doc = frappe.get_single("ilL-Desk-Settings")
	if doc.desk_owner:
		return
	owner = find_owner()
	if not owner:
		print(
			"Kevin's Desk: no enabled System User named kevins@...; set the Desk Owner in ilL-Desk-Settings"
		)
		return
	doc.desk_owner = owner
	doc.enabled = 1
	doc.save(ignore_permissions=True)
	print(f"Kevin's Desk: owner set to {owner}; open ilL-Desk-Settings for the link")
