"""Version 2 LED Sheet engineering bundles and pinned ERP artifacts."""

import json
import math

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	canonical_json,
	fingerprint,
	finite_number,
	parse_bool,
)
from illumenate_lighting.illumenate_lighting.api.power_planner import plan_power

ENGINE_VERSION = "led-sheet-2"
COUNT_UOMS = {"Nos", "Unit", "Each"}


def electrical_groups(panels, watts_per_panel, max_panels_per_feed):
	"""Use full panel watts for every channel mode, including Tunable White."""
	count = finite_number(panels, minimum=1, field="panel count")
	limit = finite_number(max_panels_per_feed, minimum=1, field="maximum panels per feed")
	watts = finite_number(watts_per_panel, minimum=0, field="panel watts")
	if not count.is_integer() or not limit.is_integer() or watts <= 0:
		raise ValueError("Panel count and feed limit must be positive integers; panel watts must be positive")
	if count > 10000:
		raise ValueError("Coverage exceeds 10,000 panels; engineering review is required")
	return [
		{
			"group_number": i + 1,
			"sheet_count": min(int(limit), int(count) - offset),
			"group_watts": min(int(limit), int(count) - offset) * watts,
			"leader_cable_qty": 1,
		}
		for i, offset in enumerate(range(0, int(count), int(limit)))
	]


def _drivers(template, spec, protocol=None):
	from illumenate_lighting.illumenate_lighting.api.driver_catalog import candidates

	return candidates(
		"ilL-LED-Sheet-Template", template, spec.input_voltage, spec.get("input_protocol"), protocol
	)


def feed_limit(watts_per_panel, candidates, maximum=None):
	"""Approved eligible drivers define feed capacity; optional sheet limit can lower it."""
	watts = finite_number(watts_per_panel, minimum=0, field="full panel watts")
	if watts <= 0:
		raise ValueError("Full panel wattage must be positive")
	capacities = []
	for driver in candidates:
		factor = finite_number(driver["usable_load_factor"], minimum=0)
		outputs = finite_number(driver["outputs_count"], minimum=1)
		if not 0 < factor <= 1 or not outputs.is_integer():
			raise ValueError("Driver load factor or output count is invalid")
		total = finite_number(driver["max_wattage"], minimum=0)
		per_output = finite_number(driver["max_wattage_per_output"], minimum=0)
		capacities.append(math.floor((min(total, per_output) * factor + 1e-9) / watts))
	limit = max(capacities, default=0)
	if maximum not in (None, "", 0, "0"):
		approved = finite_number(maximum, minimum=1, field="maximum panels per feed")
		if not approved.is_integer():
			raise ValueError("Maximum panels per feed must be an integer")
		limit = min(limit, int(approved))
	if limit < 1:
		raise ValueError(
			"No eligible driver output can carry one panel at full wattage within its usable limits"
		)
	return limit


def _component(item_code, qty, role):
	if not item_code:
		raise ValueError(f"An approved {role} Item is required")
	item = frappe.db.get_value("Item", item_code, ["stock_uom", "disabled"], as_dict=True)
	if not item or item.disabled or item.stock_uom not in COUNT_UOMS:
		raise ValueError(
			f"{item_code}: {role} requires an active, count-based Item; bulk cable needs an explicit length mapping"
		)
	return {
		"item_code": item_code,
		"qty": qty,
		"uom": item.stock_uom,
		"stock_uom": item.stock_uom,
		"role": role,
	}


