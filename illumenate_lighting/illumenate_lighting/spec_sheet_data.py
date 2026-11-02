"""Spec sheet data, payload v2 (plan 4.6, D37, D39, DC6): template and product kept apart.

``get_spec_sheet_data(template_doctype, template_id)`` returns::

    {
      "schema_version": 2,
      "context":  {environment, brand, template_doctype, template_id, product},
      "template": everything the template owns (all its fields and tables),
      "product":  null, or only what the Webflow Product owns (no mirrored template data),
      "webflow":  the product's Webflow state for the brand,
      "legacy":   null, or today's flat product record under the old key names,
    }

``legacy`` is the adapter: exactly what ``webflow_export_v2.get_webflow_products`` returns for
the product today (``configurator_options``, ``custom_webflow_status``,
``custom_dimensions_image_2`` and the other old keys), so the n8n nodes and the Vercel
generator keep working until they move to the v2 sections (plan Phase 9).

Every Webflow Product field is classified in ``PRODUCT_FIELDS`` (the product owns it),
``MIRRORED`` (the template owns it; the product holds a copy) or ``NOT_LISTING`` (sync
bookkeeping and switches). ``ownership_table`` lists them for review, and a test keeps the
classification complete when fields are added.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	CONFIGURATOR_FIELD,
	TEMPLATE_DOCTYPES,
	WEBFLOW_PRODUCT_LINKS,
)

PRODUCT = "ilL-Webflow-Product"
SCHEMA_VERSION = 2

# Owned by the Webflow Product: (fieldname, note).
PRODUCT_FIELDS = (
	("product_name", "Listing name"),
	("product_slug", "Webflow slug"),
	("product_type", ""),
	("is_active", ""),
	("webflow_status", "Webflow Status stage; legacy key custom_webflow_status"),
	("webflow_badge", "Badge (D50); legacy key product_badge"),
	("is_discontinued", "Set on save from the Webflow Status and the template status (D48)"),
	("is_configurable", "Shows the configurator on the website"),
	("configurator_intro_text", ""),
	("short_description", ""),
	("features", ""),
	("featured_image", ""),
	("series_family_image", ""),
	("gallery_images", ""),
	("documents", "Includes the spec sheet row built from the template (D19)"),
	("attribute_links", "Calculated on the product from the template's options"),
	("compatible_products", ""),
	(
		"webflow_compatible_power_supplies",
		"Calculated on the product; legacy key custom_compatible_power_supplies",
	),
	("driver_spec", "Spec link (Driver, Component)"),
	("controller_spec", "Spec link (Controller)"),
	("profile_spec", "Spec link (Component)"),
	("lens_spec", "Spec link (Component)"),
	("tape_spec", "Spec link (Component)"),
	("accessory_spec", "Spec link (Accessory)"),
	("portal_item", "Item sold on the portal"),
	("specifications", "Older attribute specification table (deprecated)"),
)

# Owned by the template; the Webflow Product holds a copy: product field -> template field.
MIRRORED = {
	"product_category": "product_category",
	"series": "series",
	"web_product_category": "product_category",
	"web_series": "series",
	"webflow_template_status": "product_status",
	"sublabel": "sublabel",
	"dimensions_image": "dimensions_image",
	"min_length_mm": "min_length_mm",
	"max_length_mm": "max_length_mm",
	"length_increment_mm": "length_increment_mm",
	"feed_lengths": "feed_lengths",
	"kit_components": "kit_components",
	"configurator_options": CONFIGURATOR_FIELD,
	"webflow_specifications": "specifications",
	"certifications": "certifications",
	"beam_angle": "beam_angle",
	"operating_temp_min_c": "operating_temp_min_c",
	"operating_temp_max_c": "operating_temp_max_c",
	"l70_life_hours": "l70_life_hours",
	"warranty_years": "warranty_years",
	"fixture_weight_per_foot_grams": "fixture_weight_per_foot_grams",
	"target_brands": "target_brands",
	**{field: "name" for field in WEBFLOW_PRODUCT_LINKS.values()},
}

# Not listing data: switches and sync bookkeeping (reported under "webflow").
NOT_LISTING = (
	"auto_populate_configurator_options",
	"auto_populate_attributes",
	"auto_calculate_specs",
	"product_badge",
	"sync_targets",
	"webflow_item_id",
	"webflow_collection_slug",
	"last_synced_at",
	"sync_status",
	"sync_error_message",
)

ROW_META = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
	"doctype",
}
DOC_META = ROW_META - {"name"}


def _clean(value):
	if isinstance(value, list):
		return [_clean(row) for row in value]
	if isinstance(value, dict):
		return {
			key: _clean(item)
			for key, item in value.items()
			if key not in ROW_META and not key.startswith("__")
		}
	return value


def template_section(template):
	"""Everything the template owns: all its fields and tables."""
	data = template.as_dict()
	result = {
		key: _clean(value) for key, value in data.items() if key not in DOC_META and not key.startswith("__")
	}
	result["doctype"] = template.doctype
	return result


def product_section(product):
	"""Only what the Webflow Product owns (mirrored template data is left out)."""
	data = product.as_dict()
	return {"name": product.name, **{field: _clean(data.get(field)) for field, _note in PRODUCT_FIELDS}}


def webflow_section(product, brand):
	"""The product's Webflow state for ``brand`` (per-brand sync row first, then the legacy one)."""
	row = next(
		(r for r in product.get("sync_targets") or [] if r.get("brand") == brand),
		None,
	)
	source = row or product
	return {
		"webflow_status": product.get("webflow_status"),
		"is_active": product.get("is_active"),
		"webflow_item_id": source.get("webflow_item_id"),
		"sync_status": source.get("sync_status") or "Never Synced",
		"last_synced_at": source.get("last_synced_at"),
		"per_brand": bool(row),
	}


