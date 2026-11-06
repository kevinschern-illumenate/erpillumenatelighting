"""What a template needs before its spec sheet can be generated (owner, 2026-11-03).

Run when Generate Spec is clicked (and for each template of a bulk run). ``missing`` stops the
generation and is listed to the user; ``warnings`` are shown but do not stop it.

Required for every template type:

- Target Brand (one enabled row)
- Display Name or Template Name
- Webflow Category (Product Category; Tape/Neon: Webflow Category). It picks the Webflow spec
  sheet page and the Webflow Product's Product Type.
- Sublabel
- Hero Image
- Dimensions Image
- Specifications: at least one row with a value
- Part No. Configurator: at least one step, each with Option Type, Option Label and Depends On
  Step

Required for Extrusion Kits:

- Default Profile Spec, with dimensions or a width and height
- Operating Temperature Min and Max (both 0 counts as not set, D43)
- Kit Components: at least one row, each with Component Type, Component Item and Description

Warnings: certifications without a Badge Image, component types without a Component Image.

Other template types get their own required fields when their Webflow page is built.
"""

import json

import frappe

KIT = "ilL-Extrusion-Kit-Template"
PAGE_PATH = "spec-sheet-templates"


# Product types that share one spec sheet page (owner, 2026-11-06): tapes and sheets.
SHARED_PAGES = {"LED Tape": "tape-sheets", "COB Tape": "tape-sheets", "LED Sheet": "tape-sheets"}


def page_slug_for(product_type):
	"""Pure: the Webflow spec sheet page for a product type."""
	return SHARED_PAGES.get(product_type) or (product_type or "").lower().replace(" ", "-")


def page_slug(template):
	"""The Webflow page slug: from the template's product type (never the Webflow Product's)."""
	from illumenate_lighting.illumenate_lighting.template_listing import product_type_for

	return page_slug_for(product_type_for(template))


def template_sites(value):
	"""Pure: the ``spec_sheet_template_sites`` map. Frappe Cloud's site config editor can store
	it as a JSON string; a value that is neither a map nor a JSON map counts as unset."""
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			return {}
	return {str(k): str(v) for k, v in value.items() if v} if isinstance(value, dict) else {}


def webflow_site(brand):
	"""The brand's Webflow site that holds the spec sheet pages.

	Site config ``spec_sheet_template_sites`` ({brand code: "https://..."}) wins, so staging can
	point at the staging Webflow site; otherwise the brand's Webflow Site URL.
	"""
	configured = template_sites(frappe.conf.get("spec_sheet_template_sites"))
	if configured.get(brand):
		return configured[brand].rstrip("/")
	from illumenate_lighting.illumenate_lighting.api.webflow_brand import resolve_brand

	try:
		url = resolve_brand(brand, allow_inactive=True).get("webflow_site_url")
	except Exception:
		url = None
	return (url or "").rstrip("/") or None


def check(template):
	"""Returns {"missing": [...], "warnings": [...], "page_url": url or None}."""
	from illumenate_lighting.illumenate_lighting.template_images import template_brand

	missing, warnings = [], []
	get = template.get
	brand = template_brand(template)
	if not brand:
		missing.append("Target Brand (one enabled row)")
	if not (get("display_name") or "").strip() and not (get("template_name") or "").strip():
		missing.append("Display Name or Template Name")
	for field, label in (
		("sublabel", "Sublabel"),
		("hero_image", "Hero Image"),
		("dimensions_image", "Dimensions Image"),
	):
		if not (get(field) or "").strip():
			missing.append(label)
	if not any((row.get("spec_value") or "").strip() for row in get("specifications") or []):
		missing.append("Specifications (at least one row with a value)")
	from illumenate_lighting.illumenate_lighting.web_listing_schema import (
		template_category,
		template_category_field,
	)

	if not template_category(template):
		label = (
			"Webflow Category"
			if template_category_field(template.doctype) == "webflow_category"
			else "Product Category"
		)
		missing.append(label)
	steps = get("part_no_configurator") or []
	if not steps:
		missing.append("Part No. Configurator (at least one step)")
	for index, row in enumerate(steps, 1):
		empty = [
			label
			for field, label in (
				("option_type", "Option Type"),
				("option_label", "Option Label"),
				("depends_on_step", "Depends On Step"),
			)
			if row.get(field) in (None, "")
		]
		if empty:
			missing.append(f"Part No. Configurator step {index}: {', '.join(empty)}")

	# The Webflow page is not checked (not every template has one); it is listed for reference.
	site = webflow_site(brand) if brand else None
	slug = page_slug(template)
	page_url = f"{site}/{PAGE_PATH}/{slug}" if site and slug else None

	if template.doctype == KIT:
		_check_kit(template, missing, warnings)

	for row in get("certifications") or []:
		if row.get("certification") and not row.get("badge_image"):
			warnings.append(f"Certification {row.certification} has no Badge Image (its badge is skipped)")
	return {"missing": missing, "warnings": warnings, "page_url": page_url}


def _check_kit(template, missing, warnings):
	profile = template.get("default_profile_spec")
	if not profile:
		missing.append("Default Profile Spec")
	else:
		row = frappe.db.get_value(
			"ilL-Spec-Profile", profile, ["dimensions", "width_mm", "height_mm"], as_dict=True
		)
		if not row or not (row.dimensions or (row.width_mm and row.height_mm)):
			missing.append(f"Dimensions (or width and height) on Default Profile Spec {profile}")
	low, high = template.get("operating_temp_min_c"), template.get("operating_temp_max_c")
	if low in (None, "") or high in (None, "") or (not float(low) and not float(high)):
		missing.append("Operating Temperature Min and Max")
	rows = template.get("kit_components") or []
	if not rows:
		missing.append("Kit Components (at least one row)")
	images = {}
	for index, row in enumerate(rows, 1):
		empty = [
			label
			for field, label in (
				("component_type", "Component Type"),
				("component_item", "Component Item"),
				("component_description", "Description"),
			)
			if not str(row.get(field) or "").strip()
		]
		if empty:
			missing.append(f"Kit Components row {index}: {', '.join(empty)}")
		if row.get("component_type"):
			images[row.component_type] = images.get(row.component_type) or row.get("component_image")
	for kind, image in images.items():
		if not image:
			warnings.append(f"No Component Image for {kind} (its first item's Variant Of item has no image)")
