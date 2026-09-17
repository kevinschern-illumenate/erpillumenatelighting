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
	"""
	Get the Customer linked to this user via Contact.

	Searches for a Contact linked to this user in the following order:
	1. Contact with user field set to this user
	2. Contact with email_id matching the user's email

	Args:
		user: The user email/name

	Returns:
		str or None: The Customer name if found, None otherwise
	"""
	# First check if user has a Contact with user field set
	contact = frappe.db.get_value(
		"Contact",
		{"user": user},
		["name"],
	)

	# If not found via user field, try to find by email_id
	if not contact:
		contact = frappe.db.get_value(
			"Contact",
			{"email_id": user},
			["name"],
		)

	if contact:
		# Get the Customer link from Dynamic Link
		customer = frappe.db.get_value(
			"Dynamic Link",
			{
				"parenttype": "Contact",
				"parent": contact,
				"link_doctype": "Customer",
			},
			"link_name",
		)
		if customer:
			return customer

	return None