def _environment():
	configured = frappe.conf.get("illumenate_environment")
	if configured:
		return configured
	site = getattr(frappe.local, "site", "") or ""
	return "staging" if "staging" in site else "production"


def _brand(template, brand=None):
	if brand:
		return brand
	enabled = [
		row.brand for row in template.get("target_brands") or [] if row.get("enabled") and row.get("brand")
	]
	if enabled:
		return enabled[0]
	from illumenate_lighting.illumenate_lighting.api.webflow_brand import get_default_brand

	return get_default_brand()


def _legacy(product_name, brand):
	from illumenate_lighting.illumenate_lighting.api.webflow_export_v2 import get_webflow_products

	products = get_webflow_products(brand=brand, product_slug=product_name, limit=1).get("products") or []
	return products[0] if products else None


def build(template, product, brand, legacy=None):
	"""Pure apart from the documents passed in: the v2 payload."""
	return {
		"schema_version": SCHEMA_VERSION,
		"context": {
			"environment": _environment(),
			"brand": brand,
			"template_doctype": template.doctype,
			"template_id": template.name,
			"product": product.name if product else None,
		},
		"template": template_section(template),
		"product": product_section(product) if product else None,
		"webflow": webflow_section(product, brand) if product else None,
		"legacy": legacy,
	}


@frappe.whitelist()
def get_spec_sheet_data(template_doctype, template_id, brand=None):
	"""Spec sheet data for one template, payload v2 (see the module docstring)."""
	if template_doctype not in TEMPLATE_DOCTYPES:
		frappe.throw(_("{0} is not a product template.").format(template_doctype))
	if not frappe.has_permission(template_doctype, "read", doc=template_id):
		frappe.throw(_("You don't have permission to read this template."), frappe.PermissionError)
	template = frappe.get_doc(template_doctype, template_id)
	brand = _brand(template, brand)
	name = template.get("webflow_product")
	product = None
	if name and frappe.db.get_value(PRODUCT, name, WEBFLOW_PRODUCT_LINKS[template_doctype]) == template.name:
		product = frappe.get_doc(PRODUCT, name)
	legacy = _legacy(product.name, brand) if product else template_record(template, brand)
	return build(template, product, brand, legacy)


def template_record(template, brand):
	"""The ``legacy`` record for a template with no Webflow Product: the same export code run
	on a temporary, unsaved product (``webflow_export_v2.export_template_record``)."""
	from illumenate_lighting.illumenate_lighting.api.webflow_export_v2 import export_template_record

	return export_template_record(template, brand)


