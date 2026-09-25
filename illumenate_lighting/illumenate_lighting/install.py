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
	from illumenate_lighting.patches.b2b_portal_foundations import execute

	execute()
	from illumenate_lighting.patches.b2b_conversations import execute as conversations

	conversations()
	from illumenate_lighting.patches.b2b_configurator_receipts import execute as configurator_receipts

	configurator_receipts()
	from illumenate_lighting.patches.b2b_fixture_groups import execute as fixture_groups

	fixture_groups()
	from illumenate_lighting.patches.b2b_accounts import execute as accounts

	accounts()
	from illumenate_lighting.patches.b2b_order_service import execute as order_service

	order_service()
	from illumenate_lighting.patches.b2b_commercial_lineage import execute as commercial_lineage

	commercial_lineage()
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
	role.desk_access = 0  # Dealers use the portal; staff roles grant Desk access.
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
