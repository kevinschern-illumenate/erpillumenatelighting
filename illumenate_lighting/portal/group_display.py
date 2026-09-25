"""Price-free group details for authorized schedule, export and document callers."""

import json

import frappe

from illumenate_lighting.illumenate_lighting.api.fixture_group_bom import description, snapshot


def details(name):
	doc = frappe.get_doc("ilL-Configured-Group", name)
	build = snapshot(doc)
	members = []
	for member in build["members"]:
		value = member["build"]
		members.append(
			{
				"key": member["member_key"],
				"geometry": member["geometry"],
				"segments": (value.get("computed") or {}).get("segments") or [],
				"cables": value.get("cables") or [],
				"feed_groups": value.get("groups") or [],
				"circuits": member["circuits"],
				"panels": value.get("panels_needed"),
			}
		)
	return {
		"name": doc.name,
		"template": doc.template,
		"family": doc.family,
		"build_hash": doc.config_hash,
		"description": description(build),
		"members": members,
		"power_plan": build["power_plan"],
		"total_watts": build["total_watts"],
		"include_power_supply": build["request"]["power"]["include_power_supply"],
	}


def stored_request(doc):
	intent = snapshot(doc)["request"]
	return {
		**intent,
		"members": [
			{"member_id": f"M{i}", "label": f"Member {i}", "input": member}
			for i, member in enumerate(intent["members"], 1)
		],
	}


def stock_components(line):
	"""Same physical stock quantities as the pinned BOM, before line quantity scaling."""
	for field, doctype in (
		("configured_group", "ilL-Configured-Group"),
		("configured_tape_neon", "ilL-Configured-Tape-Neon"),
		("configured_led_sheet", "ilL-Configured-LED-Sheet"),
	):
		if line.get(field):
			doc = frappe.get_doc(doctype, line.get(field))
			if doctype == "ilL-Configured-Group":
				build = snapshot(doc)
			else:
				build = json.loads(doc.get("build_snapshot_json") or "{}")
			return [
				(r.get("role") or "Build component", r["item_code"], r["qty"], r["stock_uom"])
				for r in build.get("components", [])
			]
	return []
