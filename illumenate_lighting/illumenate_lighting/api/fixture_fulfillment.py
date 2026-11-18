"""Assembled vs ship-in-pieces linear fixtures.

A linear fixture whose every user segment fits on one stick of profile and lens
is **Assembled**: one stock Item with one BOM, built by one Work Order (today's
behaviour). When any segment is longer than a stick, the whole fixture **ships
in pieces**:

* the order Item is a non-stock Product Bundle parent at the fixture's MSRP;
* each tape run becomes a configured LED tape "light engine" Item with its own
  BOM: the run's tape, its own leader (at the length configured for the
  fixture) and the jumpers inside the run. Identical runs share one Item;
* the profile and lens sticks, endcaps, straight joiners (``-JOIN-S``) and
  mounting accessories are packed from stock;
* power supplies are never in a BOM or a bundle: they are their own lines.

The decision, the light engines and the kit are sealed into the fixture's
immutable build snapshot, so the bundle and the light engine BOMs can always be
verified against it. Everything here is behind the ``fixture_fulfillment_split``
check on ilL-Production-Settings; with it off, builds are exactly as before.
"""

import json
import math

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	DEFAULT_UOM,
	cable_stock_quantity,
	canonical_json,
	finite_number,
	is_count_uom,
)

ASSEMBLED = "ASSEMBLED"
SHIP_PIECES = "SHIP_PIECES"
# Ship-in-pieces builds carry a fulfillment block, so they get their own engine version.
ENGINE_VERSION = "linear-3"
SETTINGS = "ilL-Production-Settings"
FLAG = "fixture_fulfillment_split"
LIGHT_ENGINE_GROUP = "Configured LED Tape"
# Item field linking a light engine Item back to its fixture build. Deliberately not
# custom_ill_configured_fixture, which marks the Item a row orders (build_links).
ITEM_LINK = "ill_light_engine_of"
ITEM_KEY = "ill_light_engine_key"
STRAIGHT_JOINER_SUFFIX = "-JOIN-S"
TOLERANCE_MM = 1e-6


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def split_enabled():
	"""True when new linear builds are split into Assembled / Ship in Pieces."""
	try:
		value = frappe.db.get_single_value(SETTINGS, FLAG)
	except Exception:
		return False
	# Only a real stored check value turns it on; anything else (a missing column) is off.
	return value in (1, "1", True)


def is_ship_pieces(fixture):
	"""A sealed build that ships in pieces (only linear-3 builds can)."""
	if not fixture or fixture.get("engine_version") != ENGINE_VERSION:
		return False
	return fulfillment(fixture).get("mode") == SHIP_PIECES


def fulfillment(fixture):
	"""The sealed fulfillment block of a fixture build ({} for older builds)."""
	try:
		build = json.loads(fixture.get("build_snapshot_json") or "{}")
	except (TypeError, ValueError):
		return {}
	return build.get("fulfillment") or {}


# ---------------------------------------------------------------------------
# Pure rules (no database)
# ---------------------------------------------------------------------------


def classify(segment_lengths_mm, stick_limit_mm):
	"""Assembled when every segment fits one stick; a limit of 0 means no limit."""
	limit = float(stick_limit_mm or 0)
	if limit <= 0:
		return ASSEMBLED
	return ASSEMBLED if all(float(length) <= limit + TOLERANCE_MM for length in segment_lengths_mm) else SHIP_PIECES


def sticks_for(length_mm, stick_limit_mm):
	limit = float(stick_limit_mm or 0)
	if limit <= 0 or float(length_mm) <= 0:
		return 1
	return max(1, math.ceil(float(length_mm) / limit - TOLERANCE_MM))


def segment_lengths(computed):
	"""Manufactured length of each user segment, in order."""
	pieces = computed.get("user_segments") or []
	if pieces and any(p.get("user_segment_index") for p in pieces):
		totals = {}
		for piece in pieces:
			key = int(piece.get("user_segment_index") or piece.get("segment_index") or 1)
			totals[key] = totals.get(key, 0) + float(piece.get("profile_cut_len_mm") or 0)
		return [totals[key] for key in sorted(totals)]
	return [float(computed.get("manufacturable_overall_length_mm") or 0)]


