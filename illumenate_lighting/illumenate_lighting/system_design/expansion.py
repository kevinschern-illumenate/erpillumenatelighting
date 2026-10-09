# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Schedule lines and their configured builds, shaped for the designer (plan H8.1, WP-2.3).

Python serializes each line and each configured record into a neutral ``Line`` / ``Build`` pair and
works out readiness; ``packages/engine/src/expand.ts`` turns them into runs (one per build copy and
electrical run). The pure functions here take plain dicts so the unit tests can run without a site.
"""

import json
import re

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.system_design import catalog, units

FIXTURE = "ilL-Configured-Fixture"
TAPE_NEON = "ilL-Configured-Tape-Neon"
SHEET = "ilL-Configured-LED-Sheet"
GROUP = "ilL-Configured-Group"
# Line link field → configured doctype, in the order a line is checked.
CONFIGURED_LINKS = (
	("configured_group", GROUP),
	("configured_fixture", FIXTURE),
	("configured_tape_neon", TAPE_NEON),
	("configured_led_sheet", SHEET),
)
# Appendix B.2: ERP environment ratings (by label or code) → engine environment. Damp is treated as wet
# for wire selection (conservative). Unknown values leave the environment blank for the dealer to pick.
ENVIRONMENT_RULES = (
	(r"direct[- ]?burial|burial", "direct-burial"),
	(r"outdoor|exterior|exposed", "outdoor-exposed"),
	(r"\bwet\b|\bdamp\b", "wet"),
	(r"plenum", "plenum"),
	(r"\bdry\b|indoor|interior", "dry-concealed"),
)
# ilL-Attribute-Power Feed Type.directionality → feed method of a run fed from that point.
FEED_METHODS = {"Start": "end", "End": "end", "Middle": "center"}


# --- Pure helpers ------------------------------------------------------------------------------


def environment_for(rating, labels=None):
	"""Engine environment for an ``ilL-Attribute-Environment Rating`` name, or ``None``."""
	if not rating:
		return None
	text = " ".join(str(part or "") for part in (rating, *(labels or {}).get(rating, ()))).lower()
	for pattern, value in ENVIRONMENT_RULES:
		if re.search(pattern, text):
			return value
	return None


def feed_method(directionality=None, end_fed=False):
	if directionality == "Middle":
		return "center"
	return "double-end" if end_fed else "end"


def line_key_for(line, idx):
	"""The line's ``line_key``; old lines without one fall back to ``line_id`` + position."""
	if line.get("line_key"):
		return str(line["line_key"]).replace(":", "-")
	return re.sub(r"[:\s]+", "-", f"{line.get('line_id') or 'line'}-{idx}")


def configured_ref(line):
	for field, doctype in CONFIGURED_LINKS:
		if line.get(field):
			return {"doctype": doctype, "name": line[field]}
	return None


def line_kind(line):
	if line.get("design_line_role"):
		return "writeback"
	if configured_ref(line):
		return "configured"
	if line.get("manufacturer_type") == "ACCESSORY" or line.get("accessory_item"):
		return "accessory"
	if line.get("manufacturer_type") == "OTHER":
		return "third-party"
	return "unconfigured"


def _float(value):
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	return number if number == number else None


def serialize_line(line, idx, engine_protocols):
	kind = line_kind(line)
	third_party = None
	if kind == "third-party":
		dimming = line.get("third_party_dimming")
		third_party = {
			"wattsEach": _float(line.get("watts_each")) or None,
			"inputVoltageV": _float(line.get("input_voltage_v")) or None,
			"voltageClass": line.get("voltage_class") or None,
			"drive": line.get("third_party_drive") or None,
			"mA": _float(line.get("third_party_ma")) or None,
			"dimming": engine_protocols.get(dimming) if dimming else None,
			"dimmingName": dimming or None,
			"manufacturer": line.get("manufacturer_name") or None,
			"model": line.get("fixture_model_number") or None,
		}
	return {
		"key": line_key_for(line, idx),
		"lineKey": line.get("line_key") or None,
		"lineId": line.get("line_id") or None,
		"idx": idx,
		"qty": max(int(line.get("qty") or 0), 0),
		"location": line.get("location") or "",
		"kind": kind,
		"productType": line.get("product_type") or None,
		"configured": configured_ref(line),
		"accessoryItem": line.get("accessory_item") or None,
		"powerSupplyForLine": line.get("power_supply_for_line") or None,
		"designLineRole": line.get("design_line_role") or None,
		"thirdParty": third_party,
	}


