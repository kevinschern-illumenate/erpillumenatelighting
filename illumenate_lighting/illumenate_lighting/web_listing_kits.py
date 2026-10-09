"""Generate Extrusion Kit templates for kit web listings that have none.

Run from the System Console (which does not allow imports), dry run first:

    print(frappe.call("illumenate_lighting.illumenate_lighting.web_listing_kits.generate_kit_templates", dry_run=1))

New templates are created inactive, so the portal kit configurator does not offer
them before their profile, lens, endcap and mounting maps exist. With ``link=1``
the listing's ``kit_template`` is pointed at a template this run created; an
existing same-named template is never linked, since it may be one being rebuilt. In the System Console, tick Commit for a real run.
"""

import json

import frappe

PRODUCT = "ilL-Webflow-Product"
KIT = "ilL-Extrusion-Kit-Template"

# Every kit template on the site as of 2026-10-01 used these values.
DEFAULT_STOCK_LENGTH_MM = 2000
DEFAULT_ENDCAP_QTY = 2
DEFAULT_MOUNTING_QTY = 1

COMPONENT_FIELDS = (
	"component_type",
	"component_item",
	"component_spec_doctype",
	"component_spec_name",
	"quantity",
	"notes",
	"custom_webflow_title",
	"custom_webflow_description",
)


def _component(listing, component_type, spec_doctype):
	for row in listing.get("kit_components") or []:
		if row.get("component_type") == component_type and row.get("component_spec_doctype") == spec_doctype:
			if row.get("component_spec_name"):
				return row
	return None


def plan_kit_template(listing, profile=None, lens=None):
	"""Return (template values, notes) for one kit listing.

	``listing`` is the Webflow Product as a dict; ``profile`` and ``lens`` are the
	ilL-Spec-Profile / ilL-Spec-Lens it names, as dicts, when they exist.
	"""
	notes = []
	profile = profile or {}
	lens = lens or {}
	code = listing["name"].upper()
	values = {
		"doctype": KIT,
		"template_code": code,
		"template_name": listing.get("product_name") or code,
		"is_active": 0,
		"series": listing.get("series"),
		"web_slug": listing["name"],
		"notes": f"Generated from Webflow Product {listing['name']}.",
	}

	if profile.get("name"):
		values["default_profile_spec"] = profile["name"]
		values["default_profile_family"] = profile.get("family") or code.removeprefix("KIT-")
	else:
		values["default_profile_family"] = code.removeprefix("KIT-")
		notes.append("no profile spec on the listing or its components")
	if profile.get("stock_length_mm"):
		values["profile_stock_length_mm"] = profile["stock_length_mm"]
	else:
		values["profile_stock_length_mm"] = DEFAULT_STOCK_LENGTH_MM
		notes.append(f"profile stock length assumed {DEFAULT_STOCK_LENGTH_MM} mm")

	if lens.get("name"):
		values["default_lens_spec"] = lens["name"]
		if lens.get("lens_appearance"):
			values["allowed_options"] = [
				{"option_type": "Lens Appearance", "lens_appearance": lens["lens_appearance"], "is_active": 1}
			]
	else:
		notes.append("no lens spec in the listing's components")
	if lens.get("stock_length_mm"):
		values["lens_stock_length_mm"] = lens["stock_length_mm"]
	else:
		values["lens_stock_length_mm"] = values["profile_stock_length_mm"]
		notes.append("lens stock length assumed equal to the profile's")

	values["solid_endcap_qty"] = DEFAULT_ENDCAP_QTY
	values["feed_through_endcap_qty"] = DEFAULT_ENDCAP_QTY
	notes.append(
		f"endcap quantities assumed {DEFAULT_ENDCAP_QTY} solid and {DEFAULT_ENDCAP_QTY} feed-through"
	)
	mounting = next(
		(r for r in listing.get("kit_components") or [] if r.get("component_type") == "Mounting Kit"), None
	)
	if mounting and mounting.get("quantity"):
		values["mounting_accessory_qty"] = mounting["quantity"]
	else:
		values["mounting_accessory_qty"] = DEFAULT_MOUNTING_QTY
		notes.append(f"mounting accessory quantity assumed {DEFAULT_MOUNTING_QTY}")

	values["kit_components"] = [
		{key: row.get(key) for key in COMPONENT_FIELDS if row.get(key) is not None}
		for row in listing.get("kit_components") or []
	]
	notes.append("needs profile, lens, endcap and mounting maps before it can be activated")
	return values, notes


def _as_dict(doctype, name):
	return frappe.get_doc(doctype, name).as_dict() if name and frappe.db.exists(doctype, name) else None


@frappe.whitelist(methods=["POST"])
def generate_kit_templates(dry_run=1, link=0):
	"""Create a kit template for each Extrusion Kit listing without one; return a report."""
	dry_run, link = int(dry_run), int(link)
	frappe.only_for("System Manager")
	report = []
	for name in frappe.get_all(
		PRODUCT,
		filters={"product_type": "Extrusion Kit", "kit_template": ["is", "not set"]},
		pluck="name",
		order_by="name asc",
	):
		listing = json.loads(frappe.as_json(frappe.get_doc(PRODUCT, name).as_dict()))
		profile_name = listing.get("profile_spec") or (
			_component(listing, "Profile", "ilL-Spec-Profile") or {}
		).get("component_spec_name")
		lens_name = (_component(listing, "Lens", "ilL-Spec-Lens") or {}).get("component_spec_name")
		values, notes = plan_kit_template(
			listing, _as_dict("ilL-Spec-Profile", profile_name), _as_dict("ilL-Spec-Lens", lens_name)
		)
		code = values["template_code"]
		row = {"listing": name, "template": code, "notes": notes}
		if frappe.db.exists(KIT, code):
			row["action"] = "exists; not changed"
		elif dry_run:
			row["action"] = "would create"
			row["values"] = {key: value for key, value in values.items() if key != "doctype"}
		else:
			frappe.get_doc(values).insert()
			row["action"] = "created"
		# Only link templates made here; a same-named template may be one being rebuilt.
		if link and row["action"] == "created":
			frappe.db.set_value(PRODUCT, name, "kit_template", code)
			frappe.db.set_value(KIT, code, "webflow_product", name, update_modified=False)
			row["action"] += "; listing linked"
		report.append(row)
	return report