def split_runs(runs, jumper_positions, lead_mm):
	"""Tape, lead and jumpers of each run.

	``runs`` = ``[(run_index, tape_mm)]`` in order; ``jumper_positions`` =
	``[(tape position mm, cut)]`` where the position is the length of tape before
	the jumper. A jumper belongs to the run whose tape spans its position.
	"""
	result, start = [], 0.0
	for index, (run_index, tape_mm) in enumerate(runs):
		end = start + float(tape_mm)
		last = index == len(runs) - 1
		jumpers = [
			cut
			for position, cut in jumper_positions
			if (start < position <= end + TOLERANCE_MM) or (last and position > end)
		]
		result.append({"run_index": run_index, "tape_mm": float(tape_mm), "lead_mm": float(lead_mm), "jumpers": jumpers})
		start = end
	return result


def dedupe_engines(engines):
	"""Identical runs share one light engine Item: ``[{key, runs, qty, components, ...}]``."""
	grouped = {}
	for engine in engines:
		signature = canonical_json(engine["components"])
		if signature in grouped:
			grouped[signature]["runs"].append(engine["run_index"])
			grouped[signature]["qty"] += 1
		else:
			grouped[signature] = {**engine, "runs": [engine["run_index"]], "qty": 1}
	result = []
	for number, engine in enumerate(grouped.values(), 1):
		engine = dict(engine)
		engine.pop("run_index", None)
		engine["key"] = f"LE{number}"
		result.append(engine)
	return result


def merge_rows(rows):
	merged = {}
	for row in rows:
		key = (row["item_code"], row["stock_uom"])
		if key in merged:
			merged[key]["qty"] = round(merged[key]["qty"] + row["qty"], 9)
		else:
			merged[key] = {k: row[k] for k in ("item_code", "qty", "uom", "stock_uom")}
	return list(merged.values())


# ---------------------------------------------------------------------------
# Master data lookups
# ---------------------------------------------------------------------------


def stick_limit(template_default_mm, profile_item=None, lens_item=None):
	"""Shortest stick among the profile and a stick lens; 0 = no limit."""
	limits = []
	profile = frappe.db.get_value("ilL-Spec-Profile", {"item": profile_item}, "stock_length_mm") if profile_item else None
	limits.append(float(profile or template_default_mm or 0))
	if lens_item:
		lens = frappe.db.get_value(
			"ilL-Spec-Lens", {"item": lens_item}, ["stock_type", "stock_length_mm", "continuous_max_length_mm"], as_dict=True
		)
		if lens:
			length = lens.continuous_max_length_mm if lens.stock_type == "Continuous Roll" else lens.stock_length_mm
			if length:
				limits.append(float(length))
	limits = [value for value in limits if value > 0]
	return min(limits) if limits else 0


def lens_is_stick(lens_item):
	if not lens_item:
		return True
	return (frappe.db.get_value("ilL-Spec-Lens", {"item": lens_item}, "stock_type") or "Stick") != "Continuous Roll"


def straight_joiner(profile_item):
	"""The family's straight field joiner (``-JOIN-S``), or None: those pieces are butted."""
	if not profile_item:
		return None
	family = frappe.db.get_value("ilL-Spec-Profile", {"item": profile_item}, "family")
	if not family:
		return None
	families = [family]
	if len(family) > 2:
		families.append(family[:2] + "XX")
	for name in families:
		rows = frappe.get_all(
			"ilL-Spec-Accessory",
			filters={"type": "Joiner", "profile_family": name},
			fields=["item"],
			order_by="item asc",
		)
		for row in rows:
			if row.item and row.item.upper().endswith(STRAIGHT_JOINER_SUFFIX):
				if not frappe.db.get_value("Item", row.item, "disabled"):
					return row.item
	return None


def length_row(item_code, length_mm):
	item = frappe.db.get_value(
		"Item", item_code, ["stock_uom", "disabled", "ill_cable_assembly_length_mm"], as_dict=True
	)
	if not item or item.disabled:
		raise ValueError(f"Light engine material {item_code} is missing or disabled")
	qty = cable_stock_quantity(
		length_mm, "mm", item.stock_uom, assembly_length_mm=item.get("ill_cable_assembly_length_mm") or None
	)
	return {"item_code": item_code, "qty": qty, "uom": item.stock_uom, "stock_uom": item.stock_uom}


