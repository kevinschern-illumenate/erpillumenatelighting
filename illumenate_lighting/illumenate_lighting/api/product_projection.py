"""Shared schema-accurate product projection; no database or actor side effects."""

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
):
	"""Project a catalog product; ``price`` is the template MSRP per foot for per-foot families.

	``rollout_reason`` is ``portal.rollout.reason()`` for the product's family; it names why
	``configure_available`` is false (for example ``pilot_only``).
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
	gallery = [
		{
			"image": row.get("image"),
			"alt_text": row.get("alt_text") or "",
			"display_order": row.get("display_order") or row.get("idx") or 0,
		}
		for row in get("gallery_images") or []
	]
	if not gallery and get("featured_image"):
		gallery = [
			{"image": get("featured_image"), "alt_text": get("product_name") or "", "display_order": 0}
		]
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
			"gallery": sorted(gallery, key=lambda r: r["display_order"]),
			"documents": documents,
			"configurator_options": sorted(options, key=lambda r: r["step"] or 0),
			"validation_errors": errors,
			"certifications": list(certifications),
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
