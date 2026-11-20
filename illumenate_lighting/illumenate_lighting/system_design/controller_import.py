# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Desk CSV import for lighting controls (controls in v1, PRD question 7).

One CSV row becomes one sellable Item and one ``ilL-Spec-Controller`` with its protocols and ports, so
pixel controllers, playback controllers and decoders reach the designer catalog and the CAD catalog the
same way field wire does (``wire_import``). Start from ``tools/seed_imports/controls_common.csv``.

Ports are ``name:direction:protocol[:max devices]`` separated by ``;`` (``DMX 1:Out:DMX512``); protocols
are names of ``ilL-Attribute-Dimming Protocol`` records separated by commas. Ethernet lighting protocols
the site does not have yet (sACN, Art-Net) are created with their engine mapping. The import is
all-or-nothing; the dry run (the default) only reports.
"""

import csv
import io

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.system_design.access import require_capability
from illumenate_lighting.illumenate_lighting.system_design.api import endpoint
from illumenate_lighting.illumenate_lighting.system_design.errors import DesignError

SPEC_DOCTYPE = "ilL-Spec-Controller"
PROTOCOL_DOCTYPE = "ilL-Attribute-Dimming Protocol"
DEFAULT_ITEM_GROUP = "Lighting Controls"
MAX_ROWS = 200
COLUMNS = (
	"item_code",
	"item_name",
	"controller_name",
	"controller_type",
	"input_voltage_type",
	"input_voltage_min",
	"input_voltage_max",
	"standby_power_watts",
	"channels",
	"max_universes",
	"max_pixels",
	"max_data_length_ft",
	"dmx_footprint",
	"unit_load",
	"max_w_per_channel",
	"max_a_per_channel",
	"max_load_watts",
	"max_load_amps",
	"output_dimming",
	"terminal_min_awg",
	"terminal_max_awg",
	"input_protocols",
	"output_protocols",
	"ports",
	"item_group",
	"source_reference",
	"is_active",
)
REQUIRED = ("item_code", "controller_name", "controller_type", "source_reference")
CONTROLLER_TYPES = (
	"DMX Controller",
	"Wireless Receiver",
	"Wall Dimmer",
	"Scene Controller",
	"Sensor",
	"Gateway",
	"Repeater",
	"DMX Decoder",
	"DMX to 0-10V Converter",
	"Pixel Controller",
	"Wireless Transmitter",
	"Relay",
	"Lutron Module",
)
DIRECTIONS = ("In", "Out", "Bidirectional")
VOLTAGE_TYPES = ("VAC", "VDC")
OUTPUT_DIMMING = ("None", "Phase Forward", "Phase Reverse", "0-10V")
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
INTS = ("input_voltage_min", "input_voltage_max", "channels", "max_universes", "max_pixels", "dmx_footprint")
FLOATS = (
	"standby_power_watts",
	"max_data_length_ft",
	"unit_load",
	"max_w_per_channel",
	"max_a_per_channel",
	"max_load_watts",
	"max_load_amps",
)
# Protocols an import may create when the site lacks them: label -> (protocol select, code, engine).
NEW_PROTOCOLS = {
	"sACN": ("SACN", "SACN", "sACN"),
	"Art-Net": ("ARTNET", "ARTNET", "Art-Net"),
}


def _split(value):
	return [part.strip() for part in str(value or "").split(",") if part.strip()]


def parse_ports(text):
	"""``(rows, problems)`` from ``name:direction:protocol[:max devices]; ...``."""
	rows, problems = [], []
	for index, part in enumerate(p.strip() for p in str(text or "").split(";")):
		if not part:
			continue
		pieces = [piece.strip() for piece in part.split(":")]
		if len(pieces) not in (3, 4) or not all(pieces[:3]):
			problems.append(
				f"Port {index + 1} '{part}' should look like 'DMX 1:Out:DMX512' or 'OUT1:Out:SPI:1020'"
			)
			continue
		name, direction, protocol = pieces[:3]
		if direction not in DIRECTIONS:
			problems.append(f"Port {name}: direction must be In, Out or Bidirectional")
			continue
		row = {"port_name": name, "direction": direction, "protocol": protocol}
		if len(pieces) == 4 and pieces[3]:
			try:
				row["max_devices"] = int(pieces[3])
			except ValueError:
				problems.append(f"Port {name}: max devices must be a whole number")
				continue
			if direction == "In":
				problems.append(f"Port {name}: device limits apply to output ports")
		rows.append(row)
	names = [row["port_name"] for row in rows]
	if len(names) != len(set(names)):
		problems.append("Port names must be unique")
	return rows, problems


def parse_csv(text):
	"""Rows of ``{row, item_code, item_name, item_group, spec, protocols, problems}``."""
	if not isinstance(text, str) or not text.strip():
		raise DesignError("INVALID", _("The CSV file is empty"))
	reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
	headers = [h.strip() for h in reader.fieldnames or []]
	missing = [column for column in REQUIRED if column not in headers]
	if missing:
		raise DesignError("INVALID", _("The CSV is missing columns: {0}").format(", ".join(missing)))
	rows, seen = [], {}
	for number, raw in enumerate(reader, start=2):
		values = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k}
		if not any(values.values()):
			continue
		if len(rows) >= MAX_ROWS:
			raise DesignError("INVALID", _("Import at most {0} controls at a time").format(MAX_ROWS))
		problems = [f"{column} is required" for column in REQUIRED if not values.get(column)]
		spec = {
			"item": values.get("item_code"),
			"controller_name": values.get("controller_name"),
			"controller_type": values.get("controller_type"),
			"input_voltage_type": values.get("input_voltage_type") or None,
			"output_dimming": values.get("output_dimming") or "None",
			"terminal_min_awg": values.get("terminal_min_awg") or None,
			"terminal_max_awg": values.get("terminal_max_awg") or None,
			"is_active": 0 if values.get("is_active") in ("0", "no", "false") else 1,
			"notes": values.get("source_reference"),
		}
		if spec["controller_type"] and spec["controller_type"] not in CONTROLLER_TYPES:
			problems.append(f"Unknown controller type '{spec['controller_type']}'")
		if spec["input_voltage_type"] and spec["input_voltage_type"] not in VOLTAGE_TYPES:
			problems.append("input_voltage_type must be VAC or VDC")
		if spec["output_dimming"] not in OUTPUT_DIMMING:
			problems.append("output_dimming must be None, Phase Forward, Phase Reverse or 0-10V")
		for field in ("terminal_min_awg", "terminal_max_awg"):
			if spec[field] and spec[field] not in AWG:
				problems.append(f"{field} must be an AWG size")
		for field in INTS + FLOATS:
			text_value = values.get(field, "")
			if not text_value:
				continue
			try:
				number_value = float(text_value)
			except ValueError:
				problems.append(f"{field} must be a number")
				continue
			if number_value < 0:
				problems.append(f"{field} cannot be negative")
			if field in INTS and not number_value.is_integer():
				problems.append(f"{field} must be a whole number")
			spec[field] = int(number_value) if field in INTS else number_value
		ports, port_problems = parse_ports(values.get("ports"))
		problems += port_problems
		protocols = {
			"input_protocols": _split(values.get("input_protocols")),
			"output_protocols": _split(values.get("output_protocols")),
		}
		if not ports and spec.get("controller_type") != "DMX Decoder":
			problems.append("List the control's ports")
		code = values.get("item_code")
		if code in seen:
			problems.append(f"item_code {code} is repeated (first on row {seen[code]})")
		elif code:
			seen[code] = number
		rows.append(
			{
				"row": number,
				"item_code": code,
				"item_name": values.get("item_name") or values.get("controller_name"),
				"item_group": values.get("item_group") or DEFAULT_ITEM_GROUP,
				"spec": spec,
				"ports": ports,
				"protocols": protocols,
				"problems": problems,
			}
		)
	if not rows:
		raise DesignError("INVALID", _("The CSV has no controls"))
	return rows


def used_protocols(row):
	return {
		*row["protocols"]["input_protocols"],
		*row["protocols"]["output_protocols"],
		*(port["protocol"] for port in row["ports"]),
	}


def plan_rows(rows):
	"""Add actions and the protocol checks that need the database."""
	for row in rows:
		code = row["item_code"]
		row["item_action"] = "existing" if code and frappe.db.exists("Item", code) else "create"
		row["spec_action"] = "update" if code and frappe.db.exists(SPEC_DOCTYPE, {"item": code}) else "create"
		for protocol in sorted(used_protocols(row)):
			if not frappe.db.exists(PROTOCOL_DOCTYPE, protocol) and protocol not in NEW_PROTOCOLS:
				row["problems"].append(f"Protocol '{protocol}' is not an ilL-Attribute-Dimming Protocol")
		if row["item_action"] == "create" and not frappe.db.exists("Item Group", row["item_group"]):
			if row["item_group"] != DEFAULT_ITEM_GROUP:
				row["problems"].append(f"Item Group '{row['item_group']}' does not exist")
	return rows


def ensure_masters(rows):
	"""The default Item Group and any Ethernet protocols the rows use (idempotent)."""
	if not frappe.db.exists("Item Group", DEFAULT_ITEM_GROUP) and frappe.db.exists(
		"Item Group", "All Item Groups"
	):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": DEFAULT_ITEM_GROUP,
				"parent_item_group": "All Item Groups",
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
	needed = set().union(*(used_protocols(row) for row in rows))
	for label, (protocol, code, engine) in NEW_PROTOCOLS.items():
		if label in needed and not frappe.db.exists(PROTOCOL_DOCTYPE, label):
			frappe.get_doc(
				{
					"doctype": PROTOCOL_DOCTYPE,
					"label": label,
					"protocol": protocol,
					"code": code,
					"signal_type": "Digital",
					"engine_protocol": engine,
				}
			).insert(ignore_permissions=True)


def _write(row):
	if row["item_action"] == "create":
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": row["item_code"],
				"item_name": row["item_name"],
				"item_group": row["item_group"],
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"is_sales_item": 1,
				"description": row["spec"]["controller_name"],
			}
		).insert(ignore_permissions=True)
	if row["spec_action"] == "update":
		doc = frappe.get_doc(
			SPEC_DOCTYPE, frappe.db.get_value(SPEC_DOCTYPE, {"item": row["item_code"]}, "name")
		)
		doc.update(row["spec"])
		for table in ("input_protocols", "output_protocols", "ports"):
			doc.set(table, [])
	else:
		doc = frappe.get_doc({"doctype": SPEC_DOCTYPE, **row["spec"]})
	for table in ("input_protocols", "output_protocols"):
		for protocol in row["protocols"][table]:
			doc.append(table, {"protocol": protocol})
	for port in row["ports"]:
		doc.append("ports", port)
	if row["spec_action"] == "update":
		doc.save(ignore_permissions=True)
	else:
		doc.insert(ignore_permissions=True)


def import_controller_csv(text, dry_run=True):
	rows = plan_rows(parse_csv(text))
	invalid = sum(1 for row in rows if row["problems"])
	report = {
		"dry_run": bool(dry_run),
		"written": False,
		"invalid": invalid,
		"rows": [
			{
				"row": row["row"],
				"item_code": row["item_code"],
				"item_action": row["item_action"],
				"spec_action": row["spec_action"],
				"problems": row["problems"],
			}
			for row in rows
		],
	}
	if dry_run or invalid:
		return report
	frappe.db.savepoint("controller_import")
	try:
		ensure_masters(rows)
		for row in rows:
			_write(row)
	except Exception:
		frappe.db.rollback(save_point="controller_import")
		raise
	report["written"] = True
	return report


@frappe.whitelist(methods=["POST"])
@endpoint
def import_controllers(csv_text=None, dry_run=1):
	"""Desk: import reviewed lighting controls. Catalog staff only."""
	require_capability("catalog")
	return import_controller_csv(csv_text, dry_run=str(dry_run).strip().lower() not in {"0", "false", "no"})
