# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Create the user that requests automatic Webflow pushes (plan 4.19, sync rebuild step 3).

Safe to run again: the helper only creates a missing user and adds missing roles.
"""

import frappe

from illumenate_lighting.illumenate_lighting.portal.service_users import ensure_service_user


def execute():
	ensure_service_user("webflow_auto_push")
	frappe.db.commit()