def resolve(result, template, spec):
	"""Complete the server calculation before assigning a reusable identity."""
	include = parse_bool(result["include_power_supply"])
	maximum = spec.get("max_panels_per_feed")
	if not include and maximum not in (None, "", 0, "0"):
		# An approved explicit feed limit describes customer-supplied power without needing a saleable driver.
		limit = finite_number(maximum, minimum=1, field="maximum panels per feed")
		if not limit.is_integer():
			raise ValueError("Maximum panels per feed must be an integer")
		candidates, revisions = [], {}
	else:
		candidates, revisions = _drivers(template.name, spec, result.get("dimming_protocol_code"))
		limit = feed_limit(result["watts_per_panel"], candidates, maximum)
	groups = electrical_groups(result["panels_needed"], result["watts_per_panel"], limit)
	plan = plan_power(
		[{"run_key": str(g["group_number"]), "watts": g["group_watts"]} for g in groups],
		candidates,
		include_power=include,
	)
	for allocation in plan["allocations"]:
		group = groups[int(allocation["run_key"]) - 1]
		driver = revisions[allocation["item_code"]]
		group.update(
			{
				"compatible_driver": allocation["item_code"],
				"driver_spec": driver["name"],
				"driver_max_wattage": driver["max_wattage"],
				"supply_number": allocation["supply"],
				"output_number": allocation["output"],
			}
		)
	plan["dependency_revisions"] = {d["driver_item"]: revisions[d["driver_item"]] for d in plan["drivers"]}
	components = [
		_component(spec.item, result["panels_needed"], "panels"),
		_component(template.jumper_cable_item, 2 * result["panels_needed"], "jumpers"),
		_component(template.leader_cable_item, len(groups), "leaders"),
	]
	components.extend(_component(d["driver_item"], d["qty"], "power") for d in plan["drivers"])
	result.update(
		{
			"groups": groups,
			"total_groups": len(groups),
			"panels_per_group": [g["sheet_count"] for g in groups],
			"leader_cable_qty": len(groups),
			"power_supplies": [dict(d) for d in plan["drivers"]],
			"power_plan": plan,
			"components": components,
			"engine_version": ENGINE_VERSION,
			"bundle_mode": "Bundle",
		}
	)
	return result


def seal(result, spec):
	"""Price-free snapshot. A commercial price change cannot rename a build."""
	excluded = {"pricing", "msrp", "total_msrp", "config_hash", "build_snapshot_json", "power_supplies"}
	snapshot = {key: value for key, value in result.items() if key not in excluded}
	snapshot["sheet_engineering"] = {
		key: spec.get(key)
		for key in (
			"input_voltage",
			"input_protocol",
			"max_panels_per_feed",
			"cut_interval_width_in",
			"cut_interval_height_in",
			"total_sheet_lumens",
			"sheet_width_ft",
			"sheet_height_ft",
			"sheet_area_sqft",
			"watts_per_sqft",
			"lumens_per_sqft",
			"led_package",
			"cct",
			"cri",
			"ip_rating",
		)
	}
	result["build_snapshot_json"] = canonical_json(snapshot)
	result["config_hash"] = fingerprint(snapshot)
	return result


def snapshot(doc):
	if doc.get("engine_version") != ENGINE_VERSION or doc.get("bundle_mode") != "Bundle":
		raise ValueError(
			"Reconfigure this legacy LED Sheet before creating new commercial or manufacturing artifacts"
		)
	result = json.loads(doc.build_snapshot_json or "{}")
	if fingerprint(result) != doc.config_hash or result.get("engine_version") != ENGINE_VERSION:
		raise ValueError("LED Sheet build snapshot does not match its immutable identity")
	return result


def item_code(doc):
	snapshot(doc)
	return "ILL-SHEET-" + doc.config_hash


def bom_items(doc):
	return [
		{key: row[key] for key in ("item_code", "qty", "uom", "stock_uom")}
		for row in snapshot(doc)["components"]
	]


def current_estimate(doc):
	"""Reprice a pinned build for a new transaction without changing its history."""
	from illumenate_lighting.illumenate_lighting.api.tape_neon_pricing import selling_amount

	build = snapshot(doc)
	template = frappe.get_doc("ilL-LED-Sheet-Template", doc.sheet_template)
	selected = build["options"]
	panel_rate = finite_number(template.price_per_sheet_msrp, minimum=0, field="panel MSRP")
	for option_type, value in selected.items():
		matches = [
			row
			for row in template.allowed_options
			if row.is_active and row.option_type == option_type and row.attribute_link == value
		]
		if len(matches) != 1:
			raise ValueError(
				f"{option_type} no longer has one approved price; review this Sheet before quoting"
			)
		panel_rate += finite_number(matches[0].msrp_adder, minimum=0, field="option MSRP")
	total = 0
	for row in build["components"]:
		current_uom = frappe.db.get_value("Item", row["item_code"], "stock_uom")
		if current_uom != row["stock_uom"]:
			raise ValueError("A component stock UOM has changed; review this build before repricing")
		total += (
			row["qty"] * panel_rate
			if row["role"] == "panels"
			else selling_amount(row["item_code"], row["qty"])
		)
	return round(total, 2)


