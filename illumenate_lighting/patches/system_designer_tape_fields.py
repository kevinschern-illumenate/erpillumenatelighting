# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Pre-fill the System Designer's tape and attribute fields from data that already exists (WP-1.1).

Only empty values are written, so the patch is idempotent and never overwrites staff edits:

- ``ilL-Attribute-Output Voltage.nominal_voltage_v`` parsed from the DC/AC choice or the name ("24V" → 24).
- ``ilL-Attribute-Dimming Protocol.engine_protocol`` from the attribute's protocol choice or label
  (Appendix B.1). Unmatched values stay blank.
- ``ilL-Spec-LED Tape``: ``max_run_single_feed_ft`` copied from ``voltage_drop_max_run_length_ft``;
  ``channels`` from the LED package when it is unambiguous; ``max_simultaneous_pct`` = 100 * channels.
"""

import frappe

from illumenate_lighting.illumenate_lighting.system_design.protocols import engine_protocol_for
from illumenate_lighting.illumenate_lighting.system_design.units import parse_voltage

# Spectrum types whose channel count is unambiguous. Others (Dim to Warm, Horticulture) need staff input.
SPECTRUM_CHANNELS = {
	"Static White": 1,
	"Tunable White": 2,
	"RGB": 3,
	"RGBW": 4,
	"RGB+W": 4,
	"RGBTW": 5,
	"RGB+TW": 5,
}


def package_channels(package):
	"""Channel count for an LED package row (``channels``, ``spectrum_type``), or ``None``."""
	if not package:
		return None
	explicit = int(package.get("channels") or 0)
	if explicit > 0:
		return explicit
	return SPECTRUM_CHANNELS.get(package.get("spectrum_type"))


def execute():
	_voltages()
	_protocols()
	_tapes()


def _empty(value):
	return value in (None, "", 0, 0.0)


def _voltages():
	doctype = "ilL-Attribute-Output Voltage"
	if not frappe.db.has_column(doctype, "nominal_voltage_v"):
		return
	for row in frappe.get_all(
		doctype, fields=["name", "dc_voltage", "ac_voltage", "voltage_name", "nominal_voltage_v"]
	):
		if not _empty(row.nominal_voltage_v):
			continue
		volts = parse_voltage(row.dc_voltage, row.voltage_name, row.ac_voltage, row.name)
		if volts:
			frappe.db.set_value(doctype, row.name, "nominal_voltage_v", volts, update_modified=False)


def _protocols():
	doctype = "ilL-Attribute-Dimming Protocol"
	if not frappe.db.has_column(doctype, "engine_protocol"):
		return
	for row in frappe.get_all(doctype, fields=["name", "label", "protocol", "engine_protocol"]):
		if row.engine_protocol:
			continue
		mapped = engine_protocol_for(row.protocol, row.label or row.name)
		if mapped:
			frappe.db.set_value(doctype, row.name, "engine_protocol", mapped, update_modified=False)


def _tapes():
	doctype = "ilL-Spec-LED Tape"
	if not frappe.db.has_column(doctype, "max_run_single_feed_ft"):
		return
	packages = {
		row.name: row
		for row in frappe.get_all("ilL-Attribute-LED Package", fields=["name", "channels", "spectrum_type"])
	}
	for row in frappe.get_all(
		doctype,
		fields=[
			"name",
			"led_package",
			"voltage_drop_max_run_length_ft",
			"max_run_single_feed_ft",
			"channels",
			"max_simultaneous_pct",
		],
	):
		updates = {}
		if _empty(row.max_run_single_feed_ft) and not _empty(row.voltage_drop_max_run_length_ft):
			updates["max_run_single_feed_ft"] = row.voltage_drop_max_run_length_ft
		channels = int(row.channels or 0)
		derived = package_channels(packages.get(row.led_package))
		if channels <= 1 and derived and derived != channels:
			channels = updates["channels"] = derived
		if _empty(row.max_simultaneous_pct):
			updates["max_simultaneous_pct"] = 100 * max(channels, 1)
		if updates:
			frappe.db.set_value(doctype, row.name, updates, update_modified=False)
