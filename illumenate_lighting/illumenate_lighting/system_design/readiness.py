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
# Categories the engine catalog has no schema for yet; readiness still checks their data.
NOT_IN_CATALOG = {"phase-dimmer"}
AWG = (
	"24",
	"22",
	"20",
	"18",
	"16",
	"14",
	"12",
	"10",
	"8",
	"6",
	"4",
	"3",
	"2",
	"1",
	"1/0",
	"2/0",
	"3/0",
	"4/0",
)
PHASE_OUTPUTS = {"Phase Forward", "Phase Reverse"}


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


def _number(value):
	try:
		return float(value)
	except (TypeError, ValueError):
		return 0.0


def _awg_order(smaller, larger):
	"""True when terminal ``smaller`` AWG is not larger than ``larger`` (blank passes)."""
	if not smaller or not larger or smaller not in AWG or larger not in AWG:
		return True
	return AWG.index(smaller) <= AWG.index(larger)


def _none(value):
	return value in (None, "", "None")


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
	if (
		volts
		and _positive(spec.get("min_operating_voltage_v"))
		and float(spec["min_operating_voltage_v"]) > float(volts)
	):
		missing.append("min_operating_voltage_v")
		notes.append(_("Minimum operating voltage is above the {0} V nominal").format(volts))
	single = _number(spec.get("max_run_single_feed_ft")) or _number(
		spec.get("voltage_drop_max_run_length_ft")
	)
	double = _number(spec.get("max_run_double_feed_ft"))
	if single > 0 and double > 0 and double < single:
		missing.append("max_run_double_feed_ft")
		notes.append(_("Double-feed run is shorter than the single-feed run"))
	channels = int(spec.get("channels") or 0)
	limits = spec.get("channel_limits")
	limit_count = len(limits) if limits is not None else int(spec.get("channel_limit_count") or 0)
	if channels < 1:
		missing.append("channels")
	else:
		pct = _number(spec.get("max_simultaneous_pct"))
		if pct > channels * 100:
			missing.append("max_simultaneous_pct")
			notes.append(
				_("Simultaneous percentage is above {0}% for {1} channels").format(channels * 100, channels)
			)
		if limit_count and limit_count != channels:
			missing.append("channel_limits")
			notes.append(_("{0} channel limits for {1} channels").format(limit_count, channels))
		elif limits and len({str(row.get("channel_name") or "").strip() for row in limits}) != channels:
			missing.append("channel_limits")
			notes.append(_("Channel names must be filled in and unique"))
		elif channels > 1 and not limit_count:
			notes.append(_("No channel limits; channels are named CH1 to CH{0}").format(channels))
		limited = spec.get("power_basis") == "Max Operating" and 0 < pct < channels * 100
		if limited and not (limits and all(_positive(row.get("max_w_per_ft")) for row in limits)):
			missing.append("channel_limits")
			notes.append(_("Max Operating below full output needs a W/ft limit for every channel"))
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
	low, high = _number(spec.get("input_voltage_min")), _number(spec.get("input_voltage_max"))
	if low > 0 and high > 0 and low > high:
		missing.append("input_voltage_max")
		notes.append(_("Input voltage range is reversed"))
	if spec.get("input_voltage_type") == "VDC" and spec.get("input_phase") == "3PH":
		missing.append("input_phase")
		notes.append(_("DC input cannot be three-phase"))
	if not _awg_order(spec.get("terminal_min_awg"), spec.get("terminal_max_awg")):
		missing.append("terminal_max_awg")
		notes.append(_("Largest terminal size is smaller than the smallest"))
	if spec.get("output_type") == "Constant Current":
		if _number(spec.get("compliance_v_min")) > _number(spec.get("compliance_v_max")) > 0:
			missing.append("compliance_v_max")
			notes.append(_("Compliance voltage range is reversed"))
	if _positive(spec.get("max_input_a")):
		at = _number(spec.get("max_input_a_at_v"))
		if at <= 0 or (low > 0 and high > 0 and not low <= at <= high):
			missing.append("max_input_a_at_v")
			notes.append(_("Maximum input current needs the voltage it applies at, inside the input range"))
	_protocol_issues("input_protocols", input_protocols, engine_protocols, missing, notes)
	return result(missing, notes)


def controller_category(controller_type, output_dimming=None):
	if controller_type == "Wall Dimmer":
		return WALL_DIMMER_CATEGORIES.get(output_dimming or "")
	return CONTROLLER_CATEGORIES.get(controller_type)