def _allocations(plan):
	"""Power-plan allocations without prices: ``run_key → (supply, output, item)``."""
	if isinstance(plan, str):
		try:
			plan = json.loads(plan or "{}")
		except ValueError:
			plan = {}
	rows = []
	for row in (plan or {}).get("allocations") or []:
		rows.append(
			{
				"runKey": str(row.get("run_key")),
				"supply": row.get("supply"),
				"output": row.get("output"),
				"itemCode": row.get("item_code"),
			}
		)
	return rows


def _run(index, length_mm, watts, method, feeds=None):
	run = {
		"runIndex": int(index),
		"lengthFt": round(float(length_mm) / units.MM_PER_FT, units.PAYLOAD_DECIMALS) if length_mm else None,
		"watts": round(float(watts or 0), units.PAYLOAD_DECIMALS),
		"feedMethod": method,
	}
	if feeds:
		run["feeds"] = feeds
	return run


def _tape_id(offering_name, context):
	offering = context["offerings"].get(offering_name)
	spec = offering and context["tapes"].get(offering.get("tape_spec"))
	if not spec:
		return None
	watts, cut = catalog.tape_group(spec, offering)
	return catalog.tape_item_id(offering["tape_spec"], watts, cut)


def _protocols(codes, context):
	"""Engine protocols for the dimming protocol names a build records (D4 gate input)."""
	found = []
	for code in codes:
		value = context["engine"].get(code) if code else None
		if value and value not in found:
			found.append(value)
	return found


def _build(doc, family, runs, context, **extra):
	issues = list(extra.pop("issues", []))
	if not runs:
		issues.append(_("No electrical runs are recorded on this build; reconfigure it"))
	return {
		"doctype": doc["doctype"],
		"name": doc["name"],
		"family": family,
		"configHash": doc.get("config_hash") or None,
		"runs": runs,
		"issues": issues,
		**extra,
	}


def linear_build(doc, context):
	"""``ilL-Configured-Fixture``: the runs table, each run fed by its own leader."""
	feed = context["feed_types"].get(doc.get("power_feed_type"))
	method = feed_method(feed, end_fed=bool(str(doc.get("feed_direction_end") or "").strip()))
	runs = [
		_run(row.get("run_index") or i, row.get("run_len_mm"), row.get("run_watts"), method)
		for i, row in enumerate(sorted(doc.get("runs") or [], key=lambda r: r.get("run_index") or 0), 1)
	]
	return _build(
		doc,
		"linear",
		runs,
		context,
		catalogId=_tape_id(doc.get("tape_offering"), context),
		environmentRating=doc.get("environment_rating") or None,
		environment=environment_for(doc.get("environment_rating"), context["environment_labels"]),
		offering=doc.get("tape_offering") or None,
		maxRunFtEffective=_float(doc.get("max_run_ft_effective")),
		totalWatts=_float(doc.get("total_watts")),
		allocations=_allocations(doc.get("power_plan_json")),
	)


