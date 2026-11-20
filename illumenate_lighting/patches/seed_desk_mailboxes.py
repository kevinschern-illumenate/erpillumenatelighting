# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Seed Kevin's Desk mailboxes once: the desk owner's own mailbox (unread only) and sales@ (all of the
inbox), plus the Google App.

Insert-if-missing: rows or a Google App already set are left alone. sales@ is the "Sales" Email
Account's address when there is one, else sales@ on the owner's domain.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "ilL-Desk-Settings"):
		return
	doc = frappe.get_single("ilL-Desk-Settings")
	changed = False
	if not doc.google_app:
		app = frappe.db.get_value(
			"Connected App",
			{
				"authorization_uri": ["like", "https://accounts.google.com/%"],
				"name": ["not like", "kevins-desk-%"],
			},
			"name",
			order_by="creation asc",
		)
		if app:
			doc.google_app = app
			changed = True
	if not doc.get("mailboxes") and doc.desk_owner:
		owner = doc.desk_owner.lower()
		sales = (frappe.db.get_value("Email Account", "Sales", "email_id") or "").strip().lower()
		sales = sales or "sales@" + owner.split("@", 1)[1]
		scopes = {owner: "Unread only", sales: "All inbox"}  # Kevin: his unread mail, and all of sales@
		for address in dict.fromkeys([owner, sales]):
			doc.append(
				"mailboxes",
				{
					"mailbox": address,
					"label": address.split("@")[0] + "@",
					"scope": scopes[address],
					"enabled": 1,
				},
			)
		changed = True
	if changed:
		doc.save(ignore_permissions=True)
		print(
			f"Kevin's Desk: mailboxes {[r.mailbox for r in doc.mailboxes]}, Google App {doc.google_app or 'not found'}"
		)
