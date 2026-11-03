# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Create the least-privilege user that claims publication jobs (hardening plan 0.6c).

Safe to run again: the helper only creates a missing user and adds missing roles.
"""

import frappe

from illumenate_lighting.illumenate_lighting.portal.service_users import ensure_service_user


def execute():
	ensure_service_user("publication")
	frappe.db.commit()
