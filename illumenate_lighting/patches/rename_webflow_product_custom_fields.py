"""Convert the Webflow Product's site Custom Fields to fields that ship with the app (plan 4.9,
D35, D46, D53, D56, owner request 2026-11-02).

- Values move to the new standard fields (an existing value in the new field is kept).
- Table rows only change which table they belong to (same child doctype).
- ``custom_dimensions_image_2`` is not renamed: its value moves to the linked template's
  ``dimensions_image`` when that is empty, and every value that could not move is listed in
  one Error Log entry so nothing is lost silently (D46).
- ``custom_min_operating_temp_c_copy`` and the stray ``custom_column_break_lgzvl`` go (D53).
- Then the Custom Field records are deleted, after every value has been copied.
"""

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_schema import WEBFLOW_PRODUCT_LINKS

PRODUCT = "ilL-Webflow-Product"
KIT_COMPONENT = "ilL-Child-Webflow-Kit-Component"
CERTIFICATION_LINK = "ilL-Child-Webflow-Certification-Link"

PRODUCT_COLUMNS = {
	"custom_webflow_status": "webflow_status",
	"custom_web_badge": "webflow_badge",
	"custom_web_product_category": "web_product_category",
	"custom_web_series": "web_series",
	"custom_template_status": "webflow_template_status",
}
PRODUCT_TABLES = {
	"custom_spec_custom": ("webflow_specifications", "ilL-Child-Webflow-Spec-Custom"),
	"custom_compatible_power_supplies": ("webflow_compatible_power_supplies", "ilL-Child-Comp-Power"),
}
CHILD_COLUMNS = {
	KIT_COMPONENT: {
		"custom_webflow_title": "webflow_title",
		"custom_webflow_description": "component_description",
	},
	CERTIFICATION_LINK: {"custom_badge_images": "webflow_badge_images"},
}
DROPPED = ("custom_dimensions_image_2", "custom_min_operating_temp_c_copy", "custom_column_break_lgzvl")


def _copy_column(doctype, old, new):
	if not (frappe.db.has_column(doctype, old) and frappe.db.has_column(doctype, new)):
		return
	frappe.db.sql(
		f"""update `tab{doctype}` set `{new}` = `{old}`
		where ifnull(`{new}`, '') = '' and ifnull(`{old}`, '') != ''"""
	)


def _move_dimensions_images():
	if not frappe.db.has_column(PRODUCT, "custom_dimensions_image_2"):
		return []
	link_fields = list(WEBFLOW_PRODUCT_LINKS.values())
	rows = frappe.get_all(
		PRODUCT,
		filters={"custom_dimensions_image_2": ["is", "set"]},
		fields=["name", "custom_dimensions_image_2", *link_fields],
		limit_page_length=0,
	)
	left = []
	for row in rows:
		image = row.custom_dimensions_image_2
		template = next(
			((doctype, row[field]) for doctype, field in WEBFLOW_PRODUCT_LINKS.items() if row.get(field)),
			None,
		)
		if not template:
			left.append(f"{row.name}: no template ({image})")
			continue
		current = frappe.db.get_value(*template, "dimensions_image")
		if not current:
			frappe.db.set_value(*template, "dimensions_image", image, update_modified=False)
		elif current != image:
			left.append(f"{row.name}: {template[0]} {template[1]} already has {current} ({image})")
	return left


def execute():
	for old, new in PRODUCT_COLUMNS.items():
		_copy_column(PRODUCT, old, new)
	if frappe.db.has_column(PRODUCT, "webflow_badge"):
		# D50: no "None" badge; blank means no badge.
		frappe.db.sql(f"update `tab{PRODUCT}` set webflow_badge = '' where webflow_badge = 'None'")
	for old, (new, child) in PRODUCT_TABLES.items():
		frappe.db.sql(
			f"update `tab{child}` set parentfield = %s where parenttype = %s and parentfield = %s",
			(new, PRODUCT, old),
		)
	for child, columns in CHILD_COLUMNS.items():
		for old, new in columns.items():
			_copy_column(child, old, new)

	left = _move_dimensions_images()
	if left:
		frappe.log_error(
			title="Dimensions Image (Dark) values not moved to a template",
			message="\n".join(left),
		)

	names = [
		*((PRODUCT, field) for field in (*PRODUCT_COLUMNS, *PRODUCT_TABLES, *DROPPED)),
		*((child, field) for child, columns in CHILD_COLUMNS.items() for field in columns),
	]
	for doctype, fieldname in names:
		custom_field = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, "name")
		if custom_field:
			frappe.delete_doc("Custom Field", custom_field, ignore_permissions=True, force=True)
	for doctype in (PRODUCT, KIT_COMPONENT, CERTIFICATION_LINK):
		frappe.clear_cache(doctype=doctype)
