"""Manufacturing build points: how hard a configured build is to make.

This is the warehouse "Schedule Wizard" difficulty metric (CapFinal), computed from
the pinned build instead of being counted by hand:

    points = 1.0·2C + 1.3·3C + 1.4·4C + 1.5·5C + 1.75·6C      (runs by conductor count)
           + 0.75·Loose + 1.75·Wet + 2.0·FMC + 2.5·Assembly     (adders)

Counting rules (confirmed with the warehouse):

* **Run** - one powered circuit: every leader/feed cable. Bucketed by conductor count
  (LED package channels + 1 common; static white = 2C, tunable white = 3C, RGB = 4C,
  RGBW = 5C, RGBTW = 6C).
* **Wet** - one per run whose environment is wet-rated (IP67 or higher).
* **FMC** - one per jumper between segments.
* **Assembly** - one per assembled linear fixture (tape put into cut-down extrusion and
  the fixture built). Tape/neon and LED sheets are soldered, not assembled.
* **Loose** - one per bulk reel of tape. Nothing else counts as loose.

Counts are stored per unit on the BOM (the pinned build), multiplied by quantity on
Sales Order lines and Work Orders, and totalled on the Sales Order. They live in
custom fields outside the build snapshot, so they never change a build's identity.
Weights are on the ilL-Production-Settings page; changing them re-scores stored
counts without recounting builds.
"""

import json

import frappe

SETTINGS = "ilL-Production-Settings"
WET_IP = 67

RUN_KEYS = ("runs_2c", "runs_3c", "runs_4c", "runs_5c", "runs_6c")
ADDER_KEYS = ("loose", "wet", "fmc", "assembly")
COUNT_KEYS = RUN_KEYS + ADDER_KEYS

# Main-board weights from the Schedule Wizard (Warehouse sheet), plus 4C = 1.4.
DEFAULT_WEIGHTS = {
	"runs_2c": 1.0,
	"runs_3c": 1.3,
	"runs_4c": 1.4,
	"runs_5c": 1.5,
	"runs_6c": 1.75,
	"loose": 0.75,
	"wet": 1.75,
	"fmc": 2.0,
	"assembly": 2.5,
}
WEIGHT_FIELDS = {
	"runs_2c": "weight_2c",
	"runs_3c": "weight_3c",
	"runs_4c": "weight_4c",
	"runs_5c": "weight_5c",
	"runs_6c": "weight_6c",
	"loose": "weight_loose",
	"wet": "weight_wet",
	"fmc": "weight_fmc",
	"assembly": "weight_assembly",
}
# Release estimates (the workbook's ESPR "Capacity Calculator"): heavier adders.
RELEASE_DEFAULTS = {**DEFAULT_WEIGHTS, "loose": 0.5, "wet": 2.0, "fmc": 2.5, "assembly": 4.0}
DEFAULT_POINTS_PER_PERSON_DAY = 57.5
DEFAULT_PAID_HOURS = 8.5
DEFAULT_PIXEL_CONDUCTORS = 4

# Used only when an LED package has no channel count.
SPECTRUM_CONDUCTORS = {
	"Static White": 2,
	"Dim to Warm": 2,
	"Horticulture": 2,
	"Tunable White": 3,
	"RGB": 4,
	"RGB+W": 5,
	"RGBW": 5,
	"RGB+TW": 6,
	"RGBTW": 6,
}

# Configured doctype -> field on Item that points back at it (when one exists).
CONFIGURED = {
	"ilL-Configured-Fixture": "custom_ill_configured_fixture",
	"ilL-Configured-Tape-Neon": "custom_ill_configured_tape_neon",
	"ilL-Configured-LED-Sheet": None,
	"ilL-Configured-Group": "ill_configured_group",
}

# Custom field names (BOM, Sales Order Item, Sales Order share them).
FIELD = {key: "ill_" + key for key in COUNT_KEYS}
POINTS_FIELD = "ill_build_points"
STAMPED_FIELD = "ill_build_points_stamped"
WARNINGS_FIELD = "ill_build_points_warnings"


# ---------------------------------------------------------------------------
# Pure scoring (no database)
# ---------------------------------------------------------------------------


def empty():
	return {key: 0 for key in COUNT_KEYS}