def _totals(rows):
	result = {}
	for row in rows:
		key = (row.get("item_code"), row.get("stock_uom") or row.get("uom"))
		qty = finite_number(
			row.get("stock_qty") if row.get("stock_qty") is not None else row.get("qty"), minimum=0
		)
		result[key] = result.get(key, 0) + qty
	return result


def assert_bom(doc, bom):
	expected, actual = _totals(bom_items(doc)), _totals(bom.items)
	if (
		bom.item != item_code(doc)
		or bom.docstatus != 1
		or not bom.is_active
		or float(bom.quantity) != 1
		or expected.keys() != actual.keys()
		or any(not math.isclose(qty, actual[key], rel_tol=0, abs_tol=1e-6) for key, qty in expected.items())
	):
		raise ValueError("LED Sheet BOM no longer matches the pinned bundle; engineering review is required")


def ensure_artifacts(doc):
	"""Serialize by configured record; failures roll back the entire local build."""
	from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
		ILLUMENATE_BRAND,
		_ensure_brand_exists,
		_ensure_item_group_exists,
	)

	frappe.db.savepoint("sheet_artifacts")
	try:
		frappe.db.sql("select name from `tabilL-Configured-LED-Sheet` where name=%s for update", doc.name)
		doc.reload()
		code = item_code(doc)
		if doc.configured_item and doc.configured_item != code:
			raise ValueError("LED Sheet Item does not match this build")
		for component in bom_items(doc):
			master = frappe.db.get_value(
				"Item", component["item_code"], ["stock_uom", "disabled"], as_dict=True
			)
			if not master or master.disabled or master.stock_uom != component["stock_uom"]:
				raise ValueError(
					"A Sheet component is disabled or its stock UOM changed; engineering review is required"
				)
		_ensure_item_group_exists("Configured LED Sheets")
		_ensure_brand_exists(ILLUMENATE_BRAND)
		if not frappe.db.exists("Item", code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": doc.part_number or doc.name,
					"item_group": "Configured LED Sheets",
					"stock_uom": "Nos",
					"is_stock_item": 1,
					"brand": ILLUMENATE_BRAND,
					"description": f"LED Sheet bundle {doc.name}; build {doc.config_hash}",
				}
			).insert(ignore_permissions=True)
		item = frappe.db.get_value("Item", code, ["stock_uom", "disabled"], as_dict=True)
		if item.disabled or item.stock_uom != "Nos":
			raise ValueError("Configured Sheet Item must be active and measured in complete bundles (Nos)")
		bom_name = doc.bom or frappe.db.get_value(
			"BOM", {"item": code, "is_active": 1, "docstatus": 1}, "name"
		)
		if bom_name:
			bom = frappe.get_doc("BOM", bom_name)
			assert_bom(doc, bom)
		else:
			bom = frappe.get_doc(
				{
					"doctype": "BOM",
					"item": code,
					"quantity": 1,
					"is_active": 1,
					"is_default": 1,
					"with_operations": 0,
					"items": bom_items(doc),
					"remarks": f"LED Sheet bundle {doc.name}; build {doc.config_hash}",
				}
			)
			bom.insert(ignore_permissions=True)
			bom.flags.ignore_permissions = True
			bom.submit()
			assert_bom(doc, bom)
		doc.configured_item, doc.bom = code, bom.name
		doc.save(ignore_permissions=True)
		return {"item_code": code, "bom_name": bom.name, "success": True, "messages": []}
	except Exception:
		frappe.db.rollback(save_point="sheet_artifacts")
		raise