def count_row(item_code, qty):
	uom = frappe.db.get_value("Item", item_code, "stock_uom")
	if not is_count_uom(uom):
		raise ValueError(f"{item_code} must be counted in pieces to ship in a bundle")
	return {"item_code": item_code, "qty": qty, "uom": uom, "stock_uom": uom}


# ---------------------------------------------------------------------------
# Sealing a build
# ---------------------------------------------------------------------------


def _jumper_positions(doc, cables):
	"""Tape before each jumper / end-leader cut, from the physical segment plan."""
	positions, tape_before = {}, 0.0
	segment_tape = sum(float(s.get("tape_cut_len_mm") or 0) for s in doc.segments or [])
	for segment in doc.segments or []:
		tape_before += float(segment.get("tape_cut_len_mm") or 0)
		if segment_tape:
			positions[f"end-{segment.segment_index}"] = tape_before
	# Single-segment plans carry no per-stick tape: an end leader sits at the end of the tape.
	total = segment_tape or float(doc.get("tape_cut_length_mm") or 0)
	result = []
	for cut in cables:
		if cut.get("role") in ("jumper", "end leader"):
			result.append((positions.get(cut["key"], total), cut))
	return result


def plan(doc, computed, components, cables, tape_item):
	"""The fulfillment block for a fully populated, unsealed linear build.

	Returns ``(fulfillment, components)``: the components are unchanged for an
	Assembled build, and for a ship-in-pieces build are the kit plus every light
	engine, so the snapshot's materials always equal what is shipped.
	"""
	template_default = frappe.db.get_value("ilL-Fixture-Template", doc.fixture_template, "default_profile_stock_len_mm")
	limit = stick_limit(template_default, doc.get("profile_item"), doc.get("lens_item"))
	lengths = segment_lengths(computed)
	mode = classify(lengths, limit)
	block = {"mode": mode, "stick_limit_mm": limit, "segment_lengths_mm": [round(v, 3) for v in lengths]}
	if mode == ASSEMBLED:
		return block, components

	sticks = [sticks_for(length, limit) for length in lengths]
	joints = sum(sticks) - len(sticks)
	cable_items = {cut["item_code"] for cut in cables}
	light_items = cable_items | ({tape_item} if tape_item else set())
	kit = []
	for row in components:
		code = row["item_code"]
		if code in light_items:
			continue  # Tape and cable go into the light engines.
		if code in (doc.get("profile_item"), doc.get("lens_item")):
			if code == doc.get("lens_item") and not lens_is_stick(code):
				kit.append(row)
				continue
			row = {**row, "qty": sum(sticks)}
		kit.append(row)
	joiner = straight_joiner(doc.get("profile_item"))
	if joiner and joints:
		kit.append(count_row(joiner, joints))
	kit = merge_rows(kit)

	feeds = [cut for cut in cables if cut.get("role") in ("leader", "additional feed")]
	if not feeds:
		raise ValueError("A ship-in-pieces fixture needs a leader for each light engine")
	lead = feeds[0]
	runs = [(run.run_index, float(run.run_len_mm or 0)) for run in doc.runs or []]
	if not runs:
		runs = [(1, float(computed.get("total_tape_length_mm") or doc.get("tape_cut_length_mm") or 0))]
	engines = []
	for run in split_runs(runs, _jumper_positions(doc, cables), lead["length_mm"]):
		rows = []
		if tape_item and run["tape_mm"] > 0:
			rows.append(length_row(tape_item, run["tape_mm"]))
		rows.append(length_row(lead["item_code"], run["lead_mm"]))
		rows.extend(length_row(cut["item_code"], cut["length_mm"]) for cut in run["jumpers"])
		engines.append(
			{
				"run_index": run["run_index"],
				"tape_mm": run["tape_mm"],
				"lead_mm": run["lead_mm"],
				"jumpers_mm": [float(cut["length_mm"]) for cut in run["jumpers"]],
				"components": merge_rows(rows),
			}
		)
	engines = dedupe_engines(engines)
	block.update(
		{
			"sticks": sticks,
			"joints": joints,
			"joiner_item": joiner if joints else None,
			"kit": kit,
			"light_engines": engines,
		}
	)
	shipped = list(kit)
	for engine in engines:
		shipped.extend({**row, "qty": row["qty"] * engine["qty"]} for row in engine["components"])
	return block, merge_rows(shipped)


