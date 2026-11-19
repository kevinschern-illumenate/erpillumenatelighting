"""Shared schema-accurate product projection; no database or actor side effects.

``resolve_product_images`` is the one batch loader that reads the database (read-only)."""

import json
from urllib.parse import unquote, urlencode, urlsplit

from illumenate_lighting.illumenate_lighting.api.configuration_contract import FAMILY_ALIASES, parse_bool

TEMPLATE_FIELDS = {
	"Extrusion Kit": "kit_template",
	"Driver": "driver_template",
	"Controller": "controller_template",
	"Linear Fixture": "fixture_template",
	"LED Tape": "tape_neon_template",
	"COB Tape": "tape_neon_template",
	"LED Neon": "tape_neon_template",
	"LED Sheet": "led_sheet_template",
}
# DocType each family's template link points at.
TEMPLATE_DOCTYPES = {
	"Extrusion Kit": "ilL-Extrusion-Kit-Template",
	"Driver": "ilL-Driver-Template",
	"Controller": "ilL-Controller-Template",
	"Linear Fixture": "ilL-Fixture-Template",
	"LED Tape": "ilL-Tape-Neon-Template",
	"COB Tape": "ilL-Tape-Neon-Template",
	"LED Neon": "ilL-Tape-Neon-Template",
	"LED Sheet": "ilL-LED-Sheet-Template",
}
# Families priced by the foot; the catalog shows the template's MSRP per foot.
PER_FOOT_TEMPLATES = {
	"Linear Fixture": "ilL-Fixture-Template",
	"LED Tape": "ilL-Tape-Neon-Template",
	"COB Tape": "ilL-Tape-Neon-Template",
	"LED Neon": "ilL-Tape-Neon-Template",
}

PRODUCT_DOCTYPE = "ilL-Webflow-Product"
GALLERY_DOCTYPE = "ilL-Child-Webflow-Gallery-Image"
# Product link fields in the order set_dynamic_hero_image() reads them.
HERO_LINKS = (
	("kit_template", "ilL-Extrusion-Kit-Template"),
	("fixture_template", "ilL-Fixture-Template"),
	("tape_neon_template", "ilL-Tape-Neon-Template"),
	("driver_template", "ilL-Driver-Template"),
	("controller_template", "ilL-Controller-Template"),
	("led_sheet_template", "ilL-LED-Sheet-Template"),
)
IMAGE_SOURCES = ("template_hero", "featured_image", "gallery", "template_image")


def choose_images(*, hero=None, hero_alt=None, featured=None, gallery=(), legacy=None, alt="", hero_first=True):
	"""The main product image under owner decision D1, plus the other images.

	Precedence: template ``hero_image`` -> Webflow ``featured_image`` -> gallery #1 ->
	template ``image`` (legacy). Every other distinct image follows in ``gallery``.
	``hero_first=False`` is the ``ill_portal_hero_image_first`` kill switch: the pre-D1
	order, gallery #1 -> ``featured_image`` -> template ``image`` -> ``hero_image``.
	"""
	alt = alt or ""
	rows = [
		{"image": row.get("image"), "alt_text": row.get("alt_text") or alt}
		for row in gallery or ()
		if row.get("image")
	]
	hero_c = ("template_hero", hero, hero_alt or alt)
	featured_c = ("featured_image", featured, alt)
	gallery_c = [("gallery", row["image"], row["alt_text"]) for row in rows[:1]]
	legacy_c = ("template_image", legacy, alt)
	if hero_first:
		candidates = [hero_c, featured_c, *gallery_c, legacy_c]
	else:
		candidates = [*gallery_c, featured_c, legacy_c, hero_c]
	source, primary, primary_alt = next(((s, url, a) for s, url, a in candidates if url), (None, None, ""))
	seen, extra = {primary}, []
	others = [(row["image"], row["alt_text"]) for row in rows] + [(featured, alt), (legacy, alt), (hero, hero_alt or alt)]
	for url, text in others:
		if url and url not in seen:
			seen.add(url)
			extra.append({"image": url, "alt_text": text})
	return {"primary": primary, "primary_alt": primary_alt, "primary_source": source, "gallery": extra}


