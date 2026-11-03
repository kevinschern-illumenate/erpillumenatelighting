"""Compare two saved schedule lines side by side (plan 6.7).

A pure read of what is already saved: part number, dimensions, run plan, driver
plan, watts, availability and (for pricing-entitled users) the MSRP the schedule
page shows. Each line is read through its own schedule's read check, so a user
can only compare lines they can already open. Nothing is recalculated or saved.
"""

import json

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.site_flags import configuration_compare_enabled

MM_PER_INCH = 25.4
EMPTY = "—"
FIELDS = (
	("part_number", "Part number"),
	("product", "Product"),
	("template", "Template"),
	("dimensions", "Dimensions"),
	("quantity", "Quantity"),
	("run_plan", "Run plan"),
	("driver_plan", "Driver plan"),
	("total_watts", "Total watts"),
	("availability", "Availability"),
	("unit_price", "Unit price (MSRP)"),
)
AVAILABILITY = {
	"available": "In stock",
	"partial": "Some components short",
	"unknown": "Availability unknown",
}


@frappe.whitelist()
def compare_lines(schedule, line_a, line_b, schedule_b=None):
	"""Side-by-side display rows for two schedule lines the user can read."""
	if not configuration_compare_enabled():
		return {"success": True, "enabled": False}
	if not line_a or not line_b:
		frappe.throw(_("Choose two lines to compare"))
	from illumenate_lighting.illumenate_lighting.api.exports import _check_pricing_permission
	from illumenate_lighting.illumenate_lighting.portal.configuration import resolve_line, schedule_context

	sides = []
	for schedule_name, line_key in ((schedule, line_a), (schedule_b or schedule, line_b)):
		doc = schedule_context(schedule_name)
		try:
			line = resolve_line(doc, line_key=line_key)
		except ValueError as error:
			frappe.throw(_(str(error)))
		sides.append((doc, line))
	priced = bool(_check_pricing_permission(frappe.session.user))
	snapshots = [snapshot(line, priced) for _doc, line in sides]
	return {
		"success": True,
		"enabled": True,
		"priced": priced,
		"lines": [header(doc, line) for doc, line in sides],
		"rows": rows(*snapshots, priced=priced),
	}


def header(schedule, line):
	return {
		"schedule": schedule.name,
		"schedule_name": schedule.get("schedule_name") or schedule.name,
		"line_key": line.get("line_key") or line.name,
		"designation": line.get("line_id") or str(line.get("idx") or ""),
		"location": line.get("location") or "",
	}


def rows(a, b, priced=False):
	"""Display rows: every value is plain text (or a list of text lines) for textContent."""
	result = []
	for key, label in FIELDS:
		if key == "unit_price" and not priced:
			continue
		left, right = text(a.get(key)), text(b.get(key))
		result.append({"key": key, "label": _(label), "a": left, "b": right, "same": left == right})
	return result


def text(value):
	if isinstance(value, (list, tuple)):
		return [str(item) for item in value if item not in (None, "")] or [EMPTY]
	if value is None or value == "":
		return EMPTY
	if isinstance(value, float):
		return f"{value:g}"
	return str(value)


def length(mm):
	mm = float(mm or 0)
	if mm <= 0:
		return None
	return f'{mm / MM_PER_INCH:.1f}" ({mm:.0f} mm)'


def watts(value):
	value = float(value or 0)
	return f"{value:.1f} W" if value else None


def money(value):
	return f"${float(value):,.2f}" if value else None


def snapshot(line, priced=False):
	"""What one saved line is, as display values. Missing records read as empty, never as an error."""
	side = {"product": line.get("product_type") or line.get("manufacturer_type"), "quantity": line.get("qty")}
	if line.get("manufacturer_type") == "ILLUMENATE":
		if line.get("configured_group"):
			_group(side, line)
		elif line.get("configured_fixture"):
			_fixture(side, line.get("configured_fixture"))
		elif line.get("configured_tape_neon"):
			_tape_neon(side, line.get("configured_tape_neon"))
		elif line.get("configured_led_sheet"):
			_led_sheet(side, line.get("configured_led_sheet"))
	elif line.get("manufacturer_type") == "ACCESSORY":
		side.update(part_number=line.get("accessory_item"), template=line.get("accessory_item_name"))
	else:
		side.update(
			part_number=line.get("fixture_model_number"),
			template=line.get("manufacturer_name"),
		)
	side["availability"] = availability(line)
	if priced:
		side["unit_price"] = price(line)
	return side


def _record(doctype, name):
	return frappe.get_doc(doctype, name) if name and frappe.db.exists(doctype, name) else None


def _fixture(side, name):
	doc = _record("ilL-Configured-Fixture", name)
	if not doc:
		return
	side.update(
		part_number=doc.get("display_part_number") or doc.get("configured_item") or doc.get("config_hash"),
		template=doc.get("fixture_template"),
		dimensions=length(doc.get("manufacturable_overall_length_mm")),
		total_watts=watts(doc.get("total_watts")),
		run_plan=[
			" · ".join(
				part
				for part in (
					f"Run {run.get('run_index') or index}",
					length(run.get("run_len_mm")),
					watts(run.get("run_watts")),
					f"leader {length(run.get('leader_len_mm'))}" if run.get("leader_len_mm") else None,
				)
				if part
			)
			for index, run in enumerate(doc.get("runs") or [], 1)
		],
		driver_plan=_drivers(
			[(row.get("driver_item"), row.get("driver_qty")) for row in doc.get("drivers") or []],
			doc.get("include_power_supply", 1),
		),
	)


