# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Seed the gallery application and design service lists and the "Custom" series (idempotent)."""

import frappe

from illumenate_lighting.illumenate_lighting.api.gallery_schema import APPLICATIONS, DESIGN_SERVICES


def execute():
	for doctype, field, names in (
		("ilL-Gallery-Application", "application_name", APPLICATIONS),
		("ilL-Design-Service", "service_name", DESIGN_SERVICES),
	):
		for name in names:
			if not frappe.db.exists(doctype, name):
				frappe.get_doc({"doctype": doctype, field: name, "is_active": 1}).insert(
					ignore_permissions=True
				)
	if not frappe.db.exists("ilL-Attribute-Series", {"series_name": "Custom"}):
		frappe.get_doc(
			{"doctype": "ilL-Attribute-Series", "series_name": "Custom", "code": "CUSTOM", "is_active": 1}
		).insert(ignore_permissions=True)