def _port_issues(ports, engine_protocols, missing, notes):
	names = set()
	for index, port in enumerate(ports, 1):
		name = str(port.get("port_name") or "").strip()
		if not name or name in names:
			missing.append("ports")
			notes.append(_("Port {0} needs a unique name").format(index))
		names.add(name)
		if not port.get("direction"):
			missing.append("ports")
			notes.append(_("Port {0} needs a direction").format(name or index))
		if not engine_protocols.get(port.get("protocol")):
			missing.append("ports")
			if port.get("protocol"):
				notes.append(_("unmapped protocol: {0}").format(port["protocol"]))
			else:
				notes.append(_("Port {0} needs a protocol").format(name or index))
		if port.get("direction") == "In" and int(port.get("max_devices") or 0):
			missing.append("ports")
			notes.append(_("Port {0}: device limits apply to output ports").format(name or index))


def _power_input_issues(spec, missing, notes):
	if not spec.get("input_voltage_type"):
		missing.append("input_voltage_type")
	low, high = _number(spec.get("input_voltage_min")), _number(spec.get("input_voltage_max"))
	for field, value in (("input_voltage_min", low), ("input_voltage_max", high)):
		if value <= 0:
			missing.append(field)
	if low > 0 and high > 0 and low > high:
		missing.append("input_voltage_max")
		notes.append(_("Input voltage range is reversed"))
	if not spec.get("terminal_max_awg"):
		missing.append("terminal_max_awg")
	elif not _awg_order(spec.get("terminal_min_awg"), spec.get("terminal_max_awg")):
		missing.append("terminal_max_awg")
		notes.append(_("Largest terminal size is smaller than the smallest"))


def controller_issues(spec, engine_protocols, input_protocols, output_protocols, ports):
	"""A.3 / A.5. ``ports`` is the list of ``ilL-Child-Controller-Port`` rows."""
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
	if category in NOT_IN_CATALOG:
		notes.append(_("Phase dimmers are not in the designer catalog yet"))
	_power_input_issues(spec, missing, notes)
	if category == "dmx-decoder":
		if int(spec.get("channels") or 0) < 1:
			missing.append("channels")
		for field in ("max_a_per_channel", "max_load_amps", "max_w_per_channel", "max_load_watts"):
			if not _positive(spec.get(field)):
				missing.append(field)
		if spec.get("input_voltage_type") == "VAC" and spec.get("output_dimming") not in PHASE_OUTPUTS:
			missing.append("output_dimming")
			notes.append(_("AC decoders need Phase Forward or Phase Reverse output dimming"))
		if spec.get("input_voltage_type") == "VDC" and not _none(spec.get("output_dimming")):
			missing.append("output_dimming")
			notes.append(_("DC decoders have no phase-cut output; set output dimming to None"))
		if not input_protocols:
			missing.append("input_protocols")
	elif category not in NOT_IN_CATALOG:
		if spec.get("standby_power_watts") is None:
			notes.append(_("Standby power not entered; the designer counts 0 W"))
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
	if category != "dmx-decoder":
		if not ports:
			missing.append("ports")
		_port_issues(ports, engine_protocols, missing, notes)
	if category == "dmx-0-10v-converter":
		engine_in = {engine_protocols.get(name) for name in input_protocols}
		engine_out = {engine_protocols.get(name) for name in output_protocols}
		if "DMX512" not in engine_in:
			missing.append("input_protocols")
			notes.append(_("Converters need DMX512 as an input protocol"))
		if "0-10V" not in engine_out:
			missing.append("output_protocols")
			notes.append(_("Converters need 0-10V as an output protocol"))
		port_protocols = [(p.get("direction"), engine_protocols.get(p.get("protocol"))) for p in ports]
		if ("In", "DMX512") not in port_protocols and ("Bidirectional", "DMX512") not in port_protocols:
			missing.append("ports")
			notes.append(_("Converters need a DMX512 input port"))
		if ("Out", "0-10V") not in port_protocols:
			missing.append("ports")
			notes.append(_("Converters need a 0-10V output port"))
	return result(missing, notes)


