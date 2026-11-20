# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Correct the Kevin's Desk owner picked by the first seed (Nov 20, 2026).

seed_desk_settings took the first enabled "kevins@..." user, which on production was
kevins@cascadeintegration.com, not kevins@illumenate.lighting. This moves the desk to the company-domain
user and issues a new link slug. It only acts when nobody but Administrator has ever edited the settings
(so a deliberate choice made in the desk is kept) and the current owner is off the company domain.
"""

import frappe

from illumenate_lighting.patches.seed_desk_settings import company_domain, find_owner

SETTINGS = "ilL-Desk-Settings"


def execute():
	if not frappe.db.exists("DocType", SETTINGS):
		return
	doc = frappe.get_single(SETTINGS)
	domain = company_domain()
	current = (doc.desk_owner or "").lower()
	if not current or not domain or current.endswith("@" + domain):
		return
	if frappe.db.exists("Version", {"ref_doctype": SETTINGS, "owner": ["!=", "Administrator"]}):
		print(f"Kevin's Desk: owner {current} was set in the desk; not changed")
		return
	owner = find_owner()
	if not owner or owner.lower() == current:
		return
	doc.desk_owner = owner
	doc.slug = ""  # validate() issues a new one; the old link stops working
	doc.save(ignore_permissions=True)
	print(f"Kevin's Desk: owner moved from {current} to {owner}; new link in ilL-Desk-Settings")