def tape_neon_build(doc, context):
	"""``ilL-Configured-Tape-Neon``: jumper-connected runs from the sealed build (``connected_runs``)."""
	from illumenate_lighting.illumenate_lighting.api.tape_neon_power import connected_runs

	issues = []
	try:
		snapshot = json.loads(doc.get("build_snapshot_json") or "{}")
	except ValueError:
		snapshot = {}
	computed = snapshot.get("computed") or {}
	try:
		source = connected_runs(computed) if computed else []
	except ValueError as exc:
		source, issues = snapshot.get("runs") or [], [str(exc)]
	runs = [
		_run(row.get("run_index") or i, row.get("run_len_mm"), row.get("run_watts"), "end")
		for i, row in enumerate(source, 1)
	]
	offering = doc.get("tape_offering") or (snapshot.get("resolved_items") or {}).get("tape_offering")
	return _build(
		doc,
		"tape",
		runs,
		context,
		issues=issues,
		protocols=_protocols([snapshot.get("dimming_protocol_code")], context),
		catalogId=_tape_id(offering, context),
		environmentRating=doc.get("environment_rating") or None,
		environment=environment_for(doc.get("environment_rating"), context["environment_labels"]),
		offering=offering or None,
		maxRunFtEffective=_float(computed.get("max_run_ft_effective")),
		totalWatts=_float(doc.get("total_watts")),
		allocations=_allocations(doc.get("power_plan_json")),
	)


def sheet_build(doc, context):
	"""``ilL-Configured-LED-Sheet``: one run per sheet group (feed), no length."""
	groups = sorted(doc.get("groups") or [], key=lambda g: g.get("group_number") or 0)
	runs = [
		_run(g.get("group_number") or i, None, g.get("group_watts"), "end") for i, g in enumerate(groups, 1)
	]
	allocations = [
		{
			"runKey": str(g.get("group_number")),
			"supply": g.get("supply_number"),
			"output": g.get("output_number"),
			"itemCode": g.get("compatible_driver"),
		}
		for g in groups
		if g.get("supply_number")
	]
	return _build(
		doc,
		"sheet",
		runs,
		context,
		catalogId=f"sheet:{doc['sheet_spec']}" if doc.get("sheet_spec") else None,
		environmentRating=doc.get("selected_environment_rating") or None,
		environment=environment_for(doc.get("selected_environment_rating"), context["environment_labels"]),
		offering=None,
		maxRunFtEffective=None,
		totalWatts=_float(doc.get("total_system_watts")),
		allocations=allocations,
	)


def group_build(doc, context):
	"""``ilL-Configured-Group``: every member's circuits, in member order, as one build's runs."""
	try:
		snapshot = json.loads(doc.get("build_snapshot_json") or "{}")
	except ValueError:
		snapshot = {}
	runs, offerings, keys = [], [], {}
	for member in snapshot.get("members") or []:
		build = member.get("build") or {}
		member_runs = (build.get("computed") or {}).get("runs") or []
		for position, circuit in enumerate(member.get("circuits") or []):
			length = member_runs[position].get("run_len_mm") if position < len(member_runs) else None
			runs.append(_run(len(runs) + 1, length, circuit.get("watts"), "end"))
			keys[str(circuit.get("run_key"))] = len(runs)
		offering = (build.get("resolved_items") or {}).get("tape_offering")
		if offering:
			offerings.append(offering)
	request = snapshot.get("request") or {}
	rating = (request.get("shared") or {}).get("environment_rating")
	ids = {_tape_id(offering, context) for offering in offerings}
	allocations = [
		{**row, "runKey": str(keys.get(row["runKey"], row["runKey"]))}
		for row in _allocations(snapshot.get("power_plan"))
	]
	return _build(
		doc,
		"group",
		runs,
		context,
		protocols=_protocols([(request.get("power") or {}).get("dimming_protocol_code")], context),
		catalogId=ids.pop() if len(ids) == 1 else None,
		environmentRating=rating or None,
		environment=environment_for(rating, context["environment_labels"]),
		offering=offerings[0] if len(set(offerings)) == 1 else None,
		maxRunFtEffective=None,
		totalWatts=_float(snapshot.get("total_watts")),
		allocations=allocations,
	)


BUILDERS = {FIXTURE: linear_build, TAPE_NEON: tape_neon_build, SHEET: sheet_build, GROUP: group_build}