def conductor_count(channels=None, spectrum=None, is_pixel=False, pixel_conductors=DEFAULT_PIXEL_CONDUCTORS):
	"""Conductors on one run's leader: ``(count, warning or None)``, clamped to 2-6."""
	if is_pixel:
		return int(pixel_conductors), None
	try:
		channels = int(channels or 0)
	except (TypeError, ValueError):
		channels = 0
	if channels > 0:
		count = channels + 1
	elif spectrum in SPECTRUM_CONDUCTORS:
		count = SPECTRUM_CONDUCTORS[spectrum]
	else:
		return 2, "Conductor count unknown (no LED package channels); scored as 2C"
	if count > 6:
		return 6, f"{count} conductors scored as 6C"
	return max(count, 2), None


def tally(runs, *, fmc=0, assembly=0, loose=0):
	"""Counts for one unit. ``runs`` is a list of ``(conductors, wet)`` pairs."""
	counts = empty()
	for conductors, wet in runs:
		conductors = min(max(int(conductors), 2), 6)
		counts[f"runs_{conductors}c"] += 1
		if wet:
			counts["wet"] += 1
	counts["fmc"] += int(fmc)
	counts["assembly"] += int(assembly)
	counts["loose"] += int(loose)
	return counts


def add(total, counts, qty=1):
	for key in COUNT_KEYS:
		total[key] = total.get(key, 0) + (counts.get(key) or 0) * qty
	return total


def score(counts, weights=None):
	"""The CapFinal formula."""
	weights = weights or DEFAULT_WEIGHTS
	return round(sum((counts.get(key) or 0) * weights[key] for key in COUNT_KEYS), 4)


def tape_runs(segments, conductors, wet_for):
	"""Runs and jumpers of a tape/neon segment chain.

	Every segment needs a start feed unless the previous segment jumpers into it;
	split runs add (runs_count - 1) additional feeds. ``wet_for(segment)`` says
	whether that segment's feed is wet-rated.
	"""
	runs, fmc = [], 0
	previous = None
	for segment in segments:
		wet = bool(wet_for(segment))
		if not (previous and previous.get("end_type") == "Jumper"):
			runs.append((conductors, wet))
		extra = int(segment.get("runs_count") or 1) - 1
		runs.extend((conductors, wet) for _ in range(max(extra, 0)))
		if segment.get("end_type") == "Jumper":
			fmc += 1
		previous = segment
	return runs, fmc


def linear_runs(cables, conductors, wet):
	"""Runs and jumpers of a linear fixture from its cable manifest."""
	feeds = sum(1 for cut in cables if cut.get("role") in ("leader", "additional feed"))
	fmc = sum(1 for cut in cables if cut.get("role") == "jumper")
	return [(conductors, wet)] * feeds, fmc


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def settings():
	try:
		values = frappe.db.get_singles_dict(SETTINGS) or {}
	except Exception:
		values = {}
	return values


def _number(values, field, default):
	value = values.get(field)
	if value in (None, ""):
		return default
	try:
		return float(value)
	except (TypeError, ValueError):
		return default


def weights(values=None):
	values = settings() if values is None else values
	return {key: _number(values, WEIGHT_FIELDS[key], DEFAULT_WEIGHTS[key]) for key in COUNT_KEYS}


def release_weights(values=None):
	"""Weights for release (hold-for-release) estimates: ``release_weight_*`` settings."""
	values = settings() if values is None else values
	return {
		key: _number(values, "release_" + WEIGHT_FIELDS[key], RELEASE_DEFAULTS[key]) for key in COUNT_KEYS
	}


def points_per_hour(values=None):
	"""Points one person builds in a paid hour (the workbook's ``CapacityHr``)."""
	values = settings() if values is None else values
	per_day = _number(values, "points_per_person_day", DEFAULT_POINTS_PER_PERSON_DAY)
	hours = _number(values, "paid_hours_per_day", DEFAULT_PAID_HOURS) or DEFAULT_PAID_HOURS
	return per_day / hours


# ---------------------------------------------------------------------------
# Reading configured builds
# ---------------------------------------------------------------------------


def _json(value, default):
	if not value:
		return default
	if isinstance(value, (dict, list)):
		return value
	try:
		return json.loads(value)
	except (TypeError, ValueError):
		return default


