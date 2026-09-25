"""Physical tape/neon materials, without price or mutable master timestamps."""

import json

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	cable_stock_quantity,
	fingerprint,
	finite_number,
)


def item_row(item_code, qty, role, *, length_unit=None):
	item = (
		frappe.db.get_value(
			"Item", item_code, ["stock_uom", "disabled", "ill_cable_assembly_length_mm"], as_dict=True
		)
		if item_code
		else None
	)
	if not item or item.disabled:
		raise ValueError(f"An active {role} Item is required")
	qty = finite_number(qty, minimum=0, field=role + " quantity")
	if length_unit:
		qty = cable_stock_quantity(
			qty, length_unit, item.stock_uom, assembly_length_mm=item.ill_cable_assembly_length_mm or None
		)
	elif item.stock_uom not in {"Nos", "Unit", "Each"}:
		raise ValueError(f"{role} must use an approved count-based Item")
	if qty <= 0:
		raise ValueError(f"{role} quantity must be positive")
	return {
		"item_code": item_code,
		"qty": qty,
		"uom": item.stock_uom,
		"stock_uom": item.stock_uom,
		"role": role,
	}


def physical_manifest(result, *, additional_feed_mm=0):
	if result["computed"].get("ordering_mode") == "BULK_REEL":
		from illumenate_lighting.illumenate_lighting.api.tape_reels import physical_manifest as reel_manifest

		return reel_manifest(result)
	computed, resolved = result["computed"], result["resolved_items"]
	segments = computed.get("segments") or []
	if not segments:
		raise ValueError("The tape/neon build needs a physical segment plan")
	components, cables = [], []
	for index, segment in enumerate(segments):
		if segment.get("end_type") == "Jumper" and index == len(segments) - 1:
			raise ValueError("An outgoing jumper must connect to a following segment")
		components.append(
			item_row(
				resolved.get("tape_item"),
				segment["manufacturable_length_mm"],
				"light engine",
				length_unit="mm",
			)
		)
		lead = finite_number(segment.get("start_lead_length_inches") or 0, minimum=0, field="leader length")
		previous = segments[index - 1] if index else None
		if previous and previous.get("end_type") == "Jumper":
			prior_length = finite_number(previous.get("end_feed_length_inches") or 0, minimum=0)
			if prior_length <= 0 or (lead and abs(lead - prior_length) > 1e-6):
				raise ValueError("A jumper belongs to its preceding segment; its inherited start must match")
			lead = 0  # The preceding outgoing jumper is the same physical cable.
		cuts = [
			("leader", lead * 25.4),
			(
				"jumper" if segment.get("end_type") == "Jumper" else "end leader",
				finite_number(segment.get("end_feed_length_inches") or 0, minimum=0, field="end cable length")
				* 25.4,
			),
		]
		runs = finite_number(segment.get("runs_count") or 1, minimum=1, field="run count")
		if not runs.is_integer():
			raise ValueError("Run count must be an integer")
		if runs > 1:
			extra = finite_number(additional_feed_mm, minimum=0, field="additional feed length")
			if extra <= 0:
				raise ValueError("Set the template leader allowance for additional split-run feeds")
			cuts.extend(("additional feed", extra) for _ in range(int(runs) - 1))
		for role, length in cuts:
			if not length:
				continue
			row = item_row(resolved.get("leader_cable_item"), length, role, length_unit="mm")
			components.append(row)
			cables.append({**row, "segment": index + 1, "length_mm": length})
	for driver in (resolved.get("driver_plan") or {}).get("drivers", []):
		components.append(item_row(driver["driver_item"], driver["qty"], "power"))
	return components, cables


def mounting_component(result, template):
	selections = result["selections"]
	code = selections.get("mounting_accessory_item")
	for key in ("mounting_accessory_unit_msrp", "mounting_accessory_total_msrp"):
		selections.pop(key, None)  # Client prices are never authoritative.
	if not code:
		return None
	qty = finite_number(selections.get("mounting_accessory_qty"), minimum=1, field="mounting quantity")
	if not qty.is_integer():
		raise ValueError("Mounting quantity must be a positive integer")
	maps = frappe.get_all(
		"ilL-Rel-Mounting-Accessory-Map",
		filters={
			"template_type": "ilL-Tape-Neon-Template",
			"fixture_template": template,
			"accessory_item": code,
			"is_active": 1,
		},
		fields=["environment_rating"],
	)
	environments = {selections.get("environment_rating")} | {
		s.get("ip_rating") for s in result["computed"].get("segments", [])
	}
	environments.discard(None)
	environments.discard("")
	if not maps or not all(
		any(not row.environment_rating or row.environment_rating == env for row in maps)
		for env in (environments or {None})
	):
		raise ValueError("Mounting accessory is not approved for this template and environment")
	selections["mounting_accessory_qty"] = int(qty)
	return item_row(code, qty, "mounting")


def prepare(result, template=None):
	from illumenate_lighting.illumenate_lighting.api.engineering_sources import capture

	allowance = (
		frappe.db.get_value("ilL-Tape-Neon-Template", template, "leader_allowance_mm_per_fixture")
		if template
		else 0
	)
	components, cables = physical_manifest(result, additional_feed_mm=allowance or 0)
	mounting = mounting_component(result, template)
	if mounting:
		components.append(mounting)
	result["components"], result["cables"] = components, cables
	result["engineering_sources"] = capture(
		tape_spec=result["resolved_items"].get("tape_spec"),
		tape_offering=result["resolved_items"].get("tape_offering"),
	)
	if frappe.flags.get("ill_product_download"):
		return result
	from illumenate_lighting.illumenate_lighting.api.tape_neon_pricing import price_result

	return price_result(result, template)


def snapshot(doc):
	build = json.loads(doc.get("build_snapshot_json") or "{}")
	if (
		doc.get("build_schema_version") != 2
		or fingerprint(build) != doc.config_hash
		or not build.get("components")
	):
		raise ValueError("Reconfigure this tape/neon build to obtain a verified physical material snapshot")
	return build


def current_estimate(doc):
	from illumenate_lighting.illumenate_lighting.api.tape_neon_pricing import price_result

	build = snapshot(doc)
	for row in build["components"]:
		item = frappe.db.get_value("Item", row["item_code"], ["stock_uom", "disabled"], as_dict=True)
		if not item or item.disabled or item.stock_uom != row["stock_uom"]:
			raise ValueError("A pinned tape/neon component is inactive or its stock UOM has changed")
	return price_result({**build, "product_category": doc.product_category}, doc.tape_neon_template)[
		"computed"
	]["total_price_msrp"]
