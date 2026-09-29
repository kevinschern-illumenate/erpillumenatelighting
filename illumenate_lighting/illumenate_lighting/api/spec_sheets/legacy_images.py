# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Move InDesign-era ``custom_image_*`` values on ilL-Webflow-Product into ``spec_assets``.

The ``custom_image_*`` columns were added with Customize Form for the InDesign data
merge and mostly hold paths on the designer's Mac. Values that already point at an
ERPNext File become ``spec_assets`` rows on the same Webflow Product; everything else
is reported so marketing can upload it through the asset importer.

Staff can read the report at any time from the System Console:

	print(frappe.call("illumenate_lighting.illumenate_lighting.api.spec_sheets.legacy_images.report"))
"""

import hashlib
from urllib.parse import urlsplit

import frappe

from illumenate_lighting.illumenate_lighting.api.spec_sheets.svg import (
	FILE_URL_PREFIXES,
	IMAGE_TYPES,
	has_fpo,
)

PRODUCT = "ilL-Webflow-Product"

# (image column, spec asset role, caption column)
MOVED = (
	("custom_image_hero", "Hero", None),
	("custom_image_component_1_hero", "Product Photo", "custom_component_1_title"),
	("custom_image_component_2_hero", "Product Photo", "custom_component_2_title"),
	("custom_image_component_3_hero", "Product Photo", "custom_component_3_title"),
	("custom_image_dimensions_1", "Dimension Drawing", None),
	("custom_image_dimensions_2", "Dimension Drawing", "custom_dimensions_2_title"),
	("custom_image_dimensions_3", "Dimension Drawing", "custom_dimensions_3_title"),
	("custom_image_dimensions_4", "Dimension Drawing", "custom_dimensions_4_title"),
	("custom_image_acc_dims_1", "Accessory Drawing", "custom_acc_1_title"),
	("custom_image_acc_dims_2", "Accessory Drawing", "custom_acc_2_title"),
	("custom_image_acc_dims_3", "Accessory Drawing", "custom_acc_3_title"),
	("custom_image_acc_dims_4", "Accessory Drawing", "custom_acc_4_title"),
	("custom_image_acc_dims_5", "Accessory Drawing", "custom_acc_5_title"),
)

# Artwork that is shared, not per product: it lives on the brand profile and the
# attribute masters now, so these columns are reported and never copied.
SHARED = {
	"custom_image_illumenate_logo": "Brand document logos (ilL-Webflow-Brand)",
	"custom_image_spec_line": "Drawn from spec_lines.json; no upload needed",
	"custom_image_etl_rated_icon": "ilL-Attribute-Certification badge_image",
	"custom_image_ul_rated_icon": "ilL-Attribute-Certification badge_image",
	"custom_image_5v_dc_icon": "ilL-Attribute-Output Voltage spec_icon",
	"custom_image_12v_dc_icon": "ilL-Attribute-Output Voltage spec_icon",
	"custom_image_24v_dc_icon": "ilL-Attribute-Output Voltage spec_icon",
	"custom_image_120v_dc_icon": "ilL-Attribute-Output Voltage spec_icon",
	"custom_image_dry_rated_icon": "ilL-Attribute-Environment Rating spec_icon",
	"custom_image_damp_rated_icon": "ilL-Attribute-Environment Rating spec_icon",
	"custom_image_wet_rated_icon": "ilL-Attribute-Environment Rating spec_icon",
}


def classify(value, site_host=None):
	"""``(kind, value)``: ``blank``, ``file`` (a File URL path), ``external`` or ``local``."""
	value = (value or "").strip()
	if not value:
		return "blank", ""
	if value.startswith(FILE_URL_PREFIXES):
		return "file", value.split("?", 1)[0]
	parts = urlsplit(value)
	if parts.scheme in ("http", "https"):
		if (
			site_host
			and parts.netloc.lower() == site_host.lower()
			and parts.path.startswith(FILE_URL_PREFIXES)
		):
			return "file", parts.path
		return "external", value
	return "local", value


def plan_product(values, existing_files, site_host=None, file_exists=lambda url: True):
	"""Rows to add to one product's ``spec_assets`` and the columns left for people to fix."""
	rows, issues = [], []
	orders = {}
	seen = set(existing_files)
	for column, role, caption in MOVED:
		kind, value = classify(values.get(column), site_host)
		if kind == "blank":
			continue
		orders[role] = orders.get(role, 0) + 1
		if kind != "file":
			issues.append({"column": column, "value": value, "problem": _PROBLEMS[kind]})
		elif not file_exists(value):
			issues.append({"column": column, "value": value, "problem": "No File record with this URL"})
		elif _suffix(value) not in IMAGE_TYPES:
			issues.append(
				{
					"column": column,
					"value": value,
					"problem": "Convert to SVG (drawings) or PNG/JPEG (photos)",
				}
			)
		elif value not in seen:
			seen.add(value)
			rows.append(
				{
					"asset_role": role,
					"file": value,
					"title": (values.get(caption) or "").strip() if caption else "",
					"display_order": orders[role],
				}
			)
	for column, home in SHARED.items():
		kind, value = classify(values.get(column), site_host)
		if kind != "blank":
			issues.append({"column": column, "value": value, "problem": f"Shared artwork; set it on {home}"})
	return rows, issues


