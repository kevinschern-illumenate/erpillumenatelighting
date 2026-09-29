# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Product spec facts shared by Webflow Product, the Webflow export, the CSV export and spec sheets.

Each value here used to be computed separately in ``spec_sheet_export.py``,
``ill_webflow_product.py`` and ``webflow_export.py``. They now call these functions,
so the website, the InDesign CSV and generated sheets print the same thing.
Pure functions; database access stays with the callers.
"""

from illumenate_lighting.illumenate_lighting.api.unit_conversion import format_length_inches

# A 100 W supply is loaded to 80 % (80 W usable).
MAX_POWER_SUPPLY_USABLE_WATTS = 80


def has_value(value):
	return value is not None and value != ""


def number(value):
	"""``value`` as a float, or None for blanks and non-numbers."""
	if value == "" or value is None:
		return None
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def plain_number(value):
	"""``48.0`` → ``"48"``; other values unchanged."""
	if value == int(value):
		return str(int(value))
	return str(value)


def fahrenheit(celsius):
	return round(celsius * 9 / 5 + 32)


def operating_temperature(c_min, c_max):
	"""``"-40°F (-40°C) to 149°F (65°C)"``; blank unless both ends are set."""
	if c_min is None or c_max is None:
		return ""
	return f"{fahrenheit(c_min)}°F ({c_min}°C) to {fahrenheit(c_max)}°F ({c_max}°C)"


def beam_angle(value):
	"""``120`` → ``"120°"``, ``37.5`` → ``"37.5°"``; blank for no value."""
	if not value:
		return ""
	return f"{int(value)}°" if value == int(value) else f"{value}°"


def voltage_value(value, suffix):
	"""Append ``VDC``/``VAC`` unless the text already carries it (``"24V"`` → ``"24VDC"``)."""
	if not has_value(value):
		return ""
	text = str(value).strip()
	compact = text.upper().replace(" ", "")
	if compact.endswith(suffix):
		return text
	if compact.endswith("V"):
		return f"{text}{suffix[1:]}"
	return f"{text}{suffix}"


def output_voltage(dc_voltage=None, ac_voltage=None, fallback=""):
	"""Display label for an Output Voltage attribute: DC first, then AC, else ``fallback``."""
	if dc_voltage:
		return voltage_value(dc_voltage, "VDC")
	if ac_voltage:
		return voltage_value(ac_voltage, "VAC")
	return str(fallback) if fallback else ""


def driver_input_voltage(minimum, maximum, voltage_type=None):
	"""``"120V-277VAC"`` from a driver's input range; blank without both ends."""
	if minimum and maximum:
		return f"{minimum}V-{maximum}{voltage_type or 'VAC'}"
	return ""


def input_voltage(light_engine, power_supply):
	"""``"24VDC (Power Supply: 120V-277VAC)"``, or whichever part is known."""
	if light_engine and power_supply:
		return f"{light_engine} (Power Supply: {power_supply})"
	return light_engine or power_supply or ""


def mm_interval(length_mm):
	"""``50`` → ``'1.97" (50mm)'``; blank for no or zero length."""
	length_mm = number(length_mm)
	if not length_mm:
		return ""
	inches = format_length_inches(length_mm, precision=2)
	if not inches:
		return ""
	mm = int(length_mm) if length_mm == int(length_mm) else length_mm
	return f"{inches} ({mm}mm)"


def production_interval(cut_increment_mm, free_cutting=False):
	return "Free-Cutting" if free_cutting else mm_interval(cut_increment_mm)


def max_footage_per_100w_supply(watts_per_foot):
	"""Feet of tape one 100 W supply (80 W usable) carries, to 0.1 ft; blank without a wattage."""
	watts = number(watts_per_foot)
	if not watts:
		return ""
	return round(MAX_POWER_SUPPLY_USABLE_WATTS / watts, 1)


def format_max_footage_per_100w_supply(watts_per_foot):
	footage = max_footage_per_100w_supply(watts_per_foot)
	return f"{plain_number(footage)}ft" if footage != "" else ""


def cri_quality(cri_name, sdcm):
	"""``"95 CRI / 2 SDCM"``, or whichever part is known."""
	parts = []
	if cri_name:
		parts.append(cri_name)
	if sdcm:
		parts.append(f"{sdcm} SDCM")
	return " / ".join(parts)
