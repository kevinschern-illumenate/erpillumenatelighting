"""ilL-Attribute-Certification badge Custom Fields become app fields (owner, 2026-11-03).

custom_badge_image_dark -> badge_image_dark, custom_206_badge_image_light -> badge_image_light_206,
custom_206_badge_image_dark -> badge_image_dark_206. Values are copied where the new field is
empty, then the Custom Field records are deleted.
"""

import frappe

DOCTYPE = "ilL-Attribute-Certification"
RENAMES = {
	"custom_badge_image_dark": "badge_image_dark",
	"custom_206_badge_image_light": "badge_image_light_206",
	"custom_206_badge_image_dark": "badge_image_dark_206",
}


def execute():
	for old, new in RENAMES.items():
		if frappe.db.has_column(DOCTYPE, old) and frappe.db.has_column(DOCTYPE, new):
			frappe.db.sql(
				f"""update `tab{DOCTYPE}` set `{new}` = `{old}`
				where ifnull(`{new}`, '') = '' and ifnull(`{old}`, '') != ''"""
			)
		name = frappe.db.get_value("Custom Field", {"dt": DOCTYPE, "fieldname": old}, "name")
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
	frappe.clear_cache(doctype=DOCTYPE)
