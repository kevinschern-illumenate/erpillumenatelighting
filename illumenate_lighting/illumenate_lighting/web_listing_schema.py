"""Web Listing fields shared by the six product templates.

Pure data, no Frappe import: ``tools/stamp_web_listing_fields.py`` writes these
definitions into each template's doctype JSON, and a unit test keeps them identical.
The tab stays hidden until the templates replace ilL-Webflow-Product as the source
of web content (see the Webflow Product merge plan).
"""

TEMPLATE_DOCTYPES = {
	"ilL-Fixture-Template": "ill_fixture_template",
	"ilL-Tape-Neon-Template": "ill_tape_neon_template",
	"ilL-Controller-Template": "ill_controller_template",
	"ilL-Driver-Template": "ill_driver_template",
	"ilL-Extrusion-Kit-Template": "ill_extrusion_kit_template",
	"ilL-LED-Sheet-Template": "ill_led_sheet_template",
}

# The Webflow Product link field that points at each template today.
WEBFLOW_PRODUCT_LINKS = {
	"ilL-Fixture-Template": "fixture_template",
	"ilL-Tape-Neon-Template": "tape_neon_template",
	"ilL-Controller-Template": "controller_template",
	"ilL-Driver-Template": "driver_template",
	"ilL-Extrusion-Kit-Template": "kit_template",
	"ilL-LED-Sheet-Template": "led_sheet_template",
}

TAB = "web_listing_tab"

_BADGES = "\nNew\nOn Sale\nQuick Ship\nHide"


def _section(fieldname, label):
	return {"fieldname": fieldname, "fieldtype": "Section Break", "label": label}


def _column(fieldname):
	return {"fieldname": fieldname, "fieldtype": "Column Break"}


SHARED_FIELDS = [
	{"fieldname": TAB, "fieldtype": "Tab Break", "label": "Web Listing", "hidden": 1},
	_section("web_identity_section", "Web Identity"),
	{
		"fieldname": "web_listed",
		"fieldtype": "Check",
		"label": "Listed on Web",
		"default": "0",
		"description": "Publish this template as a product page. Leave unticked while it is being reworked.",
	},
	{
		"fieldname": "web_slug",
		"fieldtype": "Data",
		"label": "Web Slug",
		"search_index": 1,
		"description": "Unique across all product templates. Matches the Webflow item's erp-sync-id.",
	},
	{"fieldname": "web_title", "fieldtype": "Data", "label": "Web Title"},
	_column("web_identity_column"),
	{
		"fieldname": "web_category",
		"fieldtype": "Link",
		"label": "Web Category",
		"options": "ilL-Webflow-Category",
	},
	{"fieldname": "portal_item", "fieldtype": "Link", "label": "Portal Item", "options": "Item"},
	_section("web_content_section", "Web Content"),
	{"fieldname": "short_description", "fieldtype": "Small Text", "label": "Short Description"},
	{"fieldname": "sublabel", "fieldtype": "Data", "label": "Sublabel"},
	{"fieldname": "product_badge", "fieldtype": "Select", "label": "Product Badge", "options": _BADGES},
	_column("web_content_column"),
	{"fieldname": "features", "fieldtype": "JSON", "label": "Features"},
	{"fieldname": "warranty_years", "fieldtype": "Int", "label": "Warranty (Years)"},
	_section("web_media_section", "Web Media"),
	{"fieldname": "featured_image", "fieldtype": "Attach Image", "label": "Featured Image"},
	{"fieldname": "dimensions_image", "fieldtype": "Attach Image", "label": "Dimensions Image"},
	_column("web_media_column"),
	{"fieldname": "series_family_image", "fieldtype": "Attach Image", "label": "Series Family Image"},
	{
		"fieldname": "gallery_images",
		"fieldtype": "Table",
		"label": "Gallery Images",
		"options": "ilL-Child-Webflow-Gallery-Image",
	},
	{
		"fieldname": "documents",
		"fieldtype": "Table",
		"label": "Documents",
		"options": "ilL-Child-Webflow-Document",
	},
	{
		"fieldname": "certifications",
		"fieldtype": "Table",
		"label": "Certifications",
		"options": "ilL-Child-Spec-Certification",
	},
	_section("web_configurator_section", "Web Configurator"),
	{"fieldname": "is_configurable", "fieldtype": "Check", "label": "Is Configurable", "default": "0"},
	{
		"fieldname": "configurator_intro_text",
		"fieldtype": "Small Text",
		"label": "Configurator Intro Text",
		"depends_on": "eval:doc.is_configurable",
	},
	{
		"fieldname": "configurator_options",
		"fieldtype": "Table",
		"label": "Configurator Options",
		"options": "ilL-Child-Webflow-Configurator-Option",
		"depends_on": "eval:doc.is_configurable",
	},
	_section("web_publishing_section", "Web Publishing"),
	{
		"fieldname": "target_brands",
		"fieldtype": "Table",
		"label": "Target Brands",
		"options": "ilL-Child-Webflow-Brand-Target",
	},
	{
		"fieldname": "attribute_links",
		"fieldtype": "Table",
		"label": "Attribute Links",
		"options": "ilL-Child-Webflow-Attribute-Link",
		"read_only": 1,
		"description": "Filled from this template on save.",
	},
]

