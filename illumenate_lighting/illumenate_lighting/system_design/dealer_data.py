# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Dealer-entered design data on third-party schedule lines (D8, WP-1.6).

Third-party (``OTHER``) lines carry the facts the designer needs to calculate them: watts, input
voltage, voltage class, drive and dimming. ilLumenate does not verify them, so every output labels
them "Data by dealer". The write-back markers (``design_line_role``, ``design_line_key``) are never
set from the portal.
"""

import frappe
from frappe import _

FIELDS = (
	"watts_each",
	"input_voltage_v",
	"voltage_class",
	"third_party_drive",
	"third_party_ma",
	"third_party_dimming",
)
MAX_WATTS = 2000
VOLTAGES = (12, 24, 48, 120, 208, 240, 277)
LOW_VOLTAGE_MAX = 48
VOLTAGE_CLASSES = ("Low Voltage", "Line Voltage")
DRIVES = ("CV", "CC", "Integral Driver")
MAX_MA = 10000
DIMMING_DOCTYPE = "ilL-Attribute-Dimming Protocol"


def _blank(value):
	return value is None or (isinstance(value, str) and not value.strip())


def _number(value, label):
	if _blank(value):
		return None
	try:
		number = float(value)
	except (TypeError, ValueError):
		frappe.throw(_("{0} must be a number").format(label))
	if number != number or number in (float("inf"), float("-inf")):
		frappe.throw(_("{0} must be a number").format(label))
	return number


def _choice(value, choices, label):
	if _blank(value):
		return None
	value = str(value).strip()
	if value not in choices:
		frappe.throw(_("{0} must be one of: {1}").format(label, ", ".join(choices)))
	return value


def voltage_class_for(volts):
	if volts is None:
		return None
	return "Low Voltage" if volts <= LOW_VOLTAGE_MAX else "Line Voltage"


def clean(values):
	"""Validate one complete set of dealer design values and return them normalized.

	``values`` holds every field in :data:`FIELDS` (blank means "not entered").
	"""
	watts = _number(values.get("watts_each"), _("Watts each"))
	if watts is not None and not 0 < watts <= MAX_WATTS:
		frappe.throw(_("Watts each must be more than 0 and at most {0}").format(MAX_WATTS))
	volts = _number(values.get("input_voltage_v"), _("Input voltage"))
	if volts is not None and volts not in VOLTAGES:
		frappe.throw(_("Input voltage must be one of {0} V").format(", ".join(str(v) for v in VOLTAGES)))
	voltage_class = _choice(values.get("voltage_class"), VOLTAGE_CLASSES, _("Voltage class"))
	expected = voltage_class_for(volts)
	if voltage_class and expected and voltage_class != expected:
		frappe.throw(_("{0} V is {1}, not {2}").format(int(volts), expected, voltage_class))
	drive = _choice(values.get("third_party_drive"), DRIVES, _("Drive"))
	milliamps = _number(values.get("third_party_ma"), _("Drive current"))
	if drive == "CC":
		if milliamps is None or not 0 < milliamps <= MAX_MA:
			frappe.throw(_("Constant-current fixtures need a drive current in mA"))
	else:
		milliamps = None
	dimming = (
		None if _blank(values.get("third_party_dimming")) else str(values["third_party_dimming"]).strip()
	)
	if dimming and not frappe.db.exists(DIMMING_DOCTYPE, dimming):
		frappe.throw(_("Choose a dimming protocol from the list"))
	return {
		"watts_each": watts,
		"input_voltage_v": volts,
		"voltage_class": voltage_class or expected,
		"third_party_drive": drive,
		"third_party_ma": milliamps,
		"third_party_dimming": dimming,
	}


def apply(line, line_data):
	"""Merge the dealer's changes into ``line`` (an ``OTHER`` schedule line) after validating them.

	Only keys present in ``line_data`` change; the rest keep their stored values, and the merged set is
	validated as a whole so a partial edit cannot leave CC without a current.
	"""
	if not any(field in line_data for field in FIELDS):
		return
	merged = {field: line_data[field] if field in line_data else line.get(field) for field in FIELDS}
	for field, value in clean(merged).items():
		setattr(line, field, value)


def dimming_choices():
	"""Dimming protocol names for the portal's third-party editor."""
	return frappe.get_all(DIMMING_DOCTYPE, pluck="name", order_by="name asc")
