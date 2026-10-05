"""Batched catalog facts. Shared caches never contain a user's rollout decision."""

from collections import defaultdict
from time import time_ns

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import TAPE_NEON_CATEGORIES
from illumenate_lighting.illumenate_lighting.api.product_projection import TEMPLATE_DOCTYPES, TEMPLATE_FIELDS
from illumenate_lighting.illumenate_lighting.portal.product_finder.facets import FACETS

PRODUCT = "ilL-Webflow-Product"
TEMPLATES = {
	"Linear Fixture": (
		"ilL-Fixture-Template",
		"fixture_template",
		"ilL-Child-Template-Allowed-Option",
		"ilL-Child-Template-Allowed-TapeOffering",
	),
	"LED Tape": (
		"ilL-Tape-Neon-Template",
		"tape_neon_template",
		"ilL-Child-Tape-Neon-Allowed-Option",
		"ilL-Child-Tape-Neon-Allowed-Spec",
	),
	"COB Tape": (
		"ilL-Tape-Neon-Template",
		"tape_neon_template",
		"ilL-Child-Tape-Neon-Allowed-Option",
		"ilL-Child-Tape-Neon-Allowed-Spec",
	),
	"LED Neon": (
		"ilL-Tape-Neon-Template",
		"tape_neon_template",
		"ilL-Child-Tape-Neon-Allowed-Option",
		"ilL-Child-Tape-Neon-Allowed-Spec",
	),
	"LED Sheet": (
		"ilL-LED-Sheet-Template",
		"led_sheet_template",
		"ilL-Child-LED-Sheet-Allowed-Option",
		"ilL-Child-LED-Sheet-Allowed-Spec",
	),
	"Extrusion Kit": ("ilL-Extrusion-Kit-Template", "kit_template", "ilL-Child-Kit-Allowed-Option", None),
	"Driver": (
		"ilL-Driver-Template",
		"driver_template",
		"ilL-Child-Driver-Allowed-Option",
		"ilL-Child-Driver-Template-Variant",
	),
	"Controller": (
		"ilL-Controller-Template",
		"controller_template",
		"ilL-Child-Controller-Allowed-Option",
		"ilL-Child-Controller-Template-Variant",
	),
}
SPECS = (
	"ilL-Rel-Tape Offering",
	"ilL-Spec-LED Tape",
	"ilL-Spec-LED-Sheet",
	"ilL-Spec-Driver",
	"ilL-Spec-Controller",
	"ilL-Spec-Accessory",
	"ilL-Spec-Profile",
	"ilL-Spec-Lens",
)
ATTRIBUTES = tuple(
	sorted(
		{d for f in FACETS.values() for d in f["doctypes"]}
		| {"ilL-Attribute-CRI", "ilL-Attribute-Output Level"}
	)
)
STAMP_DOCTYPES = tuple(sorted({PRODUCT, "Item", *SPECS, *ATTRIBUTES, *(v[0] for v in TEMPLATES.values())}))
STAMP_KEY = "ill_product_finder:catalog_stamp"
LIGHT_TYPES = {
	"Static White": "Static white",
	"Tunable White": "Tunable white",
	"Dim to Warm": "Dim-to-warm",
	**dict.fromkeys(("RGB", "RGB+W", "RGBW", "RGB+TW", "RGBTW"), "Full-color"),
}


def catalog_stamp():
	cached = frappe.cache().get_value(STAMP_KEY)
	if cached is not None:
		return cached
	# Every identifier is an internal constant, never user input.
	query = " UNION ALL ".join(f"SELECT MAX(modified) AS stamp FROM `tab{d}`" for d in STAMP_DOCTYPES)
	rows = frappe.db.sql(query, as_dict=True)
	modified = max((str(r.stamp) for r in rows if r.stamp), default="0")
	stamp = f"{modified}:{frappe.cache().get_value('ill_product_finder:catalog_epoch') or 0}"
	frappe.cache().set_value(STAMP_KEY, stamp, expires_in_sec=60)
	return stamp


def invalidate(*_args, **_kwargs):
	# Deleting an older row may leave MAX(modified) unchanged. Advance all derived caches too.
	frappe.cache().set_value("ill_product_finder:catalog_epoch", str(time_ns()))
	frappe.cache().delete_value(STAMP_KEY)


def load():
	key = f"ill_product_finder:facts:{catalog_stamp()}"
	cached = frappe.cache().get_value(key)
	if cached is None:
		cached = build_facts()
		frappe.cache().set_value(key, cached, expires_in_sec=3600)
	return cached


def active(row):
	return bool(row) and ("is_active" not in row or bool(row.get("is_active")))


