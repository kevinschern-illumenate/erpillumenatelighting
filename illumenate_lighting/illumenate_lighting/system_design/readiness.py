# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Design readiness: which catalog records the System Designer cannot use yet, and why (H7.2, WP-1.7).

A record is ``incomplete`` when a required field in Appendix A is missing or cannot be mapped (a tape
voltage that is not 12/24/48, a protocol with no ``engine_protocol``). ``missing`` lists **ERP
fieldnames** so staff can go straight to them. The rule functions are pure; the catalog generator
(WP-2.1) uses the same functions, so the report and the designer never disagree.
"""

import frappe
from frappe import _

TAPE_VOLTAGES = (12, 24, 48)
STATUS_READY = "ready"
STATUS_INCOMPLETE = "incomplete"
STATUS_NOT_MODELLED = "not modelled"
VOLUME_DAYS = 180

TAPE = "ilL-Spec-LED Tape"
DRIVER = "ilL-Spec-Driver"
CONTROLLER = "ilL-Spec-Controller"
WIRE = "ilL-Spec-Wire"
PRODUCT_TYPES = {"Tape": TAPE, "Driver": DRIVER, "Controller": CONTROLLER, "Wire": WIRE}

# Appendix A.5. Wall Dimmer splits on output_dimming; Sensor is not modelled yet.
CONTROLLER_CATEGORIES = {
	"DMX Controller": "dmx-controller",
	"Wireless Receiver": "wireless-rx",
	"Scene Controller": "keypad",
	"Gateway": "sacn-gateway",
	"Repeater": "opto-splitter",
	"DMX Decoder": "dmx-decoder",
	"DMX to 0-10V Converter": "dmx-0-10v-converter",
	"Pixel Controller": "pixel-controller",
	"Wireless Transmitter": "wireless-tx",
	"Relay": "relay",
	"Lutron Module": "lutron-module",
}
WALL_DIMMER_CATEGORIES = {
	"Phase Forward": "phase-dimmer",
	"Phase Reverse": "phase-dimmer",
	"0-10V": "0-10v-dimmer",
}
NOT_MODELLED = {"Sensor"}
DMX_RECEIVERS = {"dmx-decoder", "dmx-0-10v-converter"}


def _has(value):
	return value not in (None, "", 0, 0.0)


def _positive(value):
	try:
		return float(value) > 0
	except (TypeError, ValueError):
		return False


def _fraction(value):
	try:
		return 0 < float(value) <= 1
	except (TypeError, ValueError):
		return False


def result(missing, notes=None, status=None):
	missing = list(dict.fromkeys(missing))
	return {
		"status": status or (STATUS_INCOMPLETE if missing else STATUS_READY),
		"missing": missing,
		"notes": list(notes or []),
	}


def _protocol_issues(field, names, engine_protocols, missing, notes, required=True):
	"""Every linked protocol needs an ``engine_protocol`` (Appendix B.1)."""
	names = [n for n in names if n]
	if not names:
		if required:
			missing.append(field)
		return
	for name in names:
		if not engine_protocols.get(name):
			missing.append(field)
			notes.append(_("unmapped protocol: {0}").format(name))


def tape_issues(spec, voltages):
	"""A.1. ``voltages`` maps Output Voltage names to ``nominal_voltage_v``."""
	missing, notes = [], []
	if not spec.get("item"):
		missing.append("item")
	volts = voltages.get(spec.get("input_voltage"))
	if not volts:
		missing.append("input_voltage")
		if spec.get("input_voltage"):
			notes.append(_("{0} has no nominal voltage").format(spec["input_voltage"]))
	elif float(volts) not in TAPE_VOLTAGES:
		missing.append("input_voltage")
		notes.append(_("{0} V tape is not 12, 24 or 48 V").format(volts))
	for field in ("drive_type", "power_basis"):
		if not spec.get(field):
			missing.append(field)
	for field in (
		"watts_per_foot",
		"max_simultaneous_pct",
		"max_run_double_feed_ft",
		"min_operating_voltage_v",
	):
		if not _positive(spec.get(field)):
			missing.append(field)
	if not (
		_positive(spec.get("max_run_single_feed_ft")) or _positive(spec.get("voltage_drop_max_run_length_ft"))
	):
		missing.append("max_run_single_feed_ft")
	channels = int(spec.get("channels") or 0)
	if channels < 1:
		missing.append("channels")
	elif channels > 1 and not spec.get("channel_limit_count"):
		notes.append(_("No channel limits; channels are named CH1 to CH{0}").format(channels))
	if not spec.get("is_free_cutting") and not _positive(spec.get("cut_increment_mm")):
		missing.append("cut_increment_mm")
	if spec.get("pixel_protocol") not in (None, "", "None"):
		for field in ("pixels_per_m", "amps_per_pixel_max"):
			if not _positive(spec.get(field)):
				missing.append(field)
	return result(missing, notes)


def driver_issues(spec, voltages, engine_protocols, input_protocols):
	"""A.2. ``input_protocols`` lists the driver's linked dimming protocol names."""
	missing, notes = [], []
	for field in (
		"item",
		"input_voltage_type",
		"input_phase",
		"output_type",
		"terminal_min_awg",
		"terminal_max_awg",
	):
		if not spec.get(field):
			missing.append(field)
	for field in ("input_voltage_min", "input_voltage_max", "max_wattage", "max_wattage_per_output"):
		if not _positive(spec.get(field)):
			missing.append(field)
	if int(spec.get("independent_outputs_count") or 0) < 1:
		missing.append("independent_outputs_count")
	for field in ("efficiency", "power_factor", "usable_load_factor"):
		if not _fraction(spec.get(field)):
			missing.append(field)
			if _has(spec.get(field)):
				notes.append(_("{0} must be between 0 and 1").format(field))
	if spec.get("output_type") == "Constant Voltage" and not voltages.get(spec.get("voltage_output")):
		missing.append("voltage_output")
	if spec.get("output_type") == "Constant Current":
		for field in ("output_current_ma", "compliance_v_min", "compliance_v_max"):
			if not _positive(spec.get(field)):
				missing.append(field)
	_protocol_issues("input_protocols", input_protocols, engine_protocols, missing, notes)
	return result(missing, notes)