def images_list(images):
	"""``[primary, *gallery]`` in the ``{image, alt_text}`` shape the picker galleries read."""
	if not images:
		return []
	lead = [{"image": images["primary"], "alt_text": images["primary_alt"]}] if images.get("primary") else []
	return lead + list(images.get("gallery") or [])


def _fields(doctype, wanted):
	import frappe

	meta = frappe.get_meta(doctype)
	return [field for field in wanted if field == "name" or meta.has_field(field)]


def _galleries(products):
	import frappe

	galleries = {}
	if not products:
		return galleries
	for row in frappe.get_all(
		GALLERY_DOCTYPE,
		filters={"parent": ["in", list(products)], "parenttype": PRODUCT_DOCTYPE},
		fields=["parent", "image", "alt_text", "idx"],
		order_by="parent asc, idx asc",
		ignore_permissions=True,
	):
		if row.get("image"):
			galleries.setdefault(row.get("parent"), []).append(row)
	return galleries


def _rows(doctype, names, wanted):
	import frappe

	names = [name for name in dict.fromkeys(names) if name]
	if not names:
		return {}
	return {
		row.get("name"): row
		for row in frappe.get_all(
			doctype, filters={"name": ["in", names]}, fields=_fields(doctype, wanted), ignore_permissions=True
		)
	}


def product_images(product, template_row, gallery=(), hero_first=True):
	"""D1 images for one ``ilL-Webflow-Product`` row from rows the caller already loaded.

	``template_row(doctype, name)`` returns a template row (or None); ``gallery`` holds the
	product's gallery rows in order.
	"""
	linked = [
		row
		for field, template_doctype in HERO_LINKS
		if product.get(field)
		for row in [template_row(template_doctype, product.get(field))]
		if row
	]
	hero = next((t for t in linked if t.get("hero_image")), {})
	legacy = next((t for t in linked if t.get("image")), {})
	return choose_images(
		hero=hero.get("hero_image"),
		hero_alt=hero.get("hero_image_alt"),
		featured=product.get("featured_image"),
		gallery=gallery or (),
		legacy=legacy.get("image"),
		alt=product.get("product_name") or "",
		hero_first=hero_first,
	)


TEMPLATE_IMAGE_FIELDS = ("name", "template_name", "hero_image", "hero_image_alt", "image", "webflow_product")


def resolve_product_images(doctype, names):
	"""Batch-resolve product images for templates or ``ilL-Webflow-Product`` names (D1).

	Returns ``{name: {primary, primary_alt, primary_source, gallery}}``; ``gallery`` holds the
	other distinct images in display order, never the primary. Missing names are left out.
	Read-only: it never writes a resolved image back (no automatic overwrite).
	"""
	from illumenate_lighting.illumenate_lighting.portal.site_flags import hero_image_first_enabled

	names = [name for name in dict.fromkeys(names or ()) if name]
	if not names:
		return {}
	hero_first = hero_image_first_enabled()
	if doctype == PRODUCT_DOCTYPE:
		products = _rows(
			PRODUCT_DOCTYPE, names, ("name", "product_name", "featured_image", *(f for f, _ in HERO_LINKS))
		)
		templates = {
			(template_doctype, name): row
			for field, template_doctype in HERO_LINKS
			for name, row in _rows(
				template_doctype, [p.get(field) for p in products.values()], TEMPLATE_IMAGE_FIELDS
			).items()
		}
		galleries = _galleries(products)
		return {
			name: product_images(
				product, lambda doctype, key: templates.get((doctype, key)), galleries.get(name), hero_first
			)
			for name, product in products.items()
		}
	templates = _rows(doctype, names, TEMPLATE_IMAGE_FIELDS)
	products = _rows(
		PRODUCT_DOCTYPE,
		[t.get("webflow_product") for t in templates.values()],
		("name", "product_name", "featured_image"),
	)
	galleries = _galleries(products)
	resolved = {}
	for name, template in templates.items():
		product = products.get(template.get("webflow_product")) or {}
		resolved[name] = choose_images(
			hero=template.get("hero_image"),
			hero_alt=template.get("hero_image_alt"),
			featured=product.get("featured_image"),
			gallery=galleries.get(product.get("name"), ()),
			legacy=template.get("image"),
			alt=template.get("template_name") or product.get("product_name") or "",
			hero_first=hero_first,
		)
	return resolved