def bundle_rows(block, engine_items):
	"""Product Bundle rows: light engines first, then the kit, in sealed order."""
	rows = [{"item_code": engine_items[engine["key"]], "qty": engine["qty"]} for engine in block["light_engines"]]
	rows.extend({"item_code": row["item_code"], "qty": row["qty"]} for row in block["kit"])
	return rows


# ---------------------------------------------------------------------------
# ERP artifacts
# ---------------------------------------------------------------------------


def engine_description(fixture, engine):
	from illumenate_lighting.illumenate_lighting.api.fixture_group_bom import feet_inches

	runs = ", ".join(str(run) for run in engine["runs"])
	parts = [
		f"Light engine for {fixture.get('display_part_number') or fixture.name}",
		f"Run{'s' if len(engine['runs']) > 1 else ''} {runs}: {feet_inches(engine['tape_mm'])} tape",
		f"Leader {feet_inches(engine['lead_mm'])}",
	]
	if engine["jumpers_mm"]:
		parts.append("Jumpers " + ", ".join(feet_inches(mm) for mm in engine["jumpers_mm"]))
	parts.append("Ships with the extrusion kit; field installed")
	return "\n".join(parts)


def light_engine_item_code(fixture, order_code, key):
	"""``<order Item>-<key>``, kept unique to this build."""
	existing = frappe.db.get_value("Item", {ITEM_LINK: fixture.name, ITEM_KEY: key}, "name")
	if existing:
		return existing
	base = f"{order_code}-{key}"
	for code in (base, f"{order_code}-{fixture.config_hash[:6].upper()}-{key}"):
		if len(code) <= 140 and not frappe.db.exists("Item", code):
			return code
	return f"ILL-LE-{fixture.config_hash[:24]}-{key}"


def _ensure_engine_item(fixture, order_code, engine):
	from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
		ILLUMENATE_BRAND,
		_ensure_brand_exists,
		_ensure_default_uom_exists,
		_ensure_item_group_exists,
	)

	code = light_engine_item_code(fixture, order_code, engine["key"])
	if frappe.db.exists("Item", code):
		if frappe.db.get_value("Item", code, ITEM_LINK) != fixture.name:
			raise ValueError(f"Item {code} belongs to another build")
		return code
	_ensure_item_group_exists(LIGHT_ENGINE_GROUP)
	_ensure_brand_exists(ILLUMENATE_BRAND)
	_ensure_default_uom_exists()
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": f"Light engine {engine['key']} - {fixture.get('display_part_number') or fixture.name}"[:140],
			"item_group": LIGHT_ENGINE_GROUP,
			"stock_uom": DEFAULT_UOM,
			"is_stock_item": 1,
			"include_item_in_manufacturing": 1,
			"is_sales_item": 0,
			"brand": ILLUMENATE_BRAND,
			"description": engine_description(fixture, engine),
			ITEM_LINK: fixture.name,
			ITEM_KEY: engine["key"],
		}
	).insert(ignore_permissions=True)
	return code


def light_engines(fixture):
	"""``[(engine block, item code, bom)]`` for a ship-in-pieces fixture, as created."""
	saved = json.loads(fixture.get("light_engines_json") or "[]")
	by_key = {row["key"]: row for row in saved}
	return [
		(engine, by_key.get(engine["key"], {}).get("item_code"), by_key.get(engine["key"], {}).get("bom"))
		for engine in fulfillment(fixture).get("light_engines", [])
	]