def controller_category(controller_type, output_dimming=None):
	if controller_type == "Wall Dimmer":
		return WALL_DIMMER_CATEGORIES.get(output_dimming or "")
	return CONTROLLER_CATEGORIES.get(controller_type)


def controller_issues(spec, engine_protocols, input_protocols, output_protocols, port_count):
	"""A.3 / A.5."""
	kind = spec.get("controller_type")
	if kind in NOT_MODELLED:
		return result(
			[], [_("{0} devices are not modelled by the designer yet").format(kind)], STATUS_NOT_MODELLED
		)
	missing, notes = [], []
	if not spec.get("item"):
		missing.append("item")
	category = controller_category(kind, spec.get("output_dimming"))
	if not kind:
		missing.append("controller_type")
	elif not category:
		missing.append("output_dimming" if kind == "Wall Dimmer" else "controller_type")
		if kind == "Wall Dimmer":
			notes.append(_("Wall dimmers need an output dimming type to choose phase or 0-10V"))
	if category == "dmx-decoder":
		if int(spec.get("channels") or 0) < 1:
			missing.append("channels")
		for field in ("max_a_per_channel", "max_load_amps", "max_w_per_channel", "max_load_watts"):
			if not _positive(spec.get(field)):
				missing.append(field)
		if spec.get("input_voltage_type") == "VAC" and spec.get("output_dimming") in (None, "", "None"):
			missing.append("output_dimming")
	if category in DMX_RECEIVERS:
		if int(spec.get("dmx_footprint") or 0) < 1:
			missing.append("dmx_footprint")
		if not _positive(spec.get("unit_load")):
			missing.append("unit_load")
	if category == "phase-dimmer":
		for field in ("min_load_w", "led_max_w"):
			if not _positive(spec.get(field)):
				missing.append(field)
		if int(spec.get("max_supplies") or 0) < 1:
			missing.append("max_supplies")
	if not input_protocols and not output_protocols:
		missing.append("input_protocols")
	_protocol_issues("input_protocols", input_protocols, engine_protocols, missing, notes, required=False)
	_protocol_issues("output_protocols", output_protocols, engine_protocols, missing, notes, required=False)
	if port_count < 1:
		missing.append("ports")
	return result(missing, notes)


def wire_issues(spec, has_price):
	"""A.6 and D7: a wire the designer may quote needs a selling Item Price."""
	missing, notes = [], []
	if not has_price:
		missing.append("item_price")
		notes.append(_("Item {0} has no selling Item Price").format(spec.get("item")))
	if not spec.get("is_verified"):
		notes.append(_("Not verified by engineering yet"))
	return result(missing, notes)


# --- Report -----------------------------------------------------------------------------------


