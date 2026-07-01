# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Backward-compatible redirect for the legacy LED Sheet configurator page.

LED Sheet is now a first-class category on the unified ``/portal/configure``
page.  This page redirects to it while translating the legacy **one-based**
``line_idx`` used by the old configure-sheet flow into the **zero-based**
``line_idx`` that the unified configurator (and schedule links) now use.
"""

import frappe
from frappe.utils import quote

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw("Please login to configure products", frappe.PermissionError)

	params = ["category=LED%20Sheet"]

	schedule_name = frappe.form_dict.get("schedule")
	if schedule_name:
		params.append(f"schedule={quote(schedule_name, safe='')}")

	# Legacy configure-sheet links used one-based indexes; the unified page is
	# zero-based.  Detect and convert here only.
	line_idx = frappe.form_dict.get("line_idx")
	if line_idx not in (None, ""):
		try:
			legacy_idx = int(line_idx)
			zero_based = legacy_idx - 1 if legacy_idx >= 1 else legacy_idx
			params.append(f"line_idx={zero_based}")
		except (TypeError, ValueError):
			pass

	template = frappe.form_dict.get("template")
	if template:
		params.append(f"template={quote(template, safe='')}")

	frappe.local.flags.redirect_location = "/portal/configure?" + "&".join(params)
	raise frappe.Redirect