_LENGTHS = [
	_section("web_lengths_section", "Web Lengths"),
	{"fieldname": "min_length_mm", "fieldtype": "Int", "label": "Min Length (mm)"},
	{"fieldname": "max_length_mm", "fieldtype": "Int", "label": "Max Length (mm)"},
	{"fieldname": "length_increment_mm", "fieldtype": "Int", "label": "Length Increment (mm)"},
]

_FEED_LENGTHS = [
	{
		"fieldname": "feed_lengths",
		"fieldtype": "Table",
		"label": "Feed Lengths",
		"options": "ilL-Child-Webflow-Feed-Length",
	},
]

_SPEC_SHEET_DATA = [
	_section("web_spec_sheet_section", "Spec Sheet Data"),
	{"fieldname": "beam_angle", "fieldtype": "Float", "label": "Beam Angle"},
	{"fieldname": "l70_life_hours", "fieldtype": "Int", "label": "L70 Life (Hours)"},
	_column("web_spec_sheet_column"),
	{"fieldname": "operating_temp_min_c", "fieldtype": "Int", "label": "Operating Temp Min (C)"},
	{"fieldname": "operating_temp_max_c", "fieldtype": "Int", "label": "Operating Temp Max (C)"},
]

_WEIGHT = [
	{
		"fieldname": "fixture_weight_per_foot_grams",
		"fieldtype": "Float",
		"label": "Fixture Weight per Foot (g)",
	},
]

_KIT_COMPONENTS = [
	_section("web_kit_components_section", "Web Kit Components"),
	{
		"fieldname": "kit_components",
		"fieldtype": "Table",
		"label": "Kit Components",
		"options": "ilL-Child-Webflow-Kit-Component",
	},
]

TYPE_FIELDS = {
	"ilL-Fixture-Template": _LENGTHS + _FEED_LENGTHS + _SPEC_SHEET_DATA + _WEIGHT,
	"ilL-Tape-Neon-Template": _LENGTHS + _FEED_LENGTHS + _SPEC_SHEET_DATA + _WEIGHT,
	"ilL-Controller-Template": [],
	"ilL-Driver-Template": [],
	"ilL-Extrusion-Kit-Template": _LENGTHS + _SPEC_SHEET_DATA + _WEIGHT + _KIT_COMPONENTS,
	"ilL-LED-Sheet-Template": _SPEC_SHEET_DATA,
}


# Fields some templates defined before the Web Listing tab existed; they keep
# their original place and meaning.
PREEXISTING = {
	"ilL-Fixture-Template": set(),
	"ilL-Tape-Neon-Template": {"certifications", "warranty_years"},
	"ilL-Controller-Template": {"certifications"},
	"ilL-Driver-Template": {"certifications"},
	"ilL-Extrusion-Kit-Template": set(),
	"ilL-LED-Sheet-Template": {"certifications"},
}


def fields_for(doctype):
	"""Web Listing fields to add to one template, skipping fieldnames it already defines."""
	return [
		field
		for field in SHARED_FIELDS + TYPE_FIELDS[doctype]
		if field["fieldname"] not in PREEXISTING[doctype]
	]


def added_fieldnames(doctype):
	"""Data-bearing fieldnames the Web Listing tab adds to one template."""
	return {field["fieldname"] for field in fields_for(doctype) if not field["fieldtype"].endswith("Break")}
