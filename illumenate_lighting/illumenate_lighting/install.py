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
	setup_dealer_permissions()
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
	Set up ERPNext permissions for the Dealer role.

	Delegates to the single least-privilege matrix in
	:mod:`illumenate_lighting.illumenate_lighting.dealer_permissions`, which is
	also what the ``setup_dealer_sales_permissions`` migration applies to
	existing sites. Safe to re-run.
	"""
	from illumenate_lighting.illumenate_lighting.dealer_permissions import (
		apply_dealer_permissions,
	)

	changed = apply_dealer_permissions()
	frappe.db.commit()

	if changed:
		frappe.logger().info(f"Applied Dealer permissions to: {', '.join(changed)}")

	return changed
