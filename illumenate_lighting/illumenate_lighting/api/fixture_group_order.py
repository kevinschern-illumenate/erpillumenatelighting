"""Order a multi-run group as a product bundle of its individually built runs.

Converting a schedule line that holds a group (to a Quotation or Sales Order):

* every run is saved as its own configured fixture / tape / neon / Sheet build,
  with a stock Item, its BOM and an MSRP Item Price, exactly as if it had been
  configured on its own line;
* the line's readable group part number becomes a non-stock Item priced at the
  group MSRP, branded as the selling company;
* a Product Bundle of that Item packs the run Items (and the group's power
  supplies, when they are included in the group).

The pinned ``ilL-Configured-Group`` stays the engineering source of truth: each
run's saved build must carry exactly the materials the group pinned for it.
"""

import math

import frappe

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build, quantities
from illumenate_lighting.illumenate_lighting.api.configuration_contract import DEFAULT_UOM

GROUP = "ilL-Configured-Group"
ITEM_GROUP = "Configured Fixture Groups"
# Configured build doctypes, the module whose ``snapshot`` verifies them, and the Work Order link field.
MEMBER_SOURCES = (
	("ilL-Configured-Fixture", "linear_build", "ill_configured_fixture"),
	("ilL-Configured-Tape-Neon", "tape_neon_build", "ill_configured_tape_neon"),
	("ilL-Configured-LED-Sheet", "led_sheet_bundle", "ill_configured_led_sheet"),
)


def member_snapshot(doctype, doc):
	from importlib import import_module

	module = next(module for name, module, _ in MEMBER_SOURCES if name == doctype)
	return import_module("illumenate_lighting.illumenate_lighting.api." + module).snapshot(doc)


def same_materials(expected, actual):
	expected, actual = quantities(expected), quantities(actual)
	return expected.keys() == actual.keys() and all(
		math.isclose(qty, actual[key], rel_tol=0, abs_tol=1e-6) for key, qty in expected.items()
	)


def build_member(request, member, label):
	"""Save one run as its own configured build and ensure its Item, BOM and MSRP."""
	from illumenate_lighting.illumenate_lighting.api.fixture_group_configurator import member_payload
	from illumenate_lighting.illumenate_lighting.portal.configuration import persist_artifact

	artifact = persist_artifact(
		request["family"], member_payload(request, member["geometry"], standalone=True)
	)
	doc = frappe.get_doc(artifact["source_doctype"], artifact["source_name"])
	if not same_materials(member["build"]["components"], member_snapshot(doc.doctype, doc)["components"]):
		raise ValueError(
			f"{label} no longer builds with the materials pinned in its group; "
			"reconfigure the group before ordering it"
		)
	if not artifact.get("bom"):
		raise ValueError(f"{label}: a BOM could not be prepared for this run")
	return artifact


def bundle_rows(members, build):
	"""Bundle contents in run order: one row per distinct Item with its count per group."""
	rows = {}
	for artifact in members:
		rows[artifact["item_code"]] = rows.get(artifact["item_code"], 0) + 1
	power = build["request"]["power"]
	if power["include_power_supply"] and not power.get("separate_supply_line"):
		for driver in build["power_plan"]["drivers"]:
			rows[driver["driver_item"]] = rows.get(driver["driver_item"], 0) + driver["qty"]
	return [{"item_code": code, "qty": qty} for code, qty in rows.items()]


def selling_company(target_doc=None):
	from illumenate_lighting.illumenate_lighting.api.pricing_utils import portal_stock_company

	return (
		(target_doc.get("company") if target_doc is not None else None)
		or frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or portal_stock_company()
	)


def _bundle_matches(code, rows):
	existing = frappe.get_all(
		"Product Bundle Item", filters={"parent": code}, fields=["item_code", "qty"], order_by="idx asc"
	)
	return sorted((r.item_code, float(r.qty)) for r in existing) == sorted(
		(r["item_code"], float(r["qty"])) for r in rows
	)


def _part_number(schedule, line, group, rows):
	"""The line's part number, re-drawn when it already names a different group bundle."""
	from illumenate_lighting.illumenate_lighting.api.group_part_number import generate, line_prefix

	code = line.get("group_part_number")
	if code and frappe.db.exists("Item", code):
		owner = frappe.db.get_value("Item", code, "ill_configured_group")
		if owner == group.name and (
			not frappe.db.exists("Product Bundle", code) or _bundle_matches(code, rows)
		):
			return code
		code = None
	if not code:
		code = generate(line_prefix(schedule, line, group.template))
		line.group_part_number = line.ill_item_code = code
		if line.get("name") and not line.get("__islocal"):
			frappe.db.set_value(
				line.doctype,
				line.name,
				{"group_part_number": code, "ill_item_code": code},
				update_modified=False,
			)
	return code