def led_conductors(tape_offering=None, tape_spec=None, led_package=None):
	"""``(conductors, warning)`` for a light engine."""
	if tape_offering and not (led_package and tape_spec):
		row = frappe.db.get_value(
			"ilL-Rel-Tape Offering", tape_offering, ["led_package", "tape_spec"], as_dict=True
		)
		if row:
			led_package = led_package or row.led_package
			tape_spec = tape_spec or row.tape_spec
	if not led_package and tape_spec:
		led_package = frappe.db.get_value("ilL-Spec-LED Tape", tape_spec, "led_package")
	channels = spectrum = None
	pixel = False
	if led_package:
		row = frappe.db.get_value(
			"ilL-Attribute-LED Package", led_package, ["channels", "spectrum_type", "is_pixel"], as_dict=True
		)
		if row:
			channels, spectrum, pixel = row.channels, row.spectrum_type, bool(row.is_pixel)
	if not channels and tape_spec:
		channels = frappe.db.get_value("ilL-Spec-LED Tape", tape_spec, "channels")
	pixel_conductors = int(_number(settings(), "pixel_conductors", DEFAULT_PIXEL_CONDUCTORS))
	return conductor_count(channels, spectrum, pixel, pixel_conductors)


def is_wet(environment_rating=None, ip_rating=None):
	from illumenate_lighting.illumenate_lighting.api.environment_codes import (
		ENVIRONMENT_RATING,
		IP_RATING,
		ip_number,
	)

	for doctype, name in ((ENVIRONMENT_RATING, environment_rating), (IP_RATING, ip_rating)):
		number = ip_number(doctype, name) if name else None
		if number is not None and number >= WET_IP:
			return True
	return False


def _result(counts, warnings):
	return {"counts": counts, "warnings": [w for w in dict.fromkeys(warnings) if w]}


def fixture_profile(doc):
	"""ilL-Configured-Fixture (linear)."""
	conductors, warning = led_conductors(tape_offering=doc.get("tape_offering"))
	wet = is_wet(environment_rating=doc.get("environment_rating"))
	cables = _json(doc.get("cable_manifest_json"), [])
	if cables:
		runs, fmc = linear_runs(cables, conductors, wet)
	else:
		# Legacy builds without a cable manifest.
		runs = [(conductors, wet)] * max(len(doc.get("runs") or []), int(doc.get("runs_count") or 0), 1)
		fmc = (
			sum(1 for s in doc.get("segments") or [] if s.get("end_jumper_item") or s.get("end_jumper_len_mm"))
			if doc.get("is_multi_segment")
			else 0
		)
	assembly = 0 if doc.get("assembly_mode") == "SHIP_PIECES" else 1
	return _result(tally(runs, fmc=fmc, assembly=assembly), [warning])


def _tape_segments(doc):
	build = _json(doc.get("build_snapshot_json"), {})
	segments = (build.get("computed") or {}).get("segments")
	if segments:
		return segments
	return [
		{"end_type": s.get("end_type"), "ip_rating": s.get("ip_rating"), "runs_count": 1}
		for s in sorted(doc.get("segments") or [], key=lambda s: s.get("segment_index") or 0)
	]


def tape_neon_profile(doc):
	"""ilL-Configured-Tape-Neon (LED tape, COB tape, LED neon)."""
	if doc.get("assembly_mode") == "BULK_REEL":
		return _result(tally([], loose=1), [])
	conductors, warning = led_conductors(tape_offering=doc.get("tape_offering"), tape_spec=doc.get("tape_spec"))
	environment = doc.get("environment_rating")
	runs, fmc = tape_runs(
		_tape_segments(doc),
		conductors,
		lambda segment: is_wet(environment_rating=environment, ip_rating=segment.get("ip_rating")),
	)
	return _result(tally(runs, fmc=fmc), [warning])


def _sheet_conductors(sheet_spec):
	package = frappe.db.get_value("ilL-Spec-LED-Sheet", sheet_spec, "led_package") if sheet_spec else None
	return led_conductors(led_package=package) if package else (2, None)


