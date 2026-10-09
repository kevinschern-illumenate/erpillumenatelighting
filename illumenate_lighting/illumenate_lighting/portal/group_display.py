"""Read-only presentation adapters for authorized, immutable configured builds."""

import frappe

from illumenate_lighting.illumenate_lighting.api.fixture_group_bom import description, snapshot


def run_labels(line):
	"""Dealer run labels saved with a schedule line's request, keyed by member key."""
	import json

	from illumenate_lighting.illumenate_lighting.api.group_contract import member_presentation

	try:
		raw = json.loads(line.get("ill_configurator_request") or "{}")
		request = (raw.get("selections") or {}).get("group_request")
		if isinstance(request, str):
			request = json.loads(request)
		return {row["member_key"]: row["label"] for row in member_presentation(request)} if request else {}
	except (ValueError, TypeError, KeyError, AttributeError, StopIteration):
		return {}  # Labels are presentation only; the pinned build still renders without them.


def _member(index, member, label):
	from illumenate_lighting.illumenate_lighting.api.fixture_group_bom import feet_inches

	geometry, value = member["geometry"], member["build"]
	circuits = member.get("circuits", [])
	row = {
		"key": member["member_key"],
		"label": label or f"Run {index}",
		"geometry": geometry,
		"segments": (value.get("computed") or value).get("segments", []),
		"cables": value.get("cables", []),
		"panels": value.get("panels_needed"),
		"feed_groups": value.get("groups", []),
		"circuits": circuits,
		"watts": round(sum(c.get("watts") or 0 for c in circuits), 2),
	}
	if "segments" in geometry:
		segments = geometry["segments"]
		first = segments[0]
		leader = first.get("start_leader_cable_length_mm")
		if leader is None:
			leader = float(first.get("start_lead_length_inches") or 0) * 25.4
		row.update(
			length_mm=sum(s["requested_length_mm"] for s in segments),
			length=feet_inches(sum(s["requested_length_mm"] for s in segments)),
			pieces=[feet_inches(s["requested_length_mm"]) for s in segments],
			leader=feet_inches(leader) if leader else None,
		)
	else:
		row["area"] = f"{geometry['coverage_width_ft']:g} x {geometry['coverage_height_ft']:g} ft"
	return row


def details(name, labels=None):
	from illumenate_lighting.illumenate_lighting.api.fixture_group_bom import feet_inches, run_noun

	build = snapshot(frappe.get_doc("ilL-Configured-Group", name))
	request = build["request"]
	labels = labels or {}
	members = [
		_member(index, member, labels.get(member["member_key"]))
		for index, member in enumerate(build["members"], 1)
	]
	total = sum(m.get("length_mm") or 0 for m in members)
	return {
		"family": request["family"],
		"template": request["template"],
		"description": description(build),
		"total_watts": build["total_watts"],
		"include_power_supply": request["power"]["include_power_supply"],
		"separate_supply_line": bool(request["power"].get("separate_supply_line")),
		"power_plan": build["power_plan"],
		"run_noun": run_noun(request["family"], len(members)),
		"total_length": feet_inches(total) if total else None,
		"members": members,
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