def readiness_summary(lines, builds, catalog_items):
	"""``catalog_items`` maps catalog id → item kind (``incomplete`` for gaps)."""
	ready, needs_data, unconfigured, gaps, missing_keys = [], [], [], [], []
	for line in lines:
		if line["kind"] in ("writeback", "accessory"):
			continue
		if not line["lineKey"]:
			missing_keys.append(line["key"])
		if line["kind"] == "unconfigured":
			unconfigured.append(line["key"])
		elif line["kind"] == "third-party":
			if (line["thirdParty"] or {}).get("wattsEach"):
				ready.append(line["key"])
			else:
				needs_data.append({"key": line["key"], "reason": _("Enter the watts for this fixture")})
		else:
			ref = line["configured"]
			build = builds.get(ref["doctype"], {}).get(ref["name"])
			if not build:
				needs_data.append({"key": line["key"], "reason": _("The configured record is missing")})
			elif build["issues"]:
				needs_data.append({"key": line["key"], "reason": "; ".join(build["issues"])})
			elif not build.get("catalogId") or catalog_items.get(build["catalogId"]) in (None, "incomplete"):
				gaps.append(
					{
						"key": line["key"],
						"catalogId": build.get("catalogId"),
						"reason": _("This product is not complete in the design catalog yet")
						if build.get("catalogId") in catalog_items
						else _("This product is not in the design catalog yet"),
					}
				)
			else:
				ready.append(line["key"])
	return {
		"ready": ready,
		"needs_data": needs_data,
		"unconfigured": unconfigured,
		"catalog_gaps": gaps,
		"missing_line_keys": missing_keys,
	}


# --- Database ----------------------------------------------------------------------------------


def _context(offering_names):
	offerings = {}
	if offering_names:
		offerings = {
			row["name"]: row
			for row in frappe.get_all(
				"ilL-Rel-Tape Offering",
				filters={"name": ["in", sorted(offering_names)]},
				fields=["name", "tape_spec", "watts_per_ft_override", "cut_increment_mm_override"],
			)
		}
	specs = sorted({row["tape_spec"] for row in offerings.values() if row.get("tape_spec")})
	tapes = {}
	if specs:
		tapes = {
			row["name"]: row
			for row in frappe.get_all(
				"ilL-Spec-LED Tape",
				filters={"name": ["in", specs]},
				fields=["name", "watts_per_foot", "cut_increment_mm", "is_free_cutting"],
			)
		}
	return {
		"offerings": offerings,
		"tapes": tapes,
		"environment_labels": {
			row["name"]: (row.get("label"), row.get("code"))
			for row in frappe.get_all("ilL-Attribute-Environment Rating", fields=["name", "label", "code"])
		},
		"feed_types": {
			row["name"]: row.get("directionality")
			for row in frappe.get_all("ilL-Attribute-Power Feed Type", fields=["name", "directionality"])
		},
	}


def _offering_names(docs):
	names = set()
	for doc in docs:
		if doc.get("tape_offering"):
			names.add(doc["tape_offering"])
		if doc["doctype"] in (TAPE_NEON, GROUP):
			try:
				snapshot = json.loads(doc.get("build_snapshot_json") or "{}")
			except ValueError:
				continue
			builds = [snapshot] + [m.get("build") or {} for m in snapshot.get("members") or []]
			for build in builds:
				offering = (build.get("resolved_items") or {}).get("tape_offering")
				if offering:
					names.add(offering)
	return names


def expand_schedule(schedule_doc, catalog_kinds):
	"""``(lines, builds, readiness)`` for a schedule; ``catalog_kinds`` maps catalog id → specs kind."""
	engine = catalog.readiness.engine_protocols()
	lines = [serialize_line(line.as_dict(), idx, engine) for idx, line in enumerate(schedule_doc.lines, 1)]
	refs = {
		(line["configured"]["doctype"], line["configured"]["name"]) for line in lines if line["configured"]
	}
	docs = []
	for doctype, name in sorted(refs):
		if frappe.db.exists(doctype, name):
			doc = frappe.get_doc(doctype, name).as_dict()
			doc["doctype"] = doctype
			docs.append(doc)
	context = {**_context(_offering_names(docs)), "engine": engine}
	builds = {}
	for doc in docs:
		builds.setdefault(doc["doctype"], {})[doc["name"]] = BUILDERS[doc["doctype"]](doc, context)
	return lines, builds, readiness_summary(lines, builds, catalog_kinds)