def led_sheet_profile(doc):
	"""ilL-Configured-LED-Sheet: one run per feed group, one FMC per sheet jumper."""
	conductors, warning = _sheet_conductors(doc.get("sheet_spec"))
	wet = is_wet(environment_rating=doc.get("selected_environment_rating"))
	groups = len(doc.get("groups") or []) or int(doc.get("total_groups") or 0) or 1
	fmc = int(doc.get("jumper_cables_needed") or 0)
	if not fmc:
		build = _json(doc.get("build_snapshot_json"), {})
		fmc = int(sum(r.get("qty") or 0 for r in build.get("components") or [] if r.get("role") == "jumpers"))
	return _result(tally([(conductors, wet)] * groups, fmc=fmc), [warning])


def group_profile(doc):
	"""ilL-Configured-Group: the sum of its member runs."""
	build = _json(doc.get("build_snapshot_json"), {})
	request = build.get("request") or {}
	family = request.get("family") or doc.get("family")
	shared = request.get("shared") or {}
	counts, warnings = empty(), []
	for member in build.get("members") or []:
		member_build = member.get("build") or {}
		inputs = member.get("pricing_inputs") or {}
		computed = member_build.get("computed") or {}
		if family == "Linear Fixture":
			conductors, warning = led_conductors(tape_offering=inputs.get("tape_offering"))
			wet = is_wet(environment_rating=inputs.get("environment_rating") or shared.get("environment_rating"))
			runs, fmc = linear_runs(member_build.get("cables") or [], conductors, wet)
			assembly = 0 if computed.get("assembly_mode") == "SHIP_PIECES" else 1
			add(counts, tally(runs or [(conductors, wet)], fmc=fmc, assembly=assembly))
		elif family == "LED Sheet":
			conductors, warning = _sheet_conductors(member_build.get("spec") or member_build.get("sheet_spec"))
			wet = is_wet(environment_rating=shared.get("environment_rating"))
			fmc = sum(r.get("qty") or 0 for r in member_build.get("components") or [] if r.get("role") == "jumpers")
			add(counts, tally([(conductors, wet)] * max(len(member_build.get("groups") or []), 1), fmc=fmc))
		else:
			if computed.get("ordering_mode") == "BULK_REEL":
				add(counts, tally([], loose=1))
				continue
			resolved = member_build.get("resolved_items") or {}
			conductors, warning = led_conductors(
				tape_offering=resolved.get("tape_offering"), tape_spec=resolved.get("tape_spec")
			)
			environment = (member_build.get("selections") or {}).get("environment_rating") or shared.get(
				"environment_rating"
			)
			runs, fmc = tape_runs(
				computed.get("segments") or [],
				conductors,
				lambda segment, env=environment: is_wet(environment_rating=env, ip_rating=segment.get("ip_rating")),
			)
			add(counts, tally(runs, fmc=fmc))
		warnings.append(warning)
	if not build.get("members"):
		warnings.append("Group has no member snapshot; scored as 0")
	return _result(counts, warnings)


PROFILERS = {
	"ilL-Configured-Fixture": fixture_profile,
	"ilL-Configured-Tape-Neon": tape_neon_profile,
	"ilL-Configured-LED-Sheet": led_sheet_profile,
	"ilL-Configured-Group": group_profile,
}


def profile(doctype, name):
	"""Per-unit counts and warnings for one configured build."""
	return PROFILERS[doctype](frappe.get_doc(doctype, name))


def configured_for_item(item_code):
	"""``(doctype, name)`` of the configured build behind an Item, or ``None``."""
	if not item_code:
		return None
	item_fields = [f for f in CONFIGURED.values() if f]
	meta = frappe.get_meta("Item")
	present = [f for f in item_fields if meta.has_field(f)]
	if present:
		row = frappe.db.get_value("Item", item_code, present, as_dict=True) or {}
		for doctype, field in CONFIGURED.items():
			if field and row.get(field):
				return doctype, row[field]
	for doctype in CONFIGURED:
		name = frappe.db.get_value(doctype, {"configured_item": item_code}, "name")
		if name:
			return doctype, name
	return None


# ---------------------------------------------------------------------------
# BOM stamping
# ---------------------------------------------------------------------------


def _bom_has_fields():
	return frappe.get_meta("BOM").has_field(STAMPED_FIELD)


