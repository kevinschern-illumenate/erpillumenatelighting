"""Product data fields shared by the six product templates.

Pure data, no Frappe import: ``tools/stamp_web_listing_fields.py`` writes these
definitions into each template's doctype JSON, and a unit test keeps them identical.

The templates hold product information (lengths, feeds, spec-sheet data, kit
components, warranty) and their own Product Status. Marketing content and the
Webflow status and sync state stay on ilL-Webflow-Product, which links to its template.
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

# The Webflow Product types each template link applies to. The link field is shown
# only for these types, and is cleared when a product moves to another type.
WEBFLOW_PRODUCT_LINK_TYPES = {
	"fixture_template": ("Fixture Template",),
	"tape_neon_template": ("LED Tape", "COB Tape", "LED Neon"),
	"controller_template": ("Controller",),
	"driver_template": ("Driver",),
	"kit_template": ("Extrusion Kit",),
	"led_sheet_template": ("LED Sheet",),
}

# Fieldname kept from the first release so restamping replaces the old tab in place.
TAB = "web_listing_tab"

# Where a product is offered: ERPNext and the portal (Active, Internal Only), and the
# website too (Active + Live, D60). Active + Live needs a Webflow Product; Active does not.
INTERNAL_STATUS = "Internal Only"
ACTIVE_STATUS = "Active"
LIVE_STATUS = "Active + Live"
STATUSES = ("Draft", ACTIVE_STATUS, LIVE_STATUS, INTERNAL_STATUS, "Discontinued", "Archived")
ACTIVE_STATUSES = (ACTIVE_STATUS, LIVE_STATUS, INTERNAL_STATUS)
# Offered to dealers on the portal (Internal Only is staff only).
DEALER_STATUSES = (ACTIVE_STATUS, LIVE_STATUS)
# New templates are internal until someone decides dealers should see them.
DEFAULT_STATUS = INTERNAL_STATUS
STATUS_FIELD = {
	"fieldname": "product_status",
	"fieldtype": "Select",
	"label": "Product Status",
	"options": "\n".join(STATUSES),
	"default": DEFAULT_STATUS,
	"in_list_view": 1,
	"in_standard_filter": 1,
	"description": (
		"Active: offered to dealers and staff in ERPNext and the portal, not listed on the website. "
		"Active + Live: offered the same way and listed on the website through its Webflow "
		"Product, which must be linked first. Internal Only: offered to staff only, hidden from "
		"dealers and the website. New templates start Internal Only. Draft, Discontinued and "
		"Archived are not offered."
	),
}
# Placed right after is_active, which the status now sets.
STATUS_AFTER = "is_active"
IS_ACTIVE_OVERRIDES = {"read_only": 1, "description": "Set from Product Status."}

# The template owns the link to its Webflow Product (plan 4.2). The field is editable
# while empty and read only once set; template_link.py validates it and writes the
# product's per-type link field, which is a read-only mirror.
WEBFLOW_PRODUCT_FIELD = "webflow_product"
WEBFLOW_PRODUCT_OVERRIDES = {
	"read_only": 0,
	"read_only_depends_on": "eval:doc.webflow_product",
	"description": (
		"The Webflow Product that lists this template. Pick one while empty; use Actions > "
		"Unlink Webflow Product to change it. Required when Product Status is Active + Live."
	),
}


def _section(fieldname, label):
	return {"fieldname": fieldname, "fieldtype": "Section Break", "label": label}


def _column(fieldname):
	return {"fieldname": fieldname, "fieldtype": "Column Break"}


# Layout (owner, 2026-11-01): one two-column Product Data section, then Documents, then
# Specifications & Certifications, Configurator, Kit Components, Photometrics, Colorimetry.
# Target Brands and Sublabel sit in the first section (IDENTITY_FIELDS); Other Documents and,
# where there is a Spec Sheet Details section, the weight sit above the tab (PLACED_FIELDS).
_WARRANTY = {"fieldname": "warranty_years", "fieldtype": "Int", "label": "Warranty (Years)"}
# Marketing first added this on the live site; the Webflow Product copies it from its
# template on save (set_dynamic_hero_image).
_HERO_IMAGE = {"fieldname": "hero_image", "fieldtype": "Attach Image", "label": "Hero Image"}
_DIMENSIONS_IMAGE = {
	"fieldname": "dimensions_image",
	"fieldtype": "Attach Image",
	"label": "Dimensions Image",
}

_LENGTHS = [
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
	{"fieldname": "l70_life_hours", "fieldtype": "Int", "label": "L70 Life (Hours)"},
	{"fieldname": "operating_temp_min_c", "fieldtype": "Int", "label": "Operating Temp Min (C)"},
	{"fieldname": "operating_temp_max_c", "fieldtype": "Int", "label": "Operating Temp Max (C)"},
]

_KIT_COMPONENTS = [
	_section("web_kit_components_section", "Kit Components"),
	{
		"fieldname": "kit_components",
		"fieldtype": "Table",
		"label": "Kit Components",
		"options": "ilL-Child-Webflow-Kit-Component",
	},
]

# Beam angle, charts and cone-of-light rows. With a photometry record linked they are
# copies of it (photometrics.py) and read only; without one they stay editable.
_FROM_PHOTOMETRY = {"read_only_depends_on": "eval:doc.photometry"}
_PHOTOMETRICS = [
	_section("photometric_section", "Photometrics"),
	{
		"fieldname": "photometry",
		"fieldtype": "Link",
		"label": "Photometry",
		"options": "ilL-Spec-Photometry",
		"description": "Beam angle, charts and cone of light are copied from this record on save.",
	},
	{"fieldname": "beam_angle", "fieldtype": "Float", "label": "Beam Angle", **_FROM_PHOTOMETRY},
	{
		"fieldname": "photometric_image",
		"fieldtype": "Attach Image",
		"label": "Photometric Image",
		**_FROM_PHOTOMETRY,
	},
	_column("photometric_column"),
	{
		"fieldname": "tm30_chart_image",
		"fieldtype": "Attach Image",
		"label": "TM-30 Chart",
		"read_only_depends_on": "eval:doc.colorimetry && doc.colorimetry.length",
		"description": "Copied from the featured Colorimetry row when there is one.",
	},
	{
		"fieldname": "polar_chart_image",
		"fieldtype": "Attach Image",
		"label": "Polar Chart",
		**_FROM_PHOTOMETRY,
	},
	_section("cone_of_light_section", "Cone of Light"),
	{
		"fieldname": "photometric_data",
		"fieldtype": "Table",
		"label": "Cone of Light",
		"options": "ilL-Child-Photometric-Data",
		**_FROM_PHOTOMETRY,
	},
]

# Measured color results, one row per CCT the template is sold in.
_COLORIMETRY = [
	_section("colorimetry_section", "Colorimetry"),
	{
		"fieldname": "colorimetry",
		"fieldtype": "Table",
		"label": "Colorimetry",
		"options": "ilL-Child-Template-Colorimetry",
		"description": "One row per CCT. The Featured row's TM-30 chart is shown on the product page.",
	},
]


# The configurator table (D25, D58, child ilL-Child-Webflow-Configurator-Option): the same
# name on all six templates. The Fixture template's own part_number_builder table is a
# different thing (part-number sections read by the spec sheet export) and stays.
CONFIGURATOR_FIELD = "part_no_configurator"
CONFIGURATOR_TABLE = {doctype: CONFIGURATOR_FIELD for doctype in TEMPLATE_DOCTYPES}


# The name the website and the spec sheet show; the Webflow Product's product_name mirrors it.
DISPLAY_NAME_FIELD = {
	"fieldname": "display_name",
	"fieldtype": "Data",
	"label": "Display Name",
	"description": (
		"The product name shown on the website and the spec sheet. The Webflow Product's "
		"Product Name copies it. When empty, the Template Name is used."
	),
}


CONFIGURATOR_AUTO_FIELD = {
	"fieldname": "auto_populate_configurator",
	"fieldtype": "Check",
	"label": "Calculate Configurator on Save",
	"default": "1",
	"description": (
		"When checked, the steps below are rebuilt from this template's options on every save "
		"(the Is Required choices are kept). Uncheck it to set the steps up by hand: drag the "
		"rows into order and the step numbers follow on save."
	),
}


def _configurator_table(fieldname):
	return {
		"fieldname": fieldname,
		"fieldtype": "Table",
		"label": "Part No. Configurator",
		"options": "ilL-Child-Webflow-Configurator-Option",
		"description": (
			"The configurator steps and their allowed values. The website and the dealer portal "
			"read them from here."
		),
	}


# Listing data the template owns and its Webflow Product mirrors (plan 4.1, D10, D57).
# Target Brands holds at most one enabled row (D17, D22).
TARGET_BRANDS_FIELD = {
	"fieldname": "target_brands",
	"fieldtype": "Table",
	"label": "Target Brand",
	"options": "ilL-Child-Webflow-Brand-Target",
	"description": (
		"The one brand this template is listed under. At most one row can be enabled, and "
		"one is required to link a Webflow Product or generate a spec sheet."
	),
}
SUBLABEL_FIELD = {"fieldname": "sublabel", "fieldtype": "Data", "label": "Sublabel"}

_SPEC_SHEET_PUBLIC_URL = {
	"fieldname": "spec_sheet_public_url",
	"fieldtype": "Data",
	"label": "Spec Sheet Public URL",
	"read_only": 1,
	"description": "Stable link to the current spec sheet. Set when a spec sheet is generated.",
}
OTHER_DOCUMENTS_FIELD = {
	"fieldname": "other_documents",
	"fieldtype": "Table",
	"label": "Other Documents",
	"options": "ilL-Child-Webflow-Document",
}
WEIGHT_FIELD = {
	"fieldname": "fixture_weight_per_foot_grams",
	"fieldtype": "Float",
	"label": "Fixture Weight per Foot (g)",
}

# Generated fields that sit above the Product Data tab, each right after an anchor field in
# the template's own layout (owner layout, 2026-11-02): Other Documents next to the spec
# sheet, and the weight in Spec Sheet Details where the template has that section.
PLACED_FIELDS = {
	"ilL-Fixture-Template": (
		(OTHER_DOCUMENTS_FIELD, "spec_submittal_template"),
		(WEIGHT_FIELD, "minimum_top_bend_diameter_mm"),
	),
	"ilL-Tape-Neon-Template": (
		(OTHER_DOCUMENTS_FIELD, "spec_submittal_template"),
		(WEIGHT_FIELD, "available_mountings"),
	),
	"ilL-Controller-Template": ((OTHER_DOCUMENTS_FIELD, "spec_sheet"),),
	"ilL-Driver-Template": ((OTHER_DOCUMENTS_FIELD, "spec_sheet"),),
	"ilL-Extrusion-Kit-Template": ((OTHER_DOCUMENTS_FIELD, "spec_sheet"),),
	"ilL-LED-Sheet-Template": ((OTHER_DOCUMENTS_FIELD, "spec_sheet"),),
}

# The first section of every template (owner layout, 2026-11-02). Fields not listed keep
# their order at the end of the right column.
IDENTITY_LEFT = ("template_code", "template_name", "product_status", "sublabel")
IDENTITY_RIGHT = ("product_category", "is_active", "series", "target_brands")
IDENTITY_FIELDS = (TARGET_BRANDS_FIELD, SUBLABEL_FIELD)

_SPECS_AND_CERTIFICATIONS = [
	_section("web_specs_certs_section", "Specifications & Certifications"),
	{
		"fieldname": "specifications",
		"fieldtype": "Table",
		"label": "Specifications",
		"options": "ilL-Child-Webflow-Spec-Custom",
		"description": (
			"Rows with calculated labels are rebuilt on save; rows with other labels are kept. "
			"Rows reading TBD, and a temperature range of 0 to 0, are left out (D43)."
		),
	},
	{
		"fieldname": "certifications",
		"fieldtype": "Table",
		"label": "Certifications",
		"options": "ilL-Child-Spec-Certification",
		"description": "Copied to the Webflow Product with each brand's badge images.",
	},
]

# Tape/Neon's own product_category is the tape family (LED Tape, COB Tape, LED Neon), so the
# Webflow category it is listed under is a separate field (D54).
_TAPE_WEBFLOW_CATEGORY = {
	"fieldname": "webflow_category",
	"fieldtype": "Link",
	"label": "Webflow Category",
	"options": "ilL-Webflow-Category",
	"description": "The category this template's Webflow Product is listed under.",
}

# Photometric fields a template may hold; exports read them from the template.
PHOTOMETRIC_FIELDS = ("photometric_image", "tm30_chart_image", "polar_chart_image", "photometric_data")

_FIXTURE_TAPE = {
	"lengths": True,
	"feed": True,
	"spec": True,
	"weight": True,
	"photometrics": True,
	"colorimetry": True,
}
# What each template's Product Data tab holds.
TEMPLATE_PARTS = {
	"ilL-Fixture-Template": _FIXTURE_TAPE,
	"ilL-Tape-Neon-Template": {**_FIXTURE_TAPE, "category": True},
	"ilL-Controller-Template": {},
	"ilL-Driver-Template": {},
	"ilL-Extrusion-Kit-Template": {
		"lengths": True,
		"spec": True,
		"weight": True,
		"kit": True,
		"photometrics": True,
	},
	"ilL-LED-Sheet-Template": {"spec": True, "photometrics": True, "colorimetry": True},
}


def _placed(doctype):
	return {field["fieldname"] for field, _anchor in PLACED_FIELDS[doctype]}


def _tab_fields(doctype):
	parts = TEMPLATE_PARTS[doctype]
	weight = parts.get("weight") and WEIGHT_FIELD["fieldname"] not in _placed(doctype)
	left = [
		DISPLAY_NAME_FIELD,
		_WARRANTY,
		*(_LENGTHS if parts.get("lengths") else []),
		*([WEIGHT_FIELD] if weight else []),
		*([_TAPE_WEBFLOW_CATEGORY] if parts.get("category") else []),
		*(_FEED_LENGTHS if parts.get("feed") else []),
	]
	right = [
		_HERO_IMAGE,
		_DIMENSIONS_IMAGE,
		_SPEC_SHEET_PUBLIC_URL,
		*(_SPEC_SHEET_DATA if parts.get("spec") else []),
	]
	return [
		{"fieldname": TAB, "fieldtype": "Tab Break", "label": "Product Data"},
		_section("product_data_section", "Product Data"),
		*left,
		_column("product_data_column"),
		*right,
		*_SPECS_AND_CERTIFICATIONS,
		_section("web_configurator_section", "Configurator"),
		CONFIGURATOR_AUTO_FIELD,
		_configurator_table(CONFIGURATOR_TABLE[doctype]),
		*(_KIT_COMPONENTS if parts.get("kit") else []),
		*(_PHOTOMETRICS if parts.get("photometrics") else []),
		*(_COLORIMETRY if parts.get("colorimetry") else []),
	]


# Fields some templates defined before the Product Data tab existed; they keep
# their original place and meaning.
PREEXISTING = {
	"ilL-Fixture-Template": set(),
	"ilL-Tape-Neon-Template": {"warranty_years"},
	"ilL-Controller-Template": set(),
	"ilL-Driver-Template": set(),
	"ilL-Extrusion-Kit-Template": set(),
	"ilL-LED-Sheet-Template": set(),
}


def fields_for(doctype):
	"""Product Data tab fields for one template, skipping fieldnames it already defines."""
	return [field for field in _tab_fields(doctype) if field["fieldname"] not in PREEXISTING[doctype]]


def added_fieldnames(doctype):
	"""Data-bearing fieldnames this schema adds to one template, including Product Status,
	the identity fields and the fields placed above the tab."""
	return (
		{field["fieldname"] for field in fields_for(doctype) if not field["fieldtype"].endswith("Break")}
		| {STATUS_FIELD["fieldname"]}
		| {field["fieldname"] for field in IDENTITY_FIELDS}
		| _placed(doctype)
	)


# A template's Webflow Category decides its Webflow Product's Product Type (owner, 2026-11-03).
# Tape/Neon templates hold the Webflow Category in webflow_category (D54); the others in
# product_category.
CATEGORY_PRODUCT_TYPES = {
	"extrusions": "Extrusion Kit",
	"cob-tape": "COB Tape",
	"controls": "Controller",
	"landscape": "Fixture Template",
	"led-sheets": "LED Sheet",
	"led-tape": "LED Tape",
	"linear-fixtures": "Fixture Template",
	"neon": "LED Neon",
	"power-supplies": "Driver",
}


def template_category_field(doctype):
	return "webflow_category" if doctype == "ilL-Tape-Neon-Template" else "product_category"


def template_category(template):
	"""The template's Webflow Category (a link to ilL-Webflow-Category)."""
	return template.get(template_category_field(template.doctype))
