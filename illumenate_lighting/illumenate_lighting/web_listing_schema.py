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

# Where a product is offered in ERPNext and the portal. Whether it is live on the website
# is the Webflow Product's own Active flag, so the two can differ.
INTERNAL_STATUS = "Internal Only"
STATUSES = ("Draft", "Active", INTERNAL_STATUS, "Discontinued", "Archived")
ACTIVE_STATUSES = ("Active", INTERNAL_STATUS)
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
		"Active: offered to dealers and staff. Internal Only: offered to staff in ERPNext and "
		"the portal, hidden from dealers. New templates start Internal Only. Draft, "
		"Discontinued and Archived are inactive. Whether the product is live on the website "
		"is set on its Webflow Product."
	),
}
# Placed right after is_active, which the status now sets.
STATUS_AFTER = "is_active"
IS_ACTIVE_OVERRIDES = {"read_only": 1, "description": "Set from Product Status."}


def _section(fieldname, label):
	return {"fieldname": fieldname, "fieldtype": "Section Break", "label": label}


def _column(fieldname):
	return {"fieldname": fieldname, "fieldtype": "Column Break"}


SHARED_FIELDS = [
	{"fieldname": TAB, "fieldtype": "Tab Break", "label": "Product Data"},
	_section("product_data_section", "Product Data"),
	{"fieldname": "warranty_years", "fieldtype": "Int", "label": "Warranty (Years)"},
]

_LENGTHS = [
	_section("web_lengths_section", "Lengths"),
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

# Photometric fields a template may hold; exports read them from the template.
PHOTOMETRIC_FIELDS = ("photometric_image", "tm30_chart_image", "polar_chart_image", "photometric_data")

TYPE_FIELDS = {
	"ilL-Fixture-Template": _LENGTHS
	+ _FEED_LENGTHS
	+ _SPEC_SHEET_DATA
	+ _WEIGHT
	+ _PHOTOMETRICS
	+ _COLORIMETRY,
	"ilL-Tape-Neon-Template": _LENGTHS
	+ _FEED_LENGTHS
	+ _SPEC_SHEET_DATA
	+ _WEIGHT
	+ _PHOTOMETRICS
	+ _COLORIMETRY,
	"ilL-Controller-Template": [],
	"ilL-Driver-Template": [],
	"ilL-Extrusion-Kit-Template": _LENGTHS + _SPEC_SHEET_DATA + _WEIGHT + _KIT_COMPONENTS + _PHOTOMETRICS,
	"ilL-LED-Sheet-Template": _SPEC_SHEET_DATA + _PHOTOMETRICS + _COLORIMETRY,
}


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
	return [
		field
		for field in SHARED_FIELDS + TYPE_FIELDS[doctype]
		if field["fieldname"] not in PREEXISTING[doctype]
	]


def added_fieldnames(doctype):
	"""Data-bearing fieldnames this schema adds to one template, Product Status included."""
	return {
		field["fieldname"] for field in fields_for(doctype) if not field["fieldtype"].endswith("Break")
	} | {STATUS_FIELD["fieldname"]}
