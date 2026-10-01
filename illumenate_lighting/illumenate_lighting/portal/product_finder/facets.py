"""Facet registry: the product facts a Finder question can test.

Adding a facet is an engineering change (a PR): it needs a reader in the matching
engine. Mapping answers onto a facet is staff work in Desk (``ilL-Finder-Question``).
``doctypes`` lists the ERP attribute DocTypes a value map may point at; ``derived``
facets come from product data without value maps (light type is read from the LED
Package spectrum type).
"""

FAMILIES = (
	"Linear Fixture",
	"LED Tape",
	"LED Neon",
	"LED Sheet",
	"Extrusion Kit",
	"Driver",
	"Controller",
)
LIGHT = ("Linear Fixture", "LED Tape", "LED Neon", "LED Sheet")

FACETS = {
	"family": {"label": "Product type", "families": FAMILIES, "kind": "set", "doctypes": ()},
	"application": {
		"label": "Application",
		"families": FAMILIES,
		"kind": "set",
		"doctypes": ("ilL-Webflow-Category",),
	},
	"environment_rating": {
		"label": "Environment rating",
		"families": ("Linear Fixture", "LED Tape", "LED Neon", "Extrusion Kit", "Driver"),
		"kind": "rank",
		"doctypes": ("ilL-Attribute-Environment Rating",),
	},
	"ip_rating": {
		"label": "IP rating",
		"families": ("LED Tape", "LED Neon", "LED Sheet"),
		"kind": "rank",
		"doctypes": ("ilL-Attribute-IP Rating",),
	},
	"light_type": {
		"label": "Light type",
		"families": LIGHT,
		"kind": "set",
		"doctypes": ("ilL-Attribute-LED Package",),
		"derived": True,
	},
	"color_mode": {
		"label": "Color control",
		"families": ("Linear Fixture", "LED Tape", "LED Neon"),
		"kind": "set",
		"doctypes": ("ilL-Attribute-LED Package",),
		"derived": True,
	},
	"cct": {
		"label": "Color temperature",
		"families": LIGHT,
		"kind": "set",
		"doctypes": ("ilL-Attribute-CCT",),
	},
	"cct_range": {"label": "Tunable range", "families": LIGHT, "kind": "range", "doctypes": ()},
	# Compared numerically: an option's minimum against the CRI record's minimum_ra.
	"cri_min": {"label": "Minimum CRI", "families": LIGHT, "kind": "number", "doctypes": ()},
	"lumens_per_ft": {
		"label": "Brightness (lm/ft)",
		"families": ("Linear Fixture", "LED Tape", "LED Neon"),
		"kind": "number",
		"doctypes": (),
	},
	"mounting_method": {
		"label": "Mounting method",
		"families": ("Linear Fixture", "Extrusion Kit"),
		"kind": "set",
		"doctypes": ("ilL-Attribute-Mounting Method",),
	},
	"lens_appearance": {
		"label": "Lens appearance",
		"families": ("Linear Fixture", "Extrusion Kit"),
		"kind": "set",
		"doctypes": ("ilL-Attribute-Lens Appearance",),
	},
	"finish": {
		"label": "Finish",
		"families": ("Linear Fixture", "LED Neon", "Extrusion Kit"),
		"kind": "set",
		"doctypes": ("ilL-Attribute-Finish",),
	},
	"dimming_protocol": {
		"label": "Dimming / control protocol",
		"families": (*LIGHT, "Driver", "Controller"),
		"kind": "set",
		"doctypes": ("ilL-Attribute-Dimming Protocol",),
	},
	"output_voltage": {
		"label": "Voltage",
		"families": ("LED Tape", "Driver"),
		"kind": "set",
		"doctypes": ("ilL-Attribute-Output Voltage",),
	},
	"driver_wattage": {"label": "Driver load (W)", "families": ("Driver",), "kind": "number", "doctypes": ()},
	"controller_type": {
		"label": "Controller type",
		"families": ("Controller",),
		"kind": "set",
		"doctypes": ("ilL-Attribute-Controller Type",),
	},
	"channels": {"label": "Channels", "families": ("Controller",), "kind": "number", "doctypes": ()},
	"zones": {"label": "Zones", "families": ("Controller",), "kind": "number", "doctypes": ()},
	"wireless_protocol": {
		"label": "Wireless protocol",
		"families": ("Controller",),
		"kind": "set",
		"doctypes": (),
	},
	"controller_mounting": {
		"label": "Controller mounting",
		"families": ("Controller",),
		"kind": "set",
		"doctypes": ("ilL-Attribute-Mounting Type",),
	},
}

# Comparisons that make sense for each facet kind.
COMPARISONS = {
	"set": ("Any of",),
	"rank": ("Meets or exceeds", "Any of"),
	"number": ("At least", "Within band"),
	"range": ("Range covers",),
}

# Every DocType any facet may map to; mirrors the Value Map ``attribute_doctype`` Select.
MAPPABLE_DOCTYPES = tuple(sorted({doctype for facet in FACETS.values() for doctype in facet["doctypes"]}))


def needs_value_maps(facet: str) -> bool:
	"""Facets read through ERP attribute records need staff value maps (unless derived)."""
	spec = FACETS.get(facet) or {}
	return bool(spec.get("doctypes")) and not spec.get("derived")
