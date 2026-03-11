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
	- Dealer users see projects where:
	  - owner_customer == user_customer (their company's projects)
	  - OR user is owner/collaborator
	- External collaborators see only projects they are collaborators on

	Args:
		user: The user to check permissions for. Defaults to current user.

	Returns:
		str: SQL WHERE clause conditions or empty string for full access
	"""
	if not user:
		user = frappe.session.user

	# Internal users have full access
	if _is_internal_user(user):
		return ""

	# Get customer linked to this user (via Contact -> Customer link)
	user_customer = _get_user_customer(user)

	# Check if user is a Dealer
	is_dealer = _is_dealer_user(user)

	if not user_customer:
		# User has no customer link - can only see projects they own or are collaborators on
		return f"""(
			`tabilL-Project`.owner = {frappe.db.escape(user)}
			OR `tabilL-Project`.name IN (
				SELECT parent FROM `tabilL-Child-Project-Collaborator`
				WHERE user = {frappe.db.escape(user)} AND is_active = 1
			)
		)"""

	if is_dealer:
		# Dealers see all their company's projects (private and non-private)
		# Plus any projects they are collaborators on at other companies
		return f"""(
			`tabilL-Project`.owner_customer = {frappe.db.escape(user_customer)}
			OR `tabilL-Project`.owner = {frappe.db.escape(user)}
			OR `tabilL-Project`.name IN (
				SELECT parent FROM `tabilL-Child-Project-Collaborator`
				WHERE user = {frappe.db.escape(user)} AND is_active = 1
			)
		)"""

	# Non-dealer portal user with customer link - apply company-visible + private access rules
	# Visibility is based on owner_customer (the company that created the project)
	return f"""(
		(
			`tabilL-Project`.owner_customer = {frappe.db.escape(user_customer)}
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
	- Dealers can access all projects for their company
	- Regular portal users can view:
	  - Non-private projects where owner_customer == user_customer
	  - Private projects where owner == user OR user in collaborators
	- External collaborators can only access projects they are collaborators on

	Args:
		doc: The ilL-Project document
		ptype: Permission type (read, write, delete, etc.)
		user: The user to check permissions for. Defaults to current user.

	Returns:
		bool: True if user has permission, False otherwise
	"""
	if not user:
		user = frappe.session.user

	# Internal users have full access
	if _is_internal_user(user):
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

	# Check user's company/customer link
	user_customer = _get_user_customer(user)
	is_dealer = _is_dealer_user(user)

	if user_customer and user_customer == doc.owner_customer:
		if is_dealer:
			# Dealers can access all their company's projects (private or not)
			return True
		else:
			# Non-dealer users can only access non-private projects
			if not doc.is_private:
				return True

	return False


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
