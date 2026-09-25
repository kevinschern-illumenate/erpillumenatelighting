"""Continuous tape from bulk stock, distinct from cut-and-fed assemblies."""

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import finite_number, length_mm


def validate_request(selections, segments, template):
	if not template or not frappe.db.exists(
		"ilL-Tape-Neon-Template", {"name": template, "is_active": 1, "product_category": "LED Tape"}
	):
		raise ValueError("Choose an active LED Tape template for a bulk reel")
	if segments or selections.get("override_max_run_ft") not in (None, "", 0, "0"):
		raise ValueError("Bulk reels do not accept assembly segments or a run-length override")
	if finite_number(selections.get("lead_length_inches") or 0, minimum=0) != 0:
		raise ValueError("Bulk reels do not include assembled leader cables")
	if not selections.get("tape_length_value"):
		raise ValueError("Choose a positive reel length")
	mm = length_mm(selections["tape_length_value"], selections.get("tape_length_unit") or "in")
	if mm <= 0:
		raise ValueError("Choose a positive reel length")
	# Canonical inches are supported by the existing tape calculation adapter.
	selections["tape_length_value"] = round(mm / 25.4, 8)
	selections["tape_length_unit"] = "in"
	for key in ("end_feed_length_inches", "mounting_accessory_qty"):
		if finite_number(selections.get(key) or 0, minimum=0) != 0:
			raise ValueError("Bulk reels cannot contain assembly cables or mounting accessories")
	if selections.get("mounting_accessory_item") or selections.get("end_type") == "Jumper":
		raise ValueError("Bulk reels cannot contain assembly cables or mounting accessories")
	selections["ordering_mode"] = "BULK_REEL"
	selections["lead_length_inches"] = 0
	selections["feed_type"] = ""


def describe(result):
	computed = result["computed"]
	computed["ordering_mode"] = "BULK_REEL"
	computed["supply_form"] = "continuous tape from bulk stock"
	result["part_number"] += "-REEL"
	result["build_description"] = (
		f"Bulk LED tape reel: {computed['manufacturable_length_ft']:g} ft supplied continuously from bulk stock. "
		"No assembled leaders, jumpers or split-run feeds are included. "
		"Electrical runs shown are installation requirements, not physical supplied cuts."
	)
	result["messages"] = [
		message for message in result.get("messages", []) if message.get("severity") == "warning"
	]
	result["messages"].append({"severity": "info", "text": result["build_description"]})
	# Keep the electrical circuits for compatible optional supplies, while the
	# manifest owns the continuous purchased material independently of them.
	for segment in computed["segments"]:
		segment["leader_qty"] = 0


def physical_manifest(result):
	from illumenate_lighting.illumenate_lighting.api.tape_neon_build import item_row

	computed, resolved = result["computed"], result["resolved_items"]
	rows = [
		item_row(
			resolved["tape_item"], computed["manufacturable_length_mm"], "light engine", length_unit="mm"
		)
	]
	if rows[0]["stock_uom"] in {"Nos", "Unit", "Each"}:
		raise ValueError("Continuous bulk tape requires a length-based stock UOM")
	for driver in (resolved.get("driver_plan") or {}).get("drivers", []):
		rows.append(item_row(driver["driver_item"], driver["qty"], "power"))
	return rows, []