def wire_issues(spec, has_price, conductors=None):
	"""A.6 and D7: a wire the designer may quote needs a selling Item Price.

	``conductors`` is the list of ``ilL-Child-Wire-Conductor`` rows; ``None`` skips the cable checks.
	"""
	from illumenate_lighting.illumenate_lighting.system_design import wire

	missing, notes = [], []
	if not has_price:
		missing.append("item_price")
		notes.append(_("Item {0} has no selling Item Price").format(spec.get("item")))
	if not spec.get("is_verified"):
		notes.append(_("Not verified by engineering yet"))
	if conductors is None:
		return result(missing, notes)
	for field in ("wire_name", "listing", "riser_label", "source_reference"):
		if not str(spec.get(field) or "").strip():
			missing.append(field)
	applications, unknown = wire.split_applications(spec.get("applications"))
	if unknown or not applications:
		missing.append("applications")
	elif "wireless" in applications:
		missing.append("applications")
		notes.append(_("Wireless is not a cable; remove it from Applications"))
	if not wire.category_label(spec.get("category")):
		missing.append("category")
	if str(spec.get("temp_rating_c") or "") not in wire.TEMP_RATINGS:
		missing.append("temp_rating_c")
	if not _positive(spec.get("rated_v")):
		missing.append("rated_v")
	if not conductors:
		missing.append("conductors")
	elif problems := wire.conductor_problems(conductors):
		missing.append("conductors")
		notes.extend(problems)
	for row in conductors:
		if row.get("awg") in ("22", "24") and not (
			_positive(row.get("resistance_ohm_per_kft")) or _positive(spec.get("resistance_ohm_per_kft"))
		):
			missing.append("resistance_ohm_per_kft")
			notes.append(_("22 and 24 AWG need a measured resistance"))
	if spec.get("direct_burial") and not spec.get("wet"):
		missing.append("wet")
		notes.append(_("Direct-burial wire must also be wet rated"))
	if spec.get("category") == "Building Wire" and spec.get("ampacity_basis") != "310.16":
		missing.append("ampacity_basis")
		notes.append(_("Building wire ampacity uses NEC 310.16"))
	return result(missing, notes)


# --- Report -----------------------------------------------------------------------------------


def _child_rows(doctype, parenttype, parents, fields, parentfield=None):
	"""Child rows grouped by parent, in form order (one query, no N+1)."""
	if not parents:
		return {}
	filters = {"parenttype": parenttype, "parent": ["in", parents]}
	if parentfield:
		filters["parentfield"] = parentfield
	grouped = {}
	for row in frappe.get_all(doctype, filters=filters, fields=["parent", *fields], order_by="idx asc"):
		grouped.setdefault(row.pop("parent"), []).append(row)
	return grouped


def _child_names(doctype, parenttype, parents, field, parentfield=None):
	rows = _child_rows(doctype, parenttype, parents, [field], parentfield)
	return {parent: [row[field] for row in values if row.get(field)] for parent, values in rows.items()}


def engine_protocols():
	return {
		row["name"]: row["engine_protocol"]
		for row in frappe.get_all("ilL-Attribute-Dimming Protocol", fields=["name", "engine_protocol"])
	}


def voltages():
	return {
		row["name"]: row["nominal_voltage_v"]
		for row in frappe.get_all("ilL-Attribute-Output Voltage", fields=["name", "nominal_voltage_v"])
	}


TAPE_FIELDS = (
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
	"reel_length_m",
	"pixel_protocol",
	"pixels_per_m",
	"amps_per_pixel_max",
)
DRIVER_FIELDS = (
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
	"class2_outputs",
	"efficiency",
	"power_factor",
	"usable_load_factor",
	"max_input_a",
	"max_input_a_at_v",
	"inrush_a",
	"max_units_per_20a_breaker",
	"terminal_min_awg",
	"terminal_max_awg",
)
CONTROLLER_FIELDS = (
	"name",
	"item",
	"controller_name as label",
	"controller_type",
	"output_dimming",
	"input_voltage_type",
	"input_voltage_min",
	"input_voltage_max",
	"standby_power_watts",
	"channels",
	"max_a_per_channel",
	"max_load_amps",
	"max_w_per_channel",
	"max_load_watts",
	"dmx_footprint",
	"unit_load",
	"dmx_thru",
	"max_universes",
	"max_pixels",
	"max_bus_devices",
	"max_data_length_ft",
	"min_load_w",
	"led_max_w",
	"max_supplies",
	"terminal_min_awg",
	"terminal_max_awg",
)
WIRE_FIELDS = (
	"name",
	"item",
	"wire_name",
	"wire_name as label",
	"category",
	"applications",
	"riser_label",
	"is_verified",
	"source_reference",
	"listing",
	"rated_v",
	"temp_rating_c",
	"plenum",
	"riser",
	"wet",
	"direct_burial",
	"sunlight_resistant",
	"shielded",
	"impedance_ohm",
	"resistance_ohm_per_kft",
	"ampacity_a",
	"ampacity_basis",
	"od_in",
	"sales_uom_mode",
	"spool_length_ft",
)