def _tape_neon(side, name):
	doc = _record("ilL-Configured-Tape-Neon", name)
	if not doc:
		return
	plan = _json(doc.get("power_plan_json"))
	side.update(
		part_number=doc.get("part_number") or doc.get("config_hash"),
		template=doc.get("tape_neon_template"),
		dimensions=length(doc.get("manufacturable_length_mm")),
		total_watts=watts(doc.get("total_watts")),
		run_plan=[
			" · ".join(
				part
				for part in (
					f"Segment {segment.get('segment_index') or index}",
					length(segment.get("manufacturable_length_mm")),
					watts(segment.get("watts")),
					segment.get("end_type"),
				)
				if part
			)
			for index, segment in enumerate(doc.get("segments") or [], 1)
		],
		driver_plan=_drivers(
			[(row.get("driver_item") or row.get("item_code"), row.get("qty")) for row in plan.get("drivers") or []],
			doc.get("include_power_supply", 1),
		),
	)


def _led_sheet(side, name):
	doc = _record("ilL-Configured-LED-Sheet", name)
	if not doc:
		return
	groups = doc.get("groups") or []
	drivers = {}
	for group in groups:
		driver = group.get("compatible_driver")
		if driver:
			drivers[driver] = drivers.get(driver, 0) + 1
	width, height = doc.get("coverage_width_ft"), doc.get("coverage_height_ft")
	side.update(
		part_number=doc.get("part_number") or doc.get("config_hash"),
		template=doc.get("sheet_template"),
		dimensions=f"{float(width):g} × {float(height):g} ft, {doc.get('sheets_needed') or 0} panels"
		if width and height
		else None,
		total_watts=watts(doc.get("total_system_watts")),
		run_plan=[
			f"Group {group.get('group_number') or index} · {group.get('sheet_count') or 0} panels · "
			+ (watts(group.get("group_watts")) or "0 W")
			for index, group in enumerate(groups, 1)
		],
		driver_plan=_drivers(sorted(drivers.items()), doc.get("include_power_supply")),
	)


def _group(side, line):
	from illumenate_lighting.illumenate_lighting.portal.group_display import details, run_labels

	group = details(line.get("configured_group"), run_labels(line))
	plan = group.get("power_plan") or {}
	side.update(
		part_number=line.get("group_part_number"),
		template=group.get("template"),
		dimensions=group.get("total_length"),
		total_watts=watts(group.get("total_watts")),
		run_plan=[
			" · ".join(part for part in (m.get("label"), m.get("length") or m.get("area"), watts(m.get("watts"))) if part)
			for m in group.get("members") or []
		],
		driver_plan=_drivers(
			[(row.get("driver_item"), row.get("qty")) for row in plan.get("drivers") or []],
			group.get("include_power_supply"),
		),
	)


def _drivers(pairs, included):
	if not included:
		return ["Power supply not included"]
	return [f"{int(float(qty or 0)) or 1} × {item}" for item, qty in pairs if item]


def _json(value):
	if isinstance(value, dict):
		return value
	try:
		parsed = json.loads(value) if value else {}
	except (TypeError, ValueError):
		return {}
	return parsed if isinstance(parsed, dict) else {}


def availability(line):
	"""This line's stock on its own (the schedule page shares stock across all lines)."""
	from illumenate_lighting.illumenate_lighting.api.pricing_utils import (
		batch_stock_for_schedule_lines,
		fixture_components,
	)

	if line.get("manufacturer_type") == "ILLUMENATE" and any(
		line.get(key) for key in ("configured_group", "configured_tape_neon", "configured_led_sheet")
	):
		from illumenate_lighting.illumenate_lighting.portal.group_display import stock_components

		components = stock_components(line)
	elif line.get("manufacturer_type") == "ILLUMENATE" and line.get("configured_fixture"):
		doc = _record("ilL-Configured-Fixture", line.get("configured_fixture"))
		components = fixture_components(doc) if doc else []
	elif line.get("manufacturer_type") == "ACCESSORY" and line.get("accessory_item"):
		components = [("Accessory", line.get("accessory_item"), 1.0, "Nos")]
	else:
		return None
	if not components:
		return _(AVAILABILITY["unknown"])
	stock = batch_stock_for_schedule_lines([{"key": "line", "qty": line.get("qty") or 1, "components": components}])
	state = (stock["lines"].get("line") or {}).get("availability") or "unknown"
	return _(AVAILABILITY.get(state, AVAILABILITY["unknown"]))


def price(line):
	"""The schedule page's MSRP for one unit of this line, with the driver sub-line when it has one."""
	from illumenate_lighting.templates.pages.schedule import compute_line_msrp

	snapshot_price = {}
	for field, doctype in (
		("configured_fixture", "ilL-Configured-Fixture"),
		("configured_tape_neon", "ilL-Configured-Tape-Neon"),
	):
		if line.get(field):
			latest = frappe.get_all(
				"ilL-Child-Pricing-Snapshot",
				filters={"parent": line.get(field), "parenttype": doctype, "msrp_unit": [">", 0]},
				fields=["msrp_unit"],
				order_by="timestamp desc",
				limit=1,
			)
			snapshot_price[field] = float(latest[0].msrp_unit) if latest and latest[0].msrp_unit else None
	msrp = compute_line_msrp(
		line,
		fixture_snapshot_price=snapshot_price.get("configured_fixture"),
		ctn_snapshot_price=snapshot_price.get("configured_tape_neon"),
	)
	unit = money(msrp.get("unit"))
	driver = money(msrp.get("driver_unit"))
	if unit and driver:
		return f"{unit} + {driver} driver"
	return unit or driver
