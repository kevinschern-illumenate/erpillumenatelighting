# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Product templates with no hero image, and the image staff could use instead (plan 5.4, D1).

The template ``hero_image`` is the main product image shown to dealers and on Webflow. This
report lists the gaps with a suggestion from the existing images; nothing changes until a
person picks "Use as hero image", and that never replaces a hero image already set.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.product_projection import (
	HERO_LINKS,
	images_list,
	resolve_product_images,
	safe_document_url,
)

TEMPLATE_DOCTYPES = tuple(doctype for _field, doctype in HERO_LINKS)
EDIT_ROLES = ("System Manager", "ilL Catalog Publisher")
SOURCE_LABELS = {
	"featured_image": "Webflow featured image",
	"gallery": "Webflow gallery, first image",
	"template_image": "Template image (legacy)",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Template Type"), "fieldname": "template_type", "fieldtype": "Data", "width": 190},
		{
			"label": _("Template"),
			"fieldname": "template",
			"fieldtype": "Dynamic Link",
			"options": "template_type",
			"width": 170,
		},
		{"label": _("Template Name"), "fieldname": "template_name", "fieldtype": "Data", "width": 200},
		{"label": _("Active"), "fieldname": "is_active", "fieldtype": "Check", "width": 70},
		{
			"label": _("Webflow Product"),
			"fieldname": "webflow_product",
			"fieldtype": "Link",
			"options": "ilL-Webflow-Product",
			"width": 170,
		},
		{"label": _("Suggested Image"), "fieldname": "suggested_image", "fieldtype": "Data", "width": 120},
		{"label": _("Suggested From"), "fieldname": "suggested_from", "fieldtype": "Data", "width": 190},
		{"label": _("Other Images"), "fieldname": "other_images", "fieldtype": "Int", "width": 100},
		{"label": _("Action"), "fieldname": "action", "fieldtype": "Data", "width": 170},
	]


def get_data(filters):
	doctypes = (filters.template_type,) if filters.template_type in TEMPLATE_DOCTYPES else TEMPLATE_DOCTYPES
	can_edit = bool(set(EDIT_ROLES) & set(frappe.get_roles()))
	data = []
	for doctype in doctypes:
		conditions = {"hero_image": ["is", "not set"]}
		if not filters.include_inactive:
			conditions["is_active"] = 1
		rows = frappe.get_all(
			doctype,
			filters=conditions,
			fields=["name", "template_name", "is_active", "webflow_product"],
			order_by="name asc",
		)
		resolved = resolve_product_images(doctype, [row.name for row in rows])
		for row in rows:
			images = resolved.get(row.name) or {}
			suggestion = images.get("primary")
			if filters.only_with_suggestion and not suggestion:
				continue
			public = bool(safe_document_url(suggestion))
			data.append(
				{
					"template_type": doctype,
					"template": row.name,
					"template_name": row.template_name,
					"is_active": row.is_active,
					"webflow_product": row.webflow_product,
					"suggested_image": suggestion,
					"suggested_from": _(SOURCE_LABELS.get(images.get("primary_source"), ""))
					if suggestion
					else _("No image yet; upload one on the template"),
					"other_images": len(images.get("gallery") or []),
					"suggestion_public": int(public),
					"can_use": int(can_edit and public),
				}
			)
	return data


@frappe.whitelist(methods=["POST"])
def use_as_hero_image(template_type, template, image):
	"""Set an empty template ``hero_image`` to one of its existing public images.

	Refuses when the template already has a hero image (no overwrite), when ``image`` is not
	one of the template's own images, or when it is not a public file.
	"""
	frappe.only_for(EDIT_ROLES)
	if template_type not in TEMPLATE_DOCTYPES:
		frappe.throw(_("Choose a product template type."))
	doc = frappe.get_doc(template_type, template)
	doc.check_permission("write")
	if doc.get("hero_image"):
		frappe.throw(_("{0} already has a hero image. Nothing was changed.").format(template))
	candidates = {entry["image"] for entry in images_list(resolve_product_images(template_type, [template]).get(template))}
	if image not in candidates:
		frappe.throw(_("That image is not one of {0}'s images. Reload the report and try again.").format(template))
	if not safe_document_url(image):
		frappe.throw(_("Only a public image can be the hero image, because dealers and Webflow show it."))
	doc.hero_image = image
	doc.save()
	return {"template_type": template_type, "template": template, "hero_image": doc.hero_image}
