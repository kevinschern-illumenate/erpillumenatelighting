# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Seed the customer and supplier email templates (insert-if-missing; never overwrites staff edits).

Creates the ``ilL - ...`` Email Templates, the Helpdesk saved replies (when Helpdesk is
installed) and the Notifications, which are created disabled. A template staff deleted
on purpose is not recreated by later migrates, because this patch runs once. To ship
new templates later, add them to ``email_templates/library.py`` and re-run this patch
by appending a dated comment to its line in patches.txt.
"""

import frappe

from illumenate_lighting.illumenate_lighting.email_templates.seed import ensure_all


def execute():
	result = ensure_all()
	frappe.db.commit()
	return result