def _children(doctype, parenttype, parents, field, parentfield=None):
	if not parents:
		return {}
	filters = {"parenttype": parenttype, "parent": ["in", parents]}
	if parentfield:
		filters["parentfield"] = parentfield
	rows = frappe.get_all(doctype, filters=filters, fields=["parent", field])
	grouped = {}
	for row in rows:
		grouped.setdefault(row["parent"], []).append(row[field])
	return grouped


def _engine_protocols():
	return {
		row["name"]: row["engine_protocol"]
		for row in frappe.get_all("ilL-Attribute-Dimming Protocol", fields=["name", "engine_protocol"])
	}


def _voltages():
	return {
		row["name"]: row["nominal_voltage_v"]
		for row in frappe.get_all("ilL-Attribute-Output Voltage", fields=["name", "nominal_voltage_v"])
	}


def _rows(product_type, doctype, specs, issues):
	return [
		{
			"product_type": product_type,
			"doctype": doctype,
			"name": spec["name"],
			"item": spec.get("item"),
			"label": spec.get("label") or spec["name"],
			**issues(spec),
		}
		for spec in specs
	]


def tape_rows():
	specs = frappe.get_all(
		TAPE,
		fields=[
			"name",
			"item",
			"input_voltage",
			"drive_type",
			"power_basis",
			"watts_per_foot",
			"max_simultaneous_pct",
			"max_run_single_feed_ft",
			"voltage_drop_max_run_length_ft",
			"max_run_double_feed_ft",
			"min_operating_voltage_v",
			"channels",
			"is_free_cutting",
			"cut_increment_mm",
			"pixel_protocol",
			"pixels_per_m",
			"amps_per_pixel_max",
		],
	)
	limits = _children("ilL-Child-Tape-Channel", TAPE, [s["name"] for s in specs], "channel_name")
	voltages = _voltages()
	for spec in specs:
		spec["channel_limit_count"] = len(limits.get(spec["name"], []))
	return _rows("Tape", TAPE, specs, lambda spec: tape_issues(spec, voltages))


def driver_rows():
	specs = frappe.get_all(
		DRIVER,
		fields=[
			"name",
			"item",
			"input_voltage_type",
			"input_voltage_min",
			"input_voltage_max",
			"input_phase",
			"output_type",
			"voltage_output",
			"output_current_ma",
			"compliance_v_min",
			"compliance_v_max",
			"max_wattage",
			"max_wattage_per_output",
			"independent_outputs_count",
			"efficiency",
			"power_factor",
			"usable_load_factor",
			"terminal_min_awg",
			"terminal_max_awg",
		],
	)
	protocols = _children("ilL-Child-Driver-Input-Protocol", DRIVER, [s["name"] for s in specs], "protocol")
	voltages, engine = _voltages(), _engine_protocols()
	return _rows(
		"Driver",
		DRIVER,
		specs,
		lambda spec: driver_issues(spec, voltages, engine, protocols.get(spec["name"], [])),
	)


def controller_rows():
	specs = frappe.get_all(
		CONTROLLER,
		filters={"is_active": 1},
		fields=[
			"name",
			"item",
			"controller_name as label",
			"controller_type",
			"output_dimming",
			"input_voltage_type",
			"channels",
			"max_a_per_channel",
			"max_load_amps",
			"max_w_per_channel",
			"max_load_watts",
			"dmx_footprint",
			"unit_load",
			"min_load_w",
			"led_max_w",
			"max_supplies",
		],
	)
	names = [s["name"] for s in specs]
	child = "ilL-Child-Controller-Protocol"
	inputs = _children(child, CONTROLLER, names, "protocol", "input_protocols")
	outputs = _children(child, CONTROLLER, names, "protocol", "output_protocols")
	ports = _children("ilL-Child-Controller-Port", CONTROLLER, names, "port_name")
	engine = _engine_protocols()
	return _rows(
		"Controller",
		CONTROLLER,
		specs,
		lambda spec: controller_issues(
			spec,
			engine,
			inputs.get(spec["name"], []),
			outputs.get(spec["name"], []),
			len(ports.get(spec["name"], [])),
		),
	)


def wire_rows():
	specs = frappe.get_all(
		WIRE, filters={"is_active": 1}, fields=["name", "item", "wire_name as label", "is_verified"]
	)
	priced = set()
	items = [s["item"] for s in specs if s.get("item")]
	if items:
		priced = set(
			frappe.get_all(
				"Item Price", filters={"item_code": ["in", items], "selling": 1}, pluck="item_code"
			)
		)
	return _rows("Wire", WIRE, specs, lambda spec: wire_issues(spec, spec.get("item") in priced))


ROW_BUILDERS = {"Tape": tape_rows, "Driver": driver_rows, "Controller": controller_rows, "Wire": wire_rows}


