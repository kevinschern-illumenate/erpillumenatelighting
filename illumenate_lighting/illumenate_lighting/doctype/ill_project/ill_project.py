# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now


class ilLProject(Document):
	def before_insert(self):
		"""Set timestamps on collaborator rows before insert."""
		for collaborator in self.collaborators or []:
			if not collaborator.added_on:
				collaborator.added_on = now()

	def before_save(self):
		"""Set timestamps on new collaborator rows before save."""
		for collaborator in self.collaborators or []:
			if not collaborator.added_on:
				collaborator.added_on = now()

	def validate(self):
		"""Validate project data."""
		self._validate_private_requires_owner_access()

	def _validate_private_requires_owner_access(self):
		"""Ensure owner always has access if project is private."""
		if not self.is_private:
			return

		# Check if owner is in collaborators (owner always has implicit access, but can be explicit too)
		# This validation doesn't require owner to be in collaborators - owner has implicit access


def get_permission_query_conditions(user=None):
	"""
	Return SQL conditions to filter ilL-Project list for the current user.

	Rules:
	- Internal roles (System Manager, etc.) see all projects
	- Portal users see:
	  - All projects where customer == user_customer AND is_private == 0
	  - Plus projects where is_private == 1 AND (owner == user OR user in collaborators)

	Args:
		user: The user to check permissions for. Defaults to current user.

	Returns:
		str: SQL WHERE clause conditions or empty string for full access
	"""
	if not user:
		user = frappe.session.user

	# System Manager and Administrator have full access
	if "System Manager" in frappe.get_roles(user) or user == "Administrator":
		return ""

	# Get customer linked to this user (via Contact -> Customer link)
	user_customer = _get_user_customer(user)

	if not user_customer:
		# User has no customer link - can only see projects they own or are collaborators on
		return f"""(
			`tabilL-Project`.owner = {frappe.db.escape(user)}
			OR `tabilL-Project`.name IN (
				SELECT parent FROM `tabilL-Child-Project-Collaborator`
				WHERE user = {frappe.db.escape(user)} AND is_active = 1
			)
		)"""

	# User has a customer link - apply company-visible + private access rules
	return f"""(
		(
			`tabilL-Project`.customer = {frappe.db.escape(user_customer)}
			AND `tabilL-Project`.is_private = 0
		)
		OR (
			`tabilL-Project`.is_private = 1
			AND (
				`tabilL-Project`.owner = {frappe.db.escape(user)}
				OR `tabilL-Project`.name IN (
					SELECT parent FROM `tabilL-Child-Project-Collaborator`
					WHERE user = {frappe.db.escape(user)} AND is_active = 1
				)
			)
		)
	)"""


def has_permission(doc, ptype="read", user=None):
	"""
	Check if user has permission to access this specific project.

	Rules:
	- Internal roles (System Manager, etc.) always allowed
	- Portal user can view:
	  - Non-private projects where customer == user_customer
	  - Private projects where owner == user OR user in collaborators

	Args:
		doc: The ilL-Project document
		ptype: Permission type (read, write, delete, etc.)
		user: The user to check permissions for. Defaults to current user.

	Returns:
		bool: True if user has permission, False otherwise
	"""
	if not user:
		user = frappe.session.user

	# System Manager and Administrator have full access
	if "System Manager" in frappe.get_roles(user) or user == "Administrator":
		return True

	# Owner always has full access
	if doc.owner == user:
		return True

	# Check if user is an active collaborator
	collaborator_users = {
		c.user for c in doc.collaborators or []
		if c.is_active
	}
	if user in collaborator_users:
		# For write permission, check access_level
		if ptype in ["write", "delete"]:
			for c in doc.collaborators or []:
				if c.user == user and c.is_active and c.access_level == "EDIT":
					return True
			return False
		return True

	# For non-private projects, check if user is from the same customer
	if not doc.is_private:
		user_customer = _get_user_customer(user)
		if user_customer and user_customer == doc.customer:
			# Company-visible: user from same customer can read
			# For write permission on non-private projects, still allow (MVP)
			return True

	return False


def _get_user_customer(user):
	"""
	Get the Customer linked to this user via Contact.

	Args:
		user: The user email/name

	Returns:
		str or None: The Customer name if found, None otherwise
	"""
	# First check if user has a Contact with a Customer link
	contact = frappe.db.get_value(
		"Contact",
		{"user": user},
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
