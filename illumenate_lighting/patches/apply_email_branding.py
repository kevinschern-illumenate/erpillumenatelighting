# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Branded account emails: welcome and reset templates, 72-hour links, app name, staff-only 2FA.

The look itself ships as files (templates/emails/*.html) and needs no data. This patch
makes the settings changes decided on 2026-11-18; see docs/EMAIL_TEMPLATES.md.
"""

import frappe

from illumenate_lighting.illumenate_lighting.email_templates.system_emails import apply


def execute():
	result = apply()
	frappe.db.commit()
	return result