def volumes(days=VOLUME_DAYS):
	"""Schedule lines in schedules changed in the last ``days`` that use each product.

	Returns ``{"tape": {spec: n}, "item": {item_code: n}}``. Tape counts come from configured tape/neon
	and configured fixtures; Item counts from accessory lines and fixtures' driver allocations.
	"""
	cutoff = frappe.utils.add_days(frappe.utils.nowdate(), -days)
	tape = frappe.db.sql(
		"""
		select coalesce(ctn.tape_spec, offering.tape_spec) as spec, count(*) as lines
		from `tabilL-Child-Fixture-Schedule-Line` line
		join `tabilL-Project-Fixture-Schedule` schedule on schedule.name = line.parent
		left join `tabilL-Configured-Tape-Neon` ctn on ctn.name = line.configured_tape_neon
		left join `tabilL-Configured-Fixture` cf on cf.name = line.configured_fixture
		left join `tabilL-Rel-Tape Offering` offering on offering.name = cf.tape_offering
		where line.parenttype = 'ilL-Project-Fixture-Schedule' and schedule.modified >= %(cutoff)s
			and coalesce(ctn.tape_spec, offering.tape_spec) is not null
		group by spec
		""",
		{"cutoff": cutoff},
		as_dict=True,
	)
	items = frappe.db.sql(
		"""
		select item, count(*) as lines from (
			select line.accessory_item as item
			from `tabilL-Child-Fixture-Schedule-Line` line
			join `tabilL-Project-Fixture-Schedule` schedule on schedule.name = line.parent
			where line.parenttype = 'ilL-Project-Fixture-Schedule' and schedule.modified >= %(cutoff)s
				and coalesce(line.accessory_item, '') != ''
			union all
			select distinct_driver.driver_item as item
			from (
				select distinct line.name as line, alloc.driver_item
				from `tabilL-Child-Fixture-Schedule-Line` line
				join `tabilL-Project-Fixture-Schedule` schedule on schedule.name = line.parent
				join `tabilL-Child-Driver-Allocation` alloc
					on alloc.parent = line.configured_fixture and alloc.parenttype = 'ilL-Configured-Fixture'
				where line.parenttype = 'ilL-Project-Fixture-Schedule' and schedule.modified >= %(cutoff)s
					and coalesce(alloc.driver_item, '') != ''
			) distinct_driver
		) used
		group by item
		""",
		{"cutoff": cutoff},
		as_dict=True,
	)
	return {
		"tape": {row["spec"]: int(row["lines"]) for row in tape},
		"item": {row["item"]: int(row["lines"]) for row in items},
	}


def with_volume(rows, counts):
	for row in rows:
		source = counts["tape"].get(row["name"]) if row["product_type"] == "Tape" else None
		row["volume"] = source if source is not None else counts["item"].get(row["item"], 0)
	return sorted(
		rows,
		key=lambda row: (
			row["status"] != STATUS_INCOMPLETE,
			-row["volume"],
			row["product_type"],
			row["name"],
		),
	)


def build_report(product_types=None):
	chosen = [t for t in (product_types or PRODUCT_TYPES) if t in ROW_BUILDERS]
	rows = [row for name in chosen for row in ROW_BUILDERS[name]()]
	return with_volume(rows, volumes())


def summarize(rows):
	counts = {}
	for row in rows:
		bucket = counts.setdefault(row["product_type"], {"total": 0, "incomplete": 0})
		bucket["total"] += 1
		bucket["incomplete"] += row["status"] == STATUS_INCOMPLETE
	return {
		"total": len(rows),
		"incomplete": sum(1 for row in rows if row["status"] == STATUS_INCOMPLETE),
		"by_type": counts,
	}


def require_reader():
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if not any(allowed(c) for c in ("catalog", "engineering", "design_review")):
		frappe.throw(_("Catalog, engineering or design review access is required"), frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def get_report(product_type=None, only_incomplete=0):
	"""Desk "Design readiness" page."""
	require_reader()
	types = [product_type] if product_type in PRODUCT_TYPES else None
	rows = build_report(types)
	summary = summarize(rows)
	if str(only_incomplete) in ("1", "true"):
		rows = [row for row in rows if row["status"] == STATUS_INCOMPLETE]
	return {"rows": rows, "summary": summary, "volume_days": VOLUME_DAYS}


def catalog_summary():
	"""Counts only (no volume queries), for the Catalog Builder badge."""
	return summarize([row for name in PRODUCT_TYPES for row in ROW_BUILDERS[name]()])
