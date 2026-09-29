# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Where spec artwork can be attached, shared by the asset pack importer and the YAML builder.

No Frappe imports: the YAML builder CLI uses this offline.
"""

MANIFEST = "assets_manifest.json"
FORMAT = "ill-spec-asset-pack"
SOURCE_TYPES = (".svg", ".png", ".jpg", ".jpeg", ".tif", ".tiff")
FILE_URL_PREFIXES = ("/files/", "/private/files/")

SPEC_ASSET_PARENTS = (
	"ilL-Webflow-Product",
	"ilL-Spec-Profile",
	"ilL-Spec-Lens",
	"ilL-Spec-Accessory",
	"ilL-Spec-LED Tape",
	"ilL-Tape-Neon-Template",
	"ilL-Extrusion-Kit-Template",
)
# table -> (parent doctypes, file field, row fields accepted from a manifest, fields identifying a row)
TABLES = {
	"spec_assets": (
		SPEC_ASSET_PARENTS,
		"file",
		(
			"asset_role",
			"title",
			"feed_direction",
			"bend_axis",
			"display_order",
			"is_placeholder",
			"placeholder_note",
		),
		("asset_role", "title", "feed_direction", "bend_axis"),
	),
	"document_logos": (
		("ilL-Webflow-Brand",),
		"logo",
		("spec_line", "is_placeholder", "placeholder_note"),
		("spec_line",),
	),
}
# doctype -> single artwork fields
FIELDS = {
	"ilL-Attribute-Output Voltage": ("spec_icon",),
	"ilL-Attribute-Environment Rating": ("spec_icon",),
	"ilL-Attribute-Certification": ("badge_image",),
}
ASSET_ROLES = (
	"Hero",
	"Product Photo",
	"Cross Section",
	"Side View",
	"Dimension Drawing",
	"Feed Drawing",
	"Bend Drawing",
	"Accessory Drawing",
)
SPEC_LINES = ("SW", "DW", "TW", "FS", "CC", "PS", "OTHER")


def is_uploaded(value):
	"""True for values that already point at a site File or a URL (not a local asset path)."""
	return isinstance(value, str) and value.startswith((*FILE_URL_PREFIXES, "http://", "https://"))