def safe_document_url(value):
	if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
		return None
	try:
		parts = urlsplit(value)
	except ValueError:
		return None
	if (
		value.startswith("/files/")
		and not parts.netloc
		and ".." not in unquote(parts.path).replace("\\", "/").split("/")
	):
		return value
	if (
		parts.scheme == "https"
		and parts.netloc
		and not parts.username
		and not unquote(parts.path).replace("\\", "/").startswith("/private/")
	):
		return value
	return None


def project_product(
	product,
	*,
	certifications=(),
	price=None,
	commercial=False,
	configure_available=True,
	template_active=True,
	rollout_reason=None,
	images=None,
):
	"""Project a catalog product; ``price`` is the template MSRP per foot for per-foot families.

	``rollout_reason`` is ``portal.rollout.reason()`` for the product's family; it names why
	``configure_available`` is false (for example ``pilot_only``).
	``images`` is this product's ``resolve_product_images()`` entry. Without it the product's
	own ``hero_image`` (copied from its template on save) leads, so the result stays D1-ordered.
	"""
	get = product.get
	family = FAMILY_ALIASES.get(get("product_type"), get("product_type"))
	template_field = TEMPLATE_FIELDS.get(family)
	template = get(template_field) if template_field else None
	active = parse_bool(get("is_active"))
	options, errors = [], []
	for row in get("configurator_options") or []:
		try:
			values = row.get("allowed_values_json") or []
			if isinstance(values, str):
				values = json.loads(values)
			if not (
				isinstance(values, dict)
				or (isinstance(values, list) and all(isinstance(value, (str, dict)) for value in values))
			):
				raise ValueError("Allowed values must be an array of choices or a metadata object")
		except (ValueError, TypeError):
			values = []
			errors.append(
				{"field": "configurator_options", "code": "INVALID_OPTIONS", "step": row.get("option_step")}
			)
		step = row.get("option_step")
		options.append(
			{
				"step": step,
				"type": row.get("option_type"),
				"label": row.get("option_label"),
				"description": row.get("option_description"),
				"required": parse_bool(row.get("is_required")),
				"depends_on_step": row.get("depends_on_step"),
				"allowed_values": values,
				"metadata": isinstance(values, dict) or (isinstance(step, (int, float)) and step >= 90),
			}
		)
	if not active:
		capability, capability_reason = "unavailable", "inactive"
	elif not parse_bool(get("is_configurable")):
		capability, capability_reason = "inquiry", "not_configurable"
	elif not template:
		capability, capability_reason = "inquiry", "missing_template"
	elif not template_active:
		capability, capability_reason = "inquiry", "inactive_template"
	elif errors:
		capability, capability_reason = "inquiry", f"invalid_options:{errors[0].get('step')}"
	elif not configure_available:
		capability, capability_reason = "inquiry", rollout_reason or "family_not_enabled"
	else:
		capability, capability_reason = "configure", "ok"
	configure_url = None
	if capability == "configure":
		configure_url = "/portal/configure?" + urlencode(
			{"category": family, "template": template, "product_slug": get("product_slug")}
		)
	documents = []
	for row in sorted(get("documents") or [], key=lambda r: r.get("display_order") or 0):
		url = safe_document_url(row.get("document_file"))
		if not url:
			continue
		documents.append(
			{
				"id": row.get("name"),
				"title": row.get("document_title"),
				"document_name": row.get("document_title"),
				"type": row.get("document_type"),
				"document_type": row.get("document_type"),
				"file_url": url,
				"download_url": url,
				"source": get("name"),
				"classification": "public_literature",
				"display_order": row.get("display_order") or 0,
			}
		)
	if images is None:
		rows = sorted(
			get("gallery_images") or [], key=lambda r: r.get("display_order") or r.get("idx") or 0
		)
		images = choose_images(
			hero=get("hero_image"), featured=get("featured_image"), gallery=rows, alt=get("product_name") or ""
		)
	gallery = [dict(row, display_order=index) for index, row in enumerate(images_list(images))]
	result = {
		key: get(key)
		for key in (
			"name",
			"product_name",
			"product_slug",
			"product_type",
			"product_category",
			"series",
			"short_description",
			"featured_image",
			"dimensions_image",
			"features",
			"configurator_intro_text",
			"min_length_mm",
			"max_length_mm",
			"length_increment_mm",
			"fixture_template",
			"tape_neon_template",
			"led_sheet_template",
			"kit_template",
			"driver_template",
			"controller_template",
		)
	}
	# The key keeps its old name so projection hashes and readers do not change.
	result["custom_webflow_status"] = get("webflow_status")
	result.update(
		{
			"projection_version": 1,
			"family": family,
			"is_active": active,
			"is_configurable": capability == "configure",
			"capability": capability,
			"capability_reason": capability_reason,
			"configure_url": configure_url,
			"template": template,
			"gallery": gallery,
			"image": images.get("primary"),
			"image_alt": images.get("primary_alt") or "",
			"image_source": images.get("primary_source"),
			"documents": documents,
			"configurator_options": sorted(options, key=lambda r: r["step"] or 0),
			"validation_errors": errors,
			"certifications": list(certifications),
			"photometric_image": get("photometric_image"),
			"tm30_chart_image": get("tm30_chart_image"),
			"polar_chart_image": get("polar_chart_image"),
			"ies_file": get("ies_file"),
			"ldt_file": get("ldt_file"),
			"colorimetry": list(get("colorimetry") or []),
			"specifications": [
				{
					"spec_group": row.get("spec_group"),
					"spec_label": row.get("spec_label"),
					"spec_value": row.get("spec_value"),
					"spec_unit": row.get("spec_unit"),
					"display_order": row.get("display_order") or 0,
				}
				for row in sorted(get("specifications") or [], key=lambda r: r.get("display_order") or 0)
			],
			"feed_lengths": [
				{key: row.get(key) for key in ("step", "label", "code")} for row in get("feed_lengths") or []
			],
			"attribute_links": [
				{key: row.get(key) for key in ("attribute_type", "attribute_name", "display_label")}
				for row in get("attribute_links") or []
			],
			"compatible_products": [
				{key: row.get(key) for key in ("related_product", "relationship_type", "notes")}
				for row in get("compatible_products") or []
			],
			"kit_components": [
				{
					"component_type": row.get("component_type"),
					"component_item": row.get("component_item"),
					"component_spec_name": row.get("component_spec_name"),
					"quantity": row.get("quantity"),
					"notes": row.get("notes"),
					"custom_webflow_title": row.get("webflow_title"),
					"custom_webflow_description": row.get("component_description"),
				}
				for row in get("kit_components") or []
			],
			"photometric_data": [
				{
					key: row.get(key)
					for key in ("mounting_height", "light_level", "beam_diameter", "display_order")
				}
				for row in sorted(get("photometric_data") or [], key=lambda r: r.get("display_order") or 0)
			],
		}
	)
	if commercial and family in PER_FOOT_TEMPLATES and price is not None:
		result["price_per_ft_msrp"] = price
		result["pricing"] = {
			"basis": "msrp_per_foot",
			"amount": price,
			"unit": "ft",
			"excludes": ["configuration-dependent components"],
		}
	return result
