"""Read-only presentation adapters for authorized, immutable configured builds."""

import frappe

from illumenate_lighting.illumenate_lighting.api.fixture_group_bom import description, snapshot


def details(name):
	build = snapshot(frappe.get_doc("ilL-Configured-Group", name))
	request = build["request"]
	return {
		"family": request["family"],
		"template": request["template"],
		"description": description(build),
		"total_watts": build["total_watts"],
		"include_power_supply": request["power"]["include_power_supply"],
		"power_plan": build["power_plan"],
		"members": [
			{
				"key": member["member_key"],
				"geometry": member["geometry"],
				"segments": (member["build"].get("computed") or member["build"]).get("segments", []),
				"cables": member["build"].get("cables", []),
				"panels": member["build"].get("panels_needed"),
				"feed_groups": member["build"].get("groups", []),
				"circuits": member.get("circuits", []),
			}
			for member in build["members"]
		],
	}


def stored_request(doc):
	request = snapshot(doc)["request"]
	return {**request, "members": [{"input": geometry} for geometry in request["members"]]}


def stock_components(line):
	from illumenate_lighting.illumenate_lighting.api import led_sheet_bundle, tape_neon_build

	if line.get("configured_group"):
		build = snapshot(frappe.get_doc("ilL-Configured-Group", line.configured_group))
	elif line.get("configured_tape_neon"):
		doc = frappe.get_doc("ilL-Configured-Tape-Neon", line.configured_tape_neon)
		if doc.get("build_schema_version") != 2:
			return []
		build = tape_neon_build.snapshot(doc)
	elif line.get("configured_led_sheet"):
		doc = frappe.get_doc("ilL-Configured-LED-Sheet", line.configured_led_sheet)
		if doc.get("engine_version") != "led-sheet-2":
			return []
		build = led_sheet_bundle.snapshot(doc)
	else:
		return []
	return [
		(row.get("role") or "Component", row["item_code"], row["qty"], row["stock_uom"])
		for row in build["components"]
	]