def build_facts():
	from illumenate_lighting.illumenate_lighting.api.product_catalog import _project
	from illumenate_lighting.illumenate_lighting.portal.standard_products import choices

	products = frappe.get_all(PRODUCT, filters={"is_active": 1}, fields=["*"])
	if not products:
		return []
	tables = {}
	for doctype in sorted({*SPECS, *ATTRIBUTES, *(v[0] for v in TEMPLATES.values())}):
		tables[doctype] = {r.name: r for r in frappe.get_all(doctype, fields=["*"])}
	parents = [r.name for r in products] + [name for rows in tables.values() for name in rows]
	children = defaultdict(lambda: defaultdict(list))
	child_types = {c for v in TEMPLATES.values() for c in v[2:] if c} | {
		"ilL-Child-Webflow-Attribute-Link",
		"ilL-Child-Webflow-Compatibility",
		"ilL-Child-Driver-Input-Protocol",
		"ilL-Child-Controller-Protocol",
		"ilL-Child-Wireless-Protocol",
		"ilL-Child-Webflow-Configurator-Option",
	}
	for doctype in sorted(child_types):
		for row in frappe.get_all(
			doctype, filters={"parent": ["in", parents]}, fields=["*"], order_by="idx asc"
		):
			if active(row):
				children[doctype][row.parent].append(row)
	items = {
		r.name: r
		for r in frappe.get_all(
			"Item",
			filters={"disabled": 0, "has_variants": 0, "is_sales_item": 1},
			fields=["name", "item_name", "stock_uom", "disabled", "has_variants", "is_sales_item"],
		)
	}
	for kind in ("Driver", "Controller"):
		for name, doc in tables[f"ilL-{kind}-Template"].items():
			doc["variants"] = children[f"ilL-Child-{kind}-Template-Variant"][name]
	activity = {
		(d, n): active(row) for d in set(TEMPLATE_DOCTYPES.values()) for n, row in tables.get(d, {}).items()
	}
	result = []
	for product in products:
		product["configurator_options"] = children["ilL-Child-Webflow-Configurator-Option"][product.name]
		projection = _project(product, activity, public=True)
		capability = projection["capability"]
		if capability != "configure" and choices(
			product,
			get_document=lambda d, n: tables.get(d, {}).get(n, frappe._dict(is_active=0)),
			get_item=items.get,
		):
			capability = "quantity"
		if capability not in ("configure", "quantity"):
			continue
		family = projection["family"]
		spec = TEMPLATES.get(family)
		template = product.get(spec[1]) if spec else None
		options = children[spec[2]][template] if spec else []
		rows = children[spec[3]][template] if spec and spec[3] else []
		values, sources = defaultdict(set), {}

		def add(facet, value, source="template"):
			if value is not None and value != "":
				values[facet].add(value)
				sources.setdefault(facet, source)

		for row in options:
			for facet in (
				"environment_rating",
				"ip_rating",
				"cct",
				"mounting_method",
				"lens_appearance",
				"finish",
			):
				add(facet, row.get(facet))
			for facet, master in (
				("environment_rating", "ilL-Attribute-Environment Rating"),
				("cct", "ilL-Attribute-CCT"),
			):
				if row.get("attribute_doctype") == master:
					add(facet, row.get("attribute_link"))
			level = tables["ilL-Attribute-Output Level"].get(row.get("output_level"), {})
			add("lumens_per_ft", level.get("value"))
		light_specs = []
		for row in rows:
			if family == "Linear Fixture":
				offering = tables["ilL-Rel-Tape Offering"].get(row.get("tape_offering"))
				if not active(offering):
					continue
				for facet in ("environment_rating", "lens_appearance"):
					add(facet, row.get(facet))
				for facet in ("cct", "cri", "led_package"):
					add(facet, offering.get(facet))
				add(
					"lumens_per_ft",
					tables["ilL-Attribute-Output Level"].get(offering.get("output_level"), {}).get("value"),
				)
				light_specs.append(tables["ilL-Spec-LED Tape"].get(offering.get("tape_spec"), {}))
			elif family in TAPE_NEON_CATEGORIES:
				light = tables["ilL-Spec-LED Tape"].get(row.get("tape_spec"), {})
				if active(light):
					add("environment_rating", row.get("environment_rating"))
				light_specs.append(light)
			elif family == "LED Sheet":
				light_specs.append(tables["ilL-Spec-LED-Sheet"].get(row.get("spec"), {}))
		for light in filter(active, light_specs):
			for facet, field in (
				("led_package", "led_package"),
				("dimming_protocol", "input_protocol"),
				("output_voltage", "input_voltage"),
			):
				add(facet, light.get(field), "spec")
			if family == "LED Sheet":
				for facet in ("cct", "cri", "ip_rating"):
					add(facet, light.get(facet), "spec")
		if family in TAPE_NEON_CATEGORIES and not values["lumens_per_ft"]:
			for light in filter(active, light_specs):
				add("lumens_per_ft", light.get("lumens_per_foot"), "spec")
		if family in ("Driver", "Controller"):
			prefix = family.lower()
			linked_specs = [tables[f"ilL-Spec-{family}"].get(product.get(prefix + "_spec"), {})]
			linked_specs += [tables[f"ilL-Spec-{family}"].get(r.get(prefix + "_spec"), {}) for r in rows]
			axes = {
				"dimming_protocol": "input_protocol" if family == "Driver" else "output_protocol",
				"output_voltage": "voltage_output",
				"driver_wattage": "wattage",
				"controller_type": "controller_type",
				"controller_mounting": "mounting_type",
				"wireless_protocol": "wireless_protocol",
				"channels": "channels",
				"zones": "zones",
			}
			for row in rows:
				for facet, axis in axes.items():
					add(facet, row.get(axis))
			variant_wattage = bool(values["driver_wattage"])
			for detail in filter(active, linked_specs):
				for facet, axis in axes.items():
					if facet not in ("controller_type", "controller_mounting") or not values[facet]:
						add(facet, detail.get(axis), "spec")
				if family == "Driver" and not variant_wattage and detail.get("max_wattage"):
					add(
						"driver_wattage",
						detail["max_wattage"] * (detail.get("usable_load_factor") or 0.8),
						"derived",
					)
				protocol_type = (
					"ilL-Child-Driver-Input-Protocol"
					if family == "Driver"
					else "ilL-Child-Controller-Protocol"
				)
				for protocol in children[protocol_type][detail.get("name")]:
					if family == "Driver" or protocol.get("parentfield") == "output_protocols":
						add("dimming_protocol", protocol.get("protocol"), "spec")
				for protocol in children["ilL-Child-Wireless-Protocol"][detail.get("name")]:
					add("wireless_protocol", protocol.get("protocol"), "spec")
		# Product attribute links are authoritative for the facets that support them.
		links = defaultdict(set)
		for row in children["ilL-Child-Webflow-Attribute-Link"][product.name]:
			for facet, master in (
				("environment_rating", "ilL-Attribute-Environment Rating"),
				("cri", "ilL-Attribute-CRI"),
				("dimming_protocol", "ilL-Attribute-Dimming Protocol"),
			):
				if row.get("attribute_doctype") == master or row.get("attribute_type") == master.removeprefix(
					"ilL-Attribute-"
				):
					if row.get("attribute_name"):
						links[facet].add(row.attribute_name)
		for facet, linked in links.items():
			values[facet], sources[facet] = linked, "attribute_link"
		for name in values["led_package"]:
			package = tables["ilL-Attribute-LED Package"].get(name, {})
			light_type = LIGHT_TYPES.get(package.get("spectrum_type"))
			add("light_type", light_type, "derived")
			if package.get("is_pixel"):
				add("color_mode", "Addressable pixel (SPI)", "derived")
			elif light_type == "Full-color":
				add("color_mode", "Analog RGB/RGBW", "derived")
		for name in values["cri"]:
			add("cri_min", tables["ilL-Attribute-CRI"].get(name, {}).get("minimum_ra"), "derived")
		kelvins = [
			float(tables["ilL-Attribute-CCT"][name]["kelvin"])
			for name in values["cct"]
			if tables["ilL-Attribute-CCT"].get(name, {}).get("kelvin")
		]
		add("application", product.get("product_category"), "template")
		facets = {}
		for facet, registry in FACETS.items():
			present = values[facet]
			facets[facet] = (
				(
					tuple(sorted(float(v) for v in present))
					if registry["kind"] == "number"
					else frozenset(present)
				)
				if present
				else None
			)
		facets["cct_range"] = (min(kelvins), max(kelvins)) if kelvins else None
		if kelvins:
			sources["cct_range"] = "derived"
		result.append(
			{
				"name": product.name,
				"slug": product.product_slug,
				"title": product.product_name,
				"image": product.featured_image,
				"product_type": product.product_type,
				"family": family,
				"series": product.get("series"),
				"product_category": product.get("product_category"),
				"capability": capability,
				"template": template,
				"facets": facets,
				"sources": sources,
				"compatible_products": [
					dict(r) for r in children["ilL-Child-Webflow-Compatibility"][product.name]
				],
			}
		)
	return result
