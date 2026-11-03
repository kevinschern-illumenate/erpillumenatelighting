"""What a template needs before its spec sheet can be generated (owner, 2026-11-03).

Run when Generate Spec is clicked (and for each template of a bulk run). ``missing`` stops the
generation and is listed to the user; ``warnings`` are shown but do not stop it.

Required for every template type:

- Target Brand (one enabled row)
- Display Name or Template Name
- Sublabel
- Hero Image
- Dimensions Image
- Specifications: at least one row with a value
- The brand's Webflow spec sheet page for the template's product type
  (``<site>/spec-sheet-templates/<product type slug>``)

Required for Extrusion Kits:

- Default Profile Spec, with dimensions or a width and height
- Kit Components: at least one row, each with Component Type and Component Item
- A Component Image for each component type

Warnings: kit component rows without a Description, certifications without a Badge Image, no
Part No. Configurator steps.

Other template types get their own required fields when their Webflow page is built.
"""

import frappe

KIT = "ilL-Extrusion-Kit-Template"
PAGE_PATH = "spec-sheet-templates"


def page_slug(template):
	"""The Webflow page slug: the template's product type (never the Webflow Product's)."""
	from illumenate_lighting.illumenate_lighting.template_listing import product_type_for

	return (product_type_for(template) or "").lower().replace(" ", "-")


def webflow_site(brand):
	"""The brand's Webflow site that holds the spec sheet pages.

	Site config ``spec_sheet_template_sites`` ({brand code: "https://..."}) wins, so staging can
	point at the staging Webflow site; otherwise the brand's Webflow Site URL.
	"""
	configured = frappe.conf.get("spec_sheet_template_sites") or {}
	if configured.get(brand):
		return configured[brand].rstrip("/")
	from illumenate_lighting.illumenate_lighting.api.webflow_brand import resolve_brand

	try:
		url = resolve_brand(brand, allow_inactive=True).get("webflow_site_url")
	except Exception:
		url = None
	return (url or "").rstrip("/") or None


def page_exists(url):
	import requests

	try:
		return requests.get(url, timeout=15).status_code == 200
	except requests.RequestException:
		return False


def check(template, page_exists=page_exists):
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

	page_url = None
	if brand:
		site = webflow_site(brand)
		slug = page_slug(template)
		if not site:
			missing.append(f"Webflow site for brand {brand} (set its Webflow Site URL)")
		elif not slug:
			missing.append("Product type of the template (picks the Webflow spec sheet page)")
		else:
			page_url = f"{site}/{PAGE_PATH}/{slug}"
			if not page_exists(page_url):
				missing.append(f"Webflow spec sheet page {page_url} (not found)")

	if template.doctype == KIT:
		_check_kit(template, missing, warnings)

	for row in get("certifications") or []:
		if row.get("certification") and not row.get("badge_image"):
			warnings.append(f"Certification {row.certification} has no Badge Image (its badge is skipped)")
	if not get("part_no_configurator"):
		warnings.append("No Part No. Configurator steps (the part number section is hidden)")
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
	rows = template.get("kit_components") or []
	if not rows:
		missing.append("Kit Components (at least one row)")
	images = {}
	for index, row in enumerate(rows, 1):
		if not row.get("component_type") or not row.get("component_item"):
			missing.append(f"Kit Components row {index}: Component Type and Component Item")
		if row.get("component_type"):
			images[row.component_type] = images.get(row.component_type) or row.get("component_image")
		if not (row.get("component_description") or "").strip():
			warnings.append(f"Kit Components row {index} has no Description (only the code is shown)")
	for kind, image in images.items():
		if not image:
			missing.append(f"Component Image for {kind} (from its first item's Variant Of image)")
