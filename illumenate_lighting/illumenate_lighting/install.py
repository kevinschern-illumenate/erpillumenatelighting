# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Installation and setup utilities for ilLumenate Lighting.

This module provides functions to set up roles, permissions, and other
configurations required by the ilLumenate Lighting application.
"""

import frappe
from frappe import _


def after_install():
	"""
	Run after the app is installed.

	Creates the Dealer role and sets up necessary configurations.
	"""
	create_dealer_role()
	frappe.db.commit()


def create_dealer_role():
	"""
	Create the Dealer role if it doesn't exist.

	The Dealer role is for external dealer/distributor users who can:
	- Create and manage projects for their company
	- Create fixture schedules and configure fixtures
	- Create sales orders
	- Request drawings/exports
	- Create customers and contacts for their company
	- Invite external collaborators (restricted to specific projects)
	"""
	if frappe.db.exists("Role", "Dealer"):
		frappe.logger().info("Dealer role already exists, skipping creation")
		return

	role = frappe.new_doc("Role")
	role.role_name = "Dealer"
	role.desk_access = 1  # Allow desk access for full ERP features
	role.is_custom = 0  # Not a custom role (part of app)
	role.home_page = "/portal"  # Redirect to portal by default
	role.disabled = 0
	role.insert(ignore_permissions=True)

	frappe.logger().info("Created Dealer role")


def setup_dealer_permissions():
	"""
	Set up permissions for the Dealer role on various DocTypes.

	This is called during installation and can also be called manually
	to reset permissions.
	"""
	# ilLumenate Lighting DocTypes with Dealer permissions
	doctypes_full_access = [
		# Projects and Schedules
		"ilL-Project",
		"ilL-Project-Fixture-Schedule",
		# Configured fixtures (create via configurator)
		"ilL-Configured-Fixture",
		# Export jobs (request drawings)
		"ilL-Export-Job",
	]

	doctypes_read_only = [
		# Fixture templates (can view/use but not modify)
		"ilL-Fixture-Template",
		# Spec documents (read-only reference)
		"ilL-Spec-Profile",
		"ilL-Spec-Lens",
		"ilL-Spec-LED Tape",
		"ilL-Spec-Driver",
		"ilL-Spec-Accessory",
		# Attribute lookups
		"ilL-Attribute-CCT",
		"ilL-Attribute-CRI",
		"ilL-Attribute-Dimming Protocol",
		"ilL-Attribute-Endcap Color",
		"ilL-Attribute-Endcap Style",
		"ilL-Attribute-Environment Rating",
		"ilL-Attribute-Finish",
		"ilL-Attribute-IP Rating",
		"ilL-Attribute-Joiner Angle",
		"ilL-Attribute-Joiner System",
		"ilL-Attribute-Lead Time Class",
		"ilL-Attribute-Leader Cable",
		"ilL-Attribute-LED Package",
		"ilL-Attribute-Lens Appearance",
		"ilL-Attribute-Lens Interface Type",
		"ilL-Attribute-Mounting Method",
		"ilL-Attribute-Output Level",
		"ilL-Attribute-Output Voltage",
		"ilL-Attribute-Power Feed Type",
		"ilL-Attribute-Pricing Class",
		"ilL-Attribute-SDCM",
		# Relationship tables
		"ilL-Rel-Tape Offering",
		"ilL-Rel-Driver Eligibility",
		"ilL-Rel-Endcap Map",
		"ilL-Rel-Leader Cable Map",
		"ilL-Rel-Mounting Accessory Map",
	]

	# ERPNext DocTypes with Dealer permissions
	erpnext_doctypes_with_create = [
		("Customer", {"create": 1, "read": 1, "write": 1}),
		("Contact", {"create": 1, "read": 1, "write": 1}),
		("Address", {"create": 1, "read": 1, "write": 1}),
		("Sales Order", {"create": 1, "read": 1}),
	]

	erpnext_doctypes_read_only = [
		"Item",
		"Item Group",
		"Territory",
		"Customer Group",
		"Currency",
	]

	# Apply permissions
	for doctype in doctypes_full_access:
		_add_role_permission(doctype, "Dealer", {
			"read": 1, "write": 1, "create": 1, "delete": 0,
			"email": 1, "print": 1, "export": 1, "share": 1,
		})

	for doctype in doctypes_read_only:
		_add_role_permission(doctype, "Dealer", {
			"read": 1, "export": 1, "print": 1,
		})

	for doctype, perms in erpnext_doctypes_with_create:
		_add_role_permission(doctype, "Dealer", perms)

	for doctype in erpnext_doctypes_read_only:
		_add_role_permission(doctype, "Dealer", {"read": 1})

	frappe.db.commit()


def _add_role_permission(doctype: str, role: str, permissions: dict):
	"""
	Add or update role permission for a DocType.

	Args:
		doctype: The DocType name
		role: The role name
		permissions: Dict of permission flags
	"""
	if not frappe.db.exists("DocType", doctype):
		frappe.logger().warning(f"DocType {doctype} not found, skipping permission setup")
		return

	# Check if permission already exists
	existing = frappe.db.get_value(
		"DocPerm",
		{"parent": doctype, "role": role, "parenttype": "DocType"},
		"name",
	)

	if existing:
		# Update existing permission
		frappe.db.set_value("DocPerm", existing, permissions)
	else:
		# Create new permission entry
		doc = frappe.get_doc("DocType", doctype)
		doc.append("permissions", {
			"role": role,
			**permissions,
		})
		doc.flags.ignore_permissions = True
		doc.save()