def stamp_bom(bom_name, *, item_code=None, values=None):
	"""Count the build behind a BOM and store per-unit counts and points on it."""
	item_code = item_code or frappe.db.get_value("BOM", bom_name, "item")
	configured = configured_for_item(item_code)
	if configured:
		result = profile(*configured)
	else:
		result = _result(empty(), [])  # Stock items and purchased parts carry no build points.
	counts = result["counts"]
	update = {FIELD[key]: counts[key] for key in COUNT_KEYS}
	update[POINTS_FIELD] = score(counts, weights(values))
	update[STAMPED_FIELD] = 1
	update[WARNINGS_FIELD] = "\n".join(result["warnings"])
	frappe.db.set_value("BOM", bom_name, update, update_modified=False)
	return {**counts, "points": update[POINTS_FIELD], "warnings": result["warnings"]}


def bom_counts(bom_name):
	"""Per-unit counts of a BOM, stamping it first when it has never been counted."""
	if not bom_name or not _bom_has_fields():
		return None
	fields = [FIELD[key] for key in COUNT_KEYS] + [STAMPED_FIELD, WARNINGS_FIELD]
	row = frappe.db.get_value("BOM", bom_name, fields, as_dict=True)
	if not row:
		return None
	if not row.get(STAMPED_FIELD):
		stamped = stamp_bom(bom_name)
		return {key: stamped[key] for key in COUNT_KEYS} | {"warnings": stamped["warnings"]}
	counts = {key: row.get(FIELD[key]) or 0 for key in COUNT_KEYS}
	counts["warnings"] = [w for w in (row.get(WARNINGS_FIELD) or "").split("\n") if w]
	return counts


def on_bom_submit(doc, method=None):
	"""Doc event: stamp a newly submitted BOM. Never blocks the BOM."""
	if not _bom_has_fields():
		return
	try:
		stamp_bom(doc.name, item_code=doc.item)
	except Exception:
		frappe.log_error(title=f"Build points: could not stamp BOM {doc.name}")


# ---------------------------------------------------------------------------
# Sales Orders and Work Orders
# ---------------------------------------------------------------------------


def line_bom(row):
	return (
		row.get("ill_bom")
		or row.get("bom_no")
		or frappe.db.get_value("BOM", {"item": row.get("item_code"), "is_default": 1, "docstatus": 1}, "name")
	)


def order_totals(doc, values=None):
	"""Per-line and order counts for a Sales Order (no writes)."""
	values = settings() if values is None else values
	weight = weights(values)
	lines, total, warnings = {}, empty(), []
	for row in doc.get("items") or []:
		counts = bom_counts(line_bom(row)) if row.get("item_code") else None
		qty = float(row.get("stock_qty") or row.get("qty") or 0)
		line = add(empty(), counts or {}, qty)
		line["points"] = score(line, weight)
		lines[row.get("name") or row.get("idx")] = line
		add(total, line)
		warnings.extend(f"Row {row.get('idx')}: {w}" for w in (counts or {}).get("warnings") or [])
	total["points"] = score(total, weight)
	per_hour = points_per_hour(values)
	total["hours"] = round(total["points"] / per_hour, 2) if per_hour else 0
	net = float(doc.get("net_total") or 0) - float(doc.get("total_commission") or 0)
	total["worth_per_point"] = round(net / total["points"], 2) if total["points"] else 0
	total["warnings"] = warnings
	return lines, total


def _order_fields_exist():
	return frappe.get_meta("Sales Order").has_field(POINTS_FIELD)


def _order_values(total):
	values = {FIELD[key]: total[key] for key in COUNT_KEYS}
	values.update(
		{
			POINTS_FIELD: total["points"],
			"ill_build_hours": total["hours"],
			"ill_worth_per_point": total["worth_per_point"],
			WARNINGS_FIELD: "\n".join(total["warnings"]),
		}
	)
	return values


def roll_up_sales_order(doc, method=None):
	"""Doc event (Sales Order validate): line and order build points."""
	if not _order_fields_exist():
		return
	try:
		lines, total = order_totals(doc)
	except Exception:
		frappe.log_error(title=f"Build points: could not total {doc.name}")
		return
	for row in doc.get("items") or []:
		line = lines.get(row.get("name") or row.get("idx")) or {}
		for key in COUNT_KEYS:
			row.set(FIELD[key], line.get(key) or 0)
		row.set(POINTS_FIELD, line.get("points") or 0)
	doc.update(_order_values(total))


