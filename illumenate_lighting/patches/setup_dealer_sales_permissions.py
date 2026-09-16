# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Grant the Dealer role the ERPNext permissions a portal conversion needs.

``after_install`` only ever created the Dealer role, so on existing sites the
schedule → Sales Order conversion failed at ``Sales Order.insert()`` for real
dealers while working for System Managers (who bypass the check).
"""

import frappe

from illumenate_lighting.illumenate_lighting.dealer_permissions import (
	apply_dealer_permissions,
)


def execute():
	if not frappe.db.exists("Role", "Dealer"):
		return

	changed = apply_dealer_permissions()

	if changed:
		print(f"Applied least-privilege Dealer permissions to: {', '.join(changed)}")
