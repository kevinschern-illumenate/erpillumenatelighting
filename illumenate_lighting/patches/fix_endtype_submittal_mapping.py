# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Fix ``endtype`` spec-submittal mapping to use the feed-direction end code
instead of the endcap-style end code.

The ``endtype`` PDF field should display the feed direction at the fixture
end (e.g. "C" for a capped single-segment fixture), **not** the endcap
style code (e.g. "HO" for Half-Open).

Before: source_field = sku_endcap_style_end_code  →  "HO"
After:  source_field = sku_feed_direction_end_code →  "C"
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "ilL-Spec-Submittal-Mapping"):
		return

	table = frappe.qb.DocType("ilL-Spec-Submittal-Mapping")
	(
		frappe.qb.update(table)
		.set(table.source_field, "sku_feed_direction_end_code")
		.where(table.pdf_field_name == "endtype")
		.where(table.source_field == "sku_endcap_style_end_code")
		.run()
	)

	frappe.db.commit()