def refresh_sales_order(name):
	"""Recount a saved (possibly submitted) Sales Order without saving it."""
	doc = frappe.get_doc("Sales Order", name)
	lines, total = order_totals(doc)
	for row in doc.items:
		line = lines.get(row.name) or {}
		values = {FIELD[key]: line.get(key) or 0 for key in COUNT_KEYS}
		values[POINTS_FIELD] = line.get("points") or 0
		frappe.db.set_value("Sales Order Item", row.name, values, update_modified=False)
	frappe.db.set_value("Sales Order", name, _order_values(total), update_modified=False)
	return total


def work_order_points(doc):
	counts = bom_counts(doc.get("bom_no"))
	if not counts:
		return 0
	return score(add(empty(), counts, float(doc.get("qty") or 0)), weights())


def on_work_order_insert(doc, method=None):
	"""Doc event (Work Order before_insert): points for the quantity being built."""
	if not frappe.get_meta("Work Order").has_field(POINTS_FIELD):
		return
	try:
		doc.set(POINTS_FIELD, work_order_points(doc))
	except Exception:
		frappe.log_error(title="Build points: could not score Work Order")


# ---------------------------------------------------------------------------
# Backfill and re-scoring
# ---------------------------------------------------------------------------

OPEN_ORDER = {"docstatus": ["<", 2], "status": ["not in", ["Closed", "Completed", "Cancelled"]]}
OPEN_WORK = {"docstatus": ["<", 2], "status": ["not in", ["Completed", "Cancelled", "Closed"]]}


def _each(names, action, errors):
	done = 0
	for name in names:
		try:
			action(name)
			done += 1
		except Exception as error:
			errors.append(f"{name}: {error}")
	return done


def refresh_open_documents(errors):
	orders = frappe.get_all("Sales Order", filters=OPEN_ORDER, pluck="name")
	work = frappe.get_all("Work Order", filters=OPEN_WORK, fields=["name", "bom_no", "qty"])
	updated_orders = _each(orders, refresh_sales_order, errors)
	updated_work = _each(
		work,
		lambda row: frappe.db.set_value(
			"Work Order", row.name, POINTS_FIELD, work_order_points(row), update_modified=False
		),
		errors,
	)
	return updated_orders, updated_work


@frappe.whitelist()
def backfill(force=0, dry_run=0):
	"""Count every active BOM, then re-total open Sales Orders and Work Orders.

	``force`` recounts BOMs that were already stamped. ``dry_run`` only reports how
	many would be touched. Run from the desk or ``bench execute``.
	"""
	frappe.only_for(("System Manager", "Manufacturing Manager"))
	if not _bom_has_fields():
		frappe.throw("Build point fields are missing; run bench migrate first.")
	filters = {"docstatus": 1, "is_active": 1}
	if not int(force or 0):
		filters[STAMPED_FIELD] = ["in", [0, None]]
	boms = frappe.get_all("BOM", filters=filters, fields=["name", "item"])
	if int(dry_run or 0):
		return {"boms": len(boms), "orders": frappe.db.count("Sales Order", OPEN_ORDER)}
	errors = []
	values = settings()
	stamped = _each(boms, lambda row: stamp_bom(row.name, item_code=row.item, values=values), errors)
	orders, work = refresh_open_documents(errors)
	frappe.db.commit()
	return {"boms": stamped, "orders": orders, "work_orders": work, "errors": errors[:50]}


def rescore(values=None):
	"""Apply new weights to stored counts (BOMs, open orders and Work Orders)."""
	weight = weights(values)
	fields = ["name"] + [FIELD[key] for key in COUNT_KEYS]
	for row in frappe.get_all("BOM", filters={STAMPED_FIELD: 1}, fields=fields):
		counts = {key: row.get(FIELD[key]) or 0 for key in COUNT_KEYS}
		frappe.db.set_value("BOM", row.name, POINTS_FIELD, score(counts, weight), update_modified=False)
	errors = []
	refresh_open_documents(errors)
	if errors:
		frappe.log_error(title="Build points: re-score errors", message="\n".join(errors[:200]))
	frappe.db.commit()