def ensure_artifacts(fixture, order_code):
	"""Light engine Items + BOMs and the Product Bundle under ``order_code``."""
	from illumenate_lighting.illumenate_lighting.api.build_artifacts import ensure_bom

	block = fulfillment(fixture)
	if block.get("mode") != SHIP_PIECES:
		raise ValueError("This fixture build is assembled; it has no bundle")
	if frappe.db.get_value("Item", order_code, "is_stock_item"):
		raise ValueError(f"Item {order_code} maintains stock and cannot be a ship-in-pieces bundle")
	saved, engine_items = [], {}
	for engine in block["light_engines"]:
		code = _ensure_engine_item(fixture, order_code, engine)
		bom = ensure_bom(fixture, code, engine["components"])
		engine_items[engine["key"]] = code
		saved.append({"key": engine["key"], "item_code": code, "bom": bom["bom_name"], "qty": engine["qty"]})
	rows = bundle_rows(block, engine_items)
	if frappe.db.exists("Product Bundle", order_code):
		assert_bundle(order_code, rows)
	else:
		frappe.get_doc(
			{
				"doctype": "Product Bundle",
				"new_item_code": order_code,
				"description": f"Ship-in-pieces fixture {fixture.get('display_part_number') or fixture.name}",
				"items": rows,
			}
		).insert(ignore_permissions=True)
	value = canonical_json(saved)
	if fixture.get("light_engines_json") != value:
		frappe.db.set_value(fixture.doctype, fixture.name, "light_engines_json", value, update_modified=False)
		fixture.light_engines_json = value
	return {"success": True, "bom_name": None, "bundle": order_code, "light_engines": saved, "created": False, "skipped": False, "messages": []}


def assert_bundle(order_code, rows):
	existing = frappe.get_all(
		"Product Bundle Item", filters={"parent": order_code}, fields=["item_code", "qty"], order_by="idx asc"
	)
	expected = sorted((r["item_code"], round(float(r["qty"]), 6)) for r in rows)
	actual = sorted((r.item_code, round(float(r.qty), 6)) for r in existing)
	if expected != actual:
		raise ValueError("Product Bundle no longer matches the pinned ship-in-pieces build; engineering review is required")


def verify(fixture, order_code):
	"""Raise unless the bundle and every light engine BOM match the sealed build."""
	from illumenate_lighting.illumenate_lighting.api.build_artifacts import assert_bom

	engines = light_engines(fixture)
	if not engines or any(not code or not bom for _engine, code, bom in engines):
		raise ValueError("Light engines have not been prepared for this ship-in-pieces build")
	items = {}
	for engine, code, bom in engines:
		assert_bom(code, engine["components"], frappe.get_doc("BOM", bom))
		items[engine["key"]] = code
	assert_bundle(order_code, bundle_rows(fulfillment(fixture), items))
	return engines


def engine_for_item(item_code):
	"""``(fixture doc, engine block, bom)`` for a light engine Item, or None."""
	if not item_code:
		return None
	try:
		row = frappe.db.get_value("Item", item_code, [ITEM_LINK, ITEM_KEY], as_dict=True)
	except Exception:
		return None
	if not row or not row.get(ITEM_LINK):
		return None
	fixture = frappe.get_doc("ilL-Configured-Fixture", row[ITEM_LINK])
	for engine, code, bom in light_engines(fixture):
		if code == item_code:
			return fixture, engine, bom
	return None


def traveler_lines(fixture, engine=None):
	"""Readable kit and light engine instructions for travelers and pick lists."""
	from illumenate_lighting.illumenate_lighting.api.fixture_group_bom import feet_inches

	block = fulfillment(fixture)
	lines = []
	if engine is None:
		lines.append(f"Ships in pieces: a segment is longer than one {feet_inches(block['stick_limit_mm'])} stick")
		for index, (length, count) in enumerate(zip(block["segment_lengths_mm"], block["sticks"], strict=True), 1):
			lines.append(f"Segment {index}: {feet_inches(length)} from {count} stick{'s' if count > 1 else ''}")
		lines.append(
			f"Field joints: {block['joints']}; "
			+ (f"joiner {block['joiner_item']}" if block.get("joiner_item") else "pieces are butted")
		)
		for row in block["kit"]:
			lines.append(f"Pack {row['item_code']} x {finite_number(row['qty']):g}")
	engines = [engine] if engine else block.get("light_engines", [])
	for value in engines:
		lines.append(
			f"Light engine {value['key']} x {value['qty']} (run {', '.join(str(r) for r in value['runs'])}): "
			f"{feet_inches(value['tape_mm'])} tape, {feet_inches(value['lead_mm'])} leader"
			+ (", jumpers " + ", ".join(feet_inches(mm) for mm in value["jumpers_mm"]) if value["jumpers_mm"] else "")
		)
	return lines