def load_tapes():
	specs = frappe.get_all(TAPE, fields=list(TAPE_FIELDS), order_by="name asc")
	limits = _child_rows(
		"ilL-Child-Tape-Channel", TAPE, [s["name"] for s in specs], ["channel_name", "max_w_per_ft"]
	)
	for spec in specs:
		spec["channel_limits"] = limits.get(spec["name"], [])
	return specs


def load_drivers():
	specs = frappe.get_all(DRIVER, fields=list(DRIVER_FIELDS), order_by="name asc")
	names = [s["name"] for s in specs]
	protocols = _child_names("ilL-Child-Driver-Input-Protocol", DRIVER, names, "protocol")
	certifications = _child_names("ilL-Child-Spec-Certification", DRIVER, names, "certification")
	for spec in specs:
		spec["input_protocols"] = protocols.get(spec["name"], [])
		spec["certifications"] = certifications.get(spec["name"], [])
	return specs


def load_controllers():
	specs = frappe.get_all(
		CONTROLLER, filters={"is_active": 1}, fields=list(CONTROLLER_FIELDS), order_by="name asc"
	)
	names = [s["name"] for s in specs]
	child = "ilL-Child-Controller-Protocol"
	inputs = _child_names(child, CONTROLLER, names, "protocol", "input_protocols")
	outputs = _child_names(child, CONTROLLER, names, "protocol", "output_protocols")
	ports = _child_rows(
		"ilL-Child-Controller-Port",
		CONTROLLER,
		names,
		["port_name", "direction", "protocol", "max_devices"],
	)
	for spec in specs:
		spec["input_protocols"] = inputs.get(spec["name"], [])
		spec["output_protocols"] = outputs.get(spec["name"], [])
		spec["ports"] = ports.get(spec["name"], [])
	return specs


def load_wires():
	specs = frappe.get_all(WIRE, filters={"is_active": 1}, fields=list(WIRE_FIELDS), order_by="name asc")
	conductors = _child_rows(
		"ilL-Child-Wire-Conductor",
		WIRE,
		[s["name"] for s in specs],
		["count", "awg", "material", "stranding", "role", "colors", "resistance_ohm_per_kft", "ampacity_a"],
	)
	priced = set()
	items = [s["item"] for s in specs if s.get("item")]
	if items:
		priced = set(
			frappe.get_all(
				"Item Price", filters={"item_code": ["in", items], "selling": 1}, pluck="item_code"
			)
		)
	for spec in specs:
		spec["conductors"] = conductors.get(spec["name"], [])
		spec["has_price"] = spec.get("item") in priced
	return specs


def tape_check(spec, context):
	return tape_issues(spec, context["voltages"])


def driver_check(spec, context):
	return driver_issues(spec, context["voltages"], context["engine"], spec["input_protocols"])


def controller_check(spec, context):
	return controller_issues(
		spec, context["engine"], spec["input_protocols"], spec["output_protocols"], spec["ports"]
	)


def wire_check(spec, _context=None):
	return wire_issues(spec, spec["has_price"], spec["conductors"])


def context():
	return {"voltages": voltages(), "engine": engine_protocols()}


def _rows(product_type, doctype, specs, check):
	shared = context()
	return [
		{
			"product_type": product_type,
			"doctype": doctype,
			"name": spec["name"],
			"item": spec.get("item"),
			"label": spec.get("label") or spec["name"],
			**check(spec, shared),
		}
		for spec in specs
	]


def tape_rows():
	return _rows("Tape", TAPE, load_tapes(), tape_check)


def driver_rows():
	return _rows("Driver", DRIVER, load_drivers(), driver_check)


def controller_rows():
	return _rows("Controller", CONTROLLER, load_controllers(), controller_check)


def wire_rows():
	return _rows("Wire", WIRE, load_wires(), wire_check)


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