_PROBLEMS = {
	"local": "Local path (designer's computer); upload the file",
	"external": "External URL; upload the file to ERPNext",
}


def _suffix(url):
	name = url.rsplit("/", 1)[-1]
	return "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _legacy_columns():
	meta = frappe.get_meta(PRODUCT)
	wanted = [column for column, _role, caption in MOVED for column in (column, caption) if column]
	return [column for column in dict.fromkeys([*wanted, *SHARED]) if meta.has_field(column)]


def _site_host():
	return urlsplit(frappe.utils.get_url()).netloc


def _file_name(url):
	return frappe.db.get_value("File", {"file_url": url}, "name")


def run(dry_run=True):
	"""Plan (and unless ``dry_run``, apply) the move for every Webflow Product."""
	columns = _legacy_columns()
	if not columns:
		return {"products": 0, "moved": 0, "issues": []}
	existing = {}
	for row in frappe.get_all(
		"ilL-Child-Spec-Asset",
		filters={"parenttype": PRODUCT, "parentfield": "spec_assets"},
		fields=["parent", "file", "idx"],
	):
		existing.setdefault(row.parent, {"files": set(), "idx": 0})
		existing[row.parent]["files"].add(row.file)
		existing[row.parent]["idx"] = max(existing[row.parent]["idx"], row.idx or 0)
	moved, issues, products = 0, [], 0
	site_host = _site_host()
	for product in frappe.get_all(PRODUCT, fields=["name", *columns], order_by="name asc"):
		products += 1
		current = existing.get(product.name, {"files": set(), "idx": 0})
		rows, problems = plan_product(product, current["files"], site_host, lambda url: bool(_file_name(url)))
		issues.extend({"product": product.name, **problem} for problem in problems)
		for row in rows:
			moved += 1
			if dry_run:
				continue
			current["idx"] += 1
			_insert_row(product.name, current["idx"], row)
	return {"products": products, "moved": moved, "issues": issues, "dry_run": bool(dry_run)}


def _insert_row(product, idx, row):
	from illumenate_lighting.illumenate_lighting.api.spec_sheets.site import _file_content

	content = _file_content(row["file"])
	placeholder = row["file"].lower().endswith(".svg") and has_fpo(content)
	frappe.get_doc(
		{
			"doctype": "ilL-Child-Spec-Asset",
			"parent": product,
			"parenttype": PRODUCT,
			"parentfield": "spec_assets",
			"idx": idx,
			**row,
			"sha256": hashlib.sha256(content).hexdigest(),
			"is_placeholder": 1 if placeholder else 0,
			"placeholder_note": "Contains FPO magenta artwork" if placeholder else "",
		}
	).db_insert()


@frappe.whitelist(methods=["POST"])
def report():
	"""What still needs uploading, per product and column (no changes are made)."""
	frappe.only_for("System Manager")
	return run(dry_run=True)