# Keys only a real Webflow Product fills; empty in a template-only record.
PRODUCT_ONLY_KEYS = (
	"name",
	"product_slug",
	"webflow_status",
	"custom_webflow_status",
	"webflow_badge",
	"product_badge",
	"is_discontinued",
	"short_description",
	"features",
	"features_json",
	"featured_image",
	"series_family_image",
	"gallery_images",
	"documents",
	"compatible_products",
	"configurator_intro_text",
	"webflow_item_id",
	"webflow_collection_slug",
	"last_synced_at",
	"sync_status",
	"sync_error_message",
	"creation",
	"modified",
	"is_configurable",
	"driver_spec",
	"controller_spec",
	"profile_spec",
	"lens_spec",
	"tape_spec",
	"accessory_spec",
)


def compare_records(real, built):
	"""Pure: keys whose values differ between the real export and the template-only record,
	leaving out the keys only a real product fills."""
	keys = (set(real) | set(built)) - set(PRODUCT_ONLY_KEYS)
	return sorted(key for key in keys if frappe.as_json(real.get(key)) != frappe.as_json(built.get(key)))


@frappe.whitelist(methods=["POST"])
def check_template_records(limit_per_type=2):
	"""Staging check: for linked templates, build the template-only record and compare it with
	the real export. ``differences`` should be empty. System Manager only."""
	frappe.only_for("System Manager")
	report = []
	for doctype in TEMPLATE_DOCTYPES:
		for name in frappe.get_all(
			doctype, filters={"webflow_product": ["is", "set"]}, pluck="name", limit=int(limit_per_type)
		):
			template = frappe.get_doc(doctype, name)
			brand = _brand(template)
			entry = {"template": (doctype, name), "product": template.webflow_product}
			try:
				real = _legacy(template.webflow_product, brand)
				if not real:
					entry["skipped"] = "product not exported for the brand"
				else:
					entry["differences"] = compare_records(real, template_record(template, brand))
			except Exception as error:
				entry["error"] = str(error)
			report.append(entry)
	return report


def ownership_table():
	"""Rows (product field, owner, template field, legacy key) for the review table."""
	legacy_keys = {
		"webflow_status": "custom_webflow_status",
		"webflow_badge": "product_badge",
		"webflow_compatible_power_supplies": "custom_compatible_power_supplies",
		"dimensions_image": "custom_dimensions_image_2 / dimensions_image_dark",
		"webflow_specifications": "specifications",
	}
	rows = [(field, "Webflow Product", "", legacy_keys.get(field, field)) for field, _note in PRODUCT_FIELDS]
	rows += [
		(field, "Template", template_field, legacy_keys.get(field, field))
		for field, template_field in MIRRORED.items()
	]
	rows += [(field, "Not listing data", "", field) for field in NOT_LISTING]
	return rows


@frappe.whitelist(methods=["POST"])
def check_spec_sheet_data(limit_per_type=1):
	"""Staging check: build the payload for linked templates of each type. System Manager only.

	For each template doctype, the first ``limit_per_type`` linked templates. Reports errors,
	and whether ``legacy`` is present and equal to the export (it is the export, so a
	mismatch means the export changed between the two calls).
	"""
	frappe.only_for("System Manager")
	report = []
	for doctype in TEMPLATE_DOCTYPES:
		names = frappe.get_all(
			doctype, filters={"webflow_product": ["is", "set"]}, pluck="name", limit=int(limit_per_type)
		)
		for name in names:
			entry = {"template": (doctype, name)}
			try:
				data = get_spec_sheet_data(doctype, name)
				entry["product"] = data["context"]["product"]
				entry["brand"] = data["context"]["brand"]
				entry["legacy"] = "present" if data["legacy"] else "not exported for this brand"
				entry["template_fields"] = len(data["template"])
				if data["legacy"]:
					again = _legacy(data["context"]["product"], data["context"]["brand"])
					entry["legacy_matches_export"] = frappe.as_json(again) == frappe.as_json(data["legacy"])
			except Exception as error:
				entry["error"] = str(error)
			report.append(entry)
	return report
