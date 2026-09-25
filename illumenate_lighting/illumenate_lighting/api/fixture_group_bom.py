"""Immutable group snapshots and their single commercial Item / quantity-one BOM."""

import json

import frappe

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build, ensure_bom
from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json, fingerprint
from illumenate_lighting.illumenate_lighting.api.group_contract import ENGINE_VERSION, TEMPLATE_TYPES

DOCTYPE = "ilL-Configured-Group"


def snapshot(doc):
	build = json.loads(doc.get("build_snapshot_json") or "{}")
	if build.get("engine_version") != ENGINE_VERSION or fingerprint(build) != doc.config_hash:
		raise ValueError("The group engineering snapshot does not match its pinned identity")
	if not build.get("members") or not build.get("components"):
		raise ValueError("A group needs member instructions and physical materials")
	return build


def description(build):
	parts = [f"{build['request']['family']} group: {len(build['members'])} independent members"]
	for member in build["members"]:
		geometry = member["geometry"]
		if "segments" in geometry:
			dimensions = " + ".join(f"{s['requested_length_mm'] / 304.8:g} ft" for s in geometry["segments"])
		else:
			dimensions = f"{geometry['coverage_width_ft']:g} x {geometry['coverage_height_ft']:g} ft area"
		parts.append(member["member_key"] + ": " + dimensions)
	parts.append(
		"Power supplies included"
		if build["request"]["power"]["include_power_supply"]
		else "External power required"
	)
	return "\n".join(parts)


def current_estimate(doc):
	from illumenate_lighting.illumenate_lighting.api import led_sheet_bundle, linear_build, tape_neon_build
	from illumenate_lighting.illumenate_lighting.api.tape_neon_pricing import selling_amount

	build = snapshot(doc)
	family = build["request"]["family"]
	total = 0
	for member in build["members"]:
		member_build = member["build"]
		proxy = frappe._dict(
			{
				**member["pricing_inputs"],
				"build_schema_version": 2,
				"engine_version": member_build["engine_version"],
				"bundle_mode": "Bundle",
				"build_snapshot_json": canonical_json(member_build),
				"config_hash": fingerprint(member_build),
			}
		)
		adapter = (
			linear_build
			if family == "Linear Fixture"
			else led_sheet_bundle
			if family == "LED Sheet"
			else tape_neon_build
		)
		total += adapter.current_estimate(proxy)
	total += sum(selling_amount(d["driver_item"], d["qty"]) for d in build["power_plan"]["drivers"])
	return round(total, 2)


@atomic_build
def ensure_artifacts(doc, msrp=None):
	from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
		ILLUMENATE_BRAND,
		_create_item_price_at_msrp,
		_ensure_brand_exists,
		_ensure_item_group_exists,
	)

	frappe.db.sql("select name from `tabilL-Configured-Group` where name=%s for update", doc.name)
	doc.reload()
	build = snapshot(doc)
	code = "ILL-GRP-" + doc.config_hash
	if doc.configured_item and doc.configured_item != code:
		raise ValueError("The group Item does not match its pinned build")
	_ensure_item_group_exists("Configured Fixture Groups")
	_ensure_brand_exists(ILLUMENATE_BRAND)
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": f"{doc.family} group ({len(build['members'])} members)",
				"item_group": "Configured Fixture Groups",
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"is_sales_item": 1,
				"brand": ILLUMENATE_BRAND,
				"description": description(build),
			}
		).insert(ignore_permissions=True)
	item = frappe.db.get_value("Item", code, ["stock_uom", "disabled"], as_dict=True)
	if not item or item.disabled or item.stock_uom != "Nos":
		raise ValueError("Group Items must be active and measured in complete groups (Nos)")
	bom = ensure_bom(doc, code, build["components"])
	msrp = current_estimate(doc) if msrp is None else msrp
	messages = []
	_create_item_price_at_msrp(code, msrp, messages)
	if any(m.get("severity") == "error" for m in messages):
		raise ValueError("A current group selling price could not be saved")
	doc.configured_item, doc.bom = code, bom["bom_name"]
	doc.flags.group_engine_write = True
	doc.save(ignore_permissions=True)
	return {
		"product_type": doc.family,
		"source_doctype": DOCTYPE,
		"source_name": doc.name,
		"configured_group": doc.name,
		"item_code": code,
		"bom": bom["bom_name"],
		"template_code": doc.template,
		"engine_version": ENGINE_VERSION,
		"description": description(build),
		"msrp_unit": msrp,
		"total_msrp": msrp,
		"total_watts": build["total_watts"],
		"runs_count": len(build["power_plan"]["requirements"]),
		"configuration_snapshot": build,
		"messages": messages,
	}


@atomic_build
def persist(request):
	from illumenate_lighting.illumenate_lighting.api.configuration_contract import parse_bool
	from illumenate_lighting.illumenate_lighting.api.fixture_group_configurator import calculate
	from illumenate_lighting.illumenate_lighting.api.group_contract import normalize
	from illumenate_lighting.illumenate_lighting.portal.access import register_configured_record_handoff

	if not parse_bool(frappe.conf.get("ill_portal_fixture_groups"), default=False):
		frappe.throw("Independent fixture groups are not enabled for this site", frappe.PermissionError)

	intent = normalize(request)
	table = TEMPLATE_TYPES[intent["family"]]
	frappe.db.sql(f"select name from `tab{table}` where name=%s for update", intent["template"])
	result = calculate(request)  # Never accept a client build, price or is_valid flag.
	build = result["build"]
	name = frappe.db.get_value(DOCTYPE, {"config_hash": result["config_hash"]}, "name")
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		if snapshot(doc) != build:
			raise ValueError("Group identity collision requires engineering review")
	else:
		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"family": intent["family"],
				"template_type": table,
				"template": intent["template"],
				"engine_version": ENGINE_VERSION,
				"input_hash": result["input_hash"],
				"config_hash": result["config_hash"],
				"build_snapshot_json": result["build_snapshot_json"],
				"members": [
					{"member_key": m["member_key"], "snapshot_json": canonical_json(m)}
					for m in build["members"]
				],
				"allocations": [
					{
						"member_key": a["run_key"].split(":")[0],
						"run_key": a["run_key"],
						"supply_number": a["supply"],
						"output_number": a["output"],
						"item_code": a["item_code"],
						"watts": a["watts"],
					}
					for a in build["power_plan"]["allocations"]
				],
			}
		)
		doc.flags.group_engine_write = True
		doc.insert(ignore_permissions=True)
	artifact = ensure_artifacts(doc, result["pricing"]["msrp_unit"])
	register_configured_record_handoff(DOCTYPE, doc.name)
	return artifact
