# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ilLPortalUserSettings(Document):
	"""Portal User Settings - stores notification preferences and display settings per user."""

	def validate(self):
		"""Ensure users can only create/edit their own settings (unless System Manager)."""
		if "System Manager" not in frappe.get_roles(frappe.session.user):
			if self.user != frappe.session.user:
				frappe.throw("You can only modify your own portal settings.")

	def before_insert(self):
		"""Prevent duplicates — one record per user."""
		if frappe.db.exists("ilL-Portal-User-Settings", {"user": self.user}):
			frappe.throw(f"Portal settings already exist for user {self.user}.")


def get_permission_query_conditions(user=None):
	"""Non-System-Manager users can only see their own settings."""
	if not user:
		user = frappe.session.user

	if "System Manager" in frappe.get_roles(user):
		return ""

	return f"`tabilL-Portal-User-Settings`.`user` = {frappe.db.escape(user)}"


def has_permission(doc, ptype, user):
	"""Check if user has permission to access this settings record."""
	if "System Manager" in frappe.get_roles(user):
		return True
	return doc.user == user
