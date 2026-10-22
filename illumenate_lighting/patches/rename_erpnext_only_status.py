"""Rename the "ERPNext Only" Product Status to "Internal Only" on the six templates.

Same meaning for dealers (hidden from them); staff now also see these templates in the
portal. See ``portal_listing``.
"""

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_schema import INTERNAL_STATUS, TEMPLATE_DOCTYPES

OLD_STATUS = "ERPNext Only"


def execute():
	for doctype in TEMPLATE_DOCTYPES:
		if frappe.db.has_column(doctype, "product_status"):
			frappe.db.set_value(
				doctype,
				{"product_status": OLD_STATUS},
				"product_status",
				INTERNAL_STATUS,
				update_modified=False,
			)
