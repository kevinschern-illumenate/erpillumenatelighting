# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import secrets

import frappe
from frappe import _
from frappe.model.document import Document

from illumenate_lighting.kevins_desk.access import SLUG_PATTERN

# Changing these hands the desk (and, from Phase 3, its mailboxes) to someone else, so only the current
# owner may do it. Administrator (migrate, patches, bench console) is the escape hatch.
LOCKED = ("desk_owner", "enabled")


def new_slug():
	return secrets.token_urlsafe(24)  # 32 URL-safe characters


class ilLDeskSettings(Document):
	def validate(self):
		self.guard_owner_change()
		self.slug = (self.slug or "").strip() or new_slug()
		if not SLUG_PATTERN.match(self.slug):
			frappe.throw(
				_("Link Slug must be at least 24 letters, digits, '-' or '_'. Clear it to get a random one.")
			)
		if self.desk_owner:
			row = frappe.db.get_value("User", self.desk_owner, ["enabled", "user_type"], as_dict=True) or {}
			if not row.get("enabled") or row.get("user_type") != "System User":
				frappe.throw(_("Desk Owner must be an enabled System User."))

	def guard_owner_change(self):
		before = self.get_doc_before_save()
		if not before or not before.get("desk_owner"):
			return
		user = frappe.session.user
		if user in ("Administrator", before.desk_owner):
			return
		changed = [f for f in LOCKED if before.get(f) != self.get(f)]
		if changed:
			frappe.throw(
				_("Only {0} can change {1}.").format(before.desk_owner, ", ".join(changed)),
				frappe.PermissionError,
			)
