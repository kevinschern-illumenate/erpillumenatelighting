# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now

# Roles that have internal/admin access
INTERNAL_ROLES = {"System Manager", "Administrator"}

# Roles that have dealer-level access (can create/manage their company's data)
DEALER_ROLES = {"Dealer"}


def _is_internal_user(user=None):
	"""Check if user has internal/admin access."""
	if not user:
		user = frappe.session.user
	if user == "Administrator":
		return True
	user_roles = set(frappe.get_roles(user))
	return bool(user_roles & INTERNAL_ROLES)


def _is_dealer_user(user=None):
	"""Check if user has Dealer role."""
	if not user:
		user = frappe.session.user
	return "Dealer" in frappe.get_roles(user)


class ilLProject(Document):
	def before_insert(self):
		"""Set timestamps on collaborator rows and owner_customer before insert."""
		for collaborator in self.collaborators or []:
			if not collaborator.added_on:
				collaborator.added_on = now()

		# Set owner_customer from the creating user's Contact -> Customer link
		if not self.owner_customer:
			user_customer = _get_user_customer(frappe.session.user)
			if user_customer:
				self.owner_customer = user_customer

	def before_save(self):
		"""Set timestamps on new collaborator rows before save."""
		for collaborator in self.collaborators or []:
			if not collaborator.added_on:
				collaborator.added_on = now()

	def validate(self):
		"""Validate project data."""
		self._validate_private_requires_owner_access()
		self._validate_owner_customer_change()

	def _validate_owner_customer_change(self):
		"""Only internal users may reassign the Owner Company of an existing project."""
		if self.is_new() or self.flags.ignore_permissions:
			return

		previous = self.get_doc_before_save()
		if not previous or previous.owner_customer == self.owner_customer:
			return

		if not _is_internal_user():
			frappe.throw(
				_("Only internal users can change the Owner Company of a project."),
				frappe.PermissionError,
			)

	def _validate_private_requires_owner_access(self):
		"""Ensure owner always has access if project is private."""
		if not self.is_private:
			return

		# Check if owner is in collaborators (owner always has implicit access, but can be explicit too)
		# This validation doesn't require owner to be in collaborators - owner has implicit access


def get_permission_query_conditions(user=None):
	"""
	Return SQL conditions to filter ilL-Project list for the current user.

	Generated from the same policy as :func:`has_permission` (see
	``illumenate_lighting.illumenate_lighting.portal.access``) so list
	visibility and direct access always agree.

	Args:
		user: The user to check permissions for. Defaults to current user.

	Returns:
		str: SQL WHERE clause conditions or empty string for full access
	"""
	from illumenate_lighting.illumenate_lighting.portal.access import (
		project_query_conditions,
	)

	return project_query_conditions(user)


def has_permission(doc, ptype="read", user=None):
	"""
	Check if user has permission to access this specific project.

	Rules (see ``portal.access.project_permission``):
	- Internal roles (System Manager, etc.) always allowed
	- Owner always allowed
	- Active collaborators: read always; write only with EDIT access; never
	  owner operations (delete)
	- Dealers of the owning company: read and write
	- Other users of the owning company: read non-private projects only

	Args:
		doc: The ilL-Project document
		ptype: Permission type (read, write, delete, etc.)
		user: The user to check permissions for. Defaults to current user.

	Returns:
		bool: True if user has permission, False otherwise
	"""
	from illumenate_lighting.illumenate_lighting.portal.access import (
		project_permission,
	)

	return project_permission(doc, ptype, user)


def has_website_permission(doc, ptype="read", user=None, verbose=False):
	"""
	Check if a website/portal user has permission to access this project.

	This is called for portal pages accessing ilL-Project documents.
	Uses the same logic as has_permission.

	Args:
		doc: The ilL-Project document
		ptype: Permission type (read, write, etc.)
		user: The user to check permissions for. Defaults to current user.
		verbose: Whether to log verbose output

	Returns:
		bool: True if user has permission, False otherwise
	"""
	return has_permission(doc, ptype, user)


def _get_user_customer(user):
	"""Resolve one company; new contact-only records cannot silently grant membership."""
	meta = frappe.get_meta("Contact")
	filters = {"ill_portal_archived": 0} if meta.has_field("ill_portal_archived") else {}
	fields = ["name", "user"]
	if meta.has_field("ill_portal_contact_only"):
		fields.append("ill_portal_contact_only")
	contacts = frappe.get_all("Contact", filters=filters,
		or_filters={"user": user, "email_id": user}, fields=fields)
	names = [row.name for row in contacts if row.user == user or (not row.user and not row.get("ill_portal_contact_only"))]
	if not names:
		return None
	customers = set(frappe.get_all("Dynamic Link", filters={"parenttype": "Contact",
		"parent": ["in", names], "link_doctype": "Customer"}, pluck="link_name"))
	return next(iter(customers)) if len(customers) == 1 else None