@atomic_build
def ensure_order_bundle(schedule, line, target_doc=None):
	"""Build every run, then the group's bundle Item; returns the quote/order row artifact."""
	from illumenate_lighting.illumenate_lighting.api.fixture_group_bom import (
		current_estimate,
		description,
		run_noun,
		snapshot,
	)
	from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
		_create_item_price_at_msrp,
		_ensure_brand_exists,
		_ensure_default_uom_exists,
		_ensure_item_group_exists,
	)
	from illumenate_lighting.illumenate_lighting.portal.group_display import run_labels

	group = frappe.get_doc(GROUP, line.configured_group)
	build = snapshot(group)
	labels = run_labels(line)
	members = [
		build_member(build["request"], member, labels.get(member["member_key"]) or f"Run {index}")
		for index, member in enumerate(build["members"], 1)
	]
	rows = bundle_rows(members, build)
	code = _part_number(schedule, line, group, rows)
	brand = selling_company(target_doc)
	text = description(build, labels)
	count = len(build["members"])
	if not frappe.db.exists("Item", code):
		_ensure_item_group_exists(ITEM_GROUP)
		_ensure_default_uom_exists()
		_ensure_brand_exists(brand)
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": f"{group.family} multi-run group ({count} {run_noun(group.family, count)})",
				"item_group": ITEM_GROUP,
				"stock_uom": DEFAULT_UOM,
				"is_stock_item": 0,
				"include_item_in_manufacturing": 0,
				"is_sales_item": 1,
				"brand": brand,
				"description": text,
				"ill_configured_group": group.name,
			}
		).insert(ignore_permissions=True)
	elif frappe.db.get_value("Item", code, "is_stock_item"):
		raise ValueError(f"Item {code} maintains stock and cannot be a group bundle")
	if not frappe.db.exists("Product Bundle", code):
		frappe.get_doc(
			{
				"doctype": "Product Bundle",
				"new_item_code": code,
				"description": f"Runs of configured group {group.name}",
				"items": rows,
			}
		).insert(ignore_permissions=True)
	msrp = current_estimate(group)
	messages = []
	_create_item_price_at_msrp(code, msrp, messages)
	if any(m.get("severity") == "error" for m in messages):
		raise ValueError("A current group selling price could not be saved")
	return {
		"product_type": group.family,
		"source_doctype": GROUP,
		"source_name": group.name,
		"configured_group": group.name,
		"item_code": code,
		"bom": None,
		"template_code": group.template,
		"engine_version": group.engine_version,
		"description": text,
		"msrp_unit": msrp,
		"total_msrp": msrp,
		"total_watts": build["total_watts"],
		"runs_count": len(build["power_plan"]["requirements"]),
		"configuration_snapshot": build,
		"members": members,
		"messages": messages,
	}


def bundle_members(item_code):
	"""Configured builds packed under a group bundle Item: ``[(doctype, doc, qty per group)]``.

	Returns ``None`` when ``item_code`` is not a group bundle, so callers keep
	their single-build path for historical group Items and every other row.
	"""
	if not item_code or not frappe.db.get_value("Item", item_code, "ill_configured_group"):
		return None
	if not frappe.db.exists("Product Bundle", item_code):
		return None
	members = []
	for row in frappe.get_all(
		"Product Bundle Item", filters={"parent": item_code}, fields=["item_code", "qty"], order_by="idx asc"
	):
		for doctype, _module, _field in MEMBER_SOURCES:
			name = frappe.db.get_value(doctype, {"configured_item": row.item_code}, "name")
			if name:
				members.append((doctype, frappe.get_doc(doctype, name), float(row.qty)))
				break
	return members


def bundle_units(lines):
	"""Manufactured Items per group for each bundle order line: ``{line name: {item: qty}}``."""
	codes = {line.get("item_code") for line in lines if line.get("ill_configured_group")}
	codes.discard(None)
	if not codes:
		return {}
	rows = frappe.get_all(
		"Product Bundle Item",
		filters={"parent": ["in", sorted(codes)]},
		fields=["parent", "item_code", "qty"],
	)
	built = set(
		frappe.get_all(
			"BOM",
			filters={"item": ["in", sorted({r.item_code for r in rows})], "docstatus": 1, "is_active": 1},
			pluck="item",
		)
		if rows
		else []
	)
	per_item = {}
	for row in rows:
		if row.item_code in built:
			per_item.setdefault(row.parent, {})[row.item_code] = float(row.qty)
	return {line["name"]: per_item[line["item_code"]] for line in lines if line.get("item_code") in per_item}
