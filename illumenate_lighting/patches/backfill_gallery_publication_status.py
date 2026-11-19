# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Fill the new publication_status field on galleries that existed before it."""

import frappe

GALLERY = "ilL-Webflow-Gallery"


def execute():
	if not frappe.db.exists("DocType", GALLERY):
		return
	frappe.reload_doc("illumenate_lighting", "doctype", "ill_webflow_gallery")
	from illumenate_lighting.illumenate_lighting.api.gallery_publication import sync_status

	for name in frappe.get_all(GALLERY, pluck="name"):
		sync_status(name)
