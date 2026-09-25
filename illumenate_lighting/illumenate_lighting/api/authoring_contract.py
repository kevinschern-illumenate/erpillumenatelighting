"""Pure engineering checks shared by publication preflight and import tooling.

Drafts remain saveable. Findings prevent channel approval, not ordinary editing.
"""

import math


def record_issues(doctype, record):
	errors = []

	def error(field, message):
		errors.append(
			{
				"record": record.get("name") or record.get("template_code") or record.get("item"),
				"field": field,
				"message": message,
			}
		)

	def required(*fields):
		for field in fields:
			if not record.get(field):
				error(field, "Set this engineering value before channel approval")

	def number(field, *, positive=True, maximum=None, integer=False):
		try:
			value = record.get(field)
			if isinstance(value, bool):
				raise ValueError
			value = float(value)
			if (
				not math.isfinite(value)
				or (value <= 0 if positive else value < 0)
				or (maximum is not None and value > maximum)
				or (integer and not value.is_integer())
			):
				raise ValueError
		except (TypeError, ValueError):
			error(
				field,
				"Enter a finite "
				+ ("positive" if positive else "nonnegative")
				+ (" whole number" if integer else " number")
				+ (f" at most {maximum}" if maximum is not None else ""),
			)

	if doctype.startswith("ilL-Spec-"):
		required("item")
	if doctype == "ilL-Spec-LED Tape":
		required("input_voltage", "input_protocol", "led_package")
		for field in ("watts_per_foot", "voltage_drop_max_run_length_ft"):
			number(field)
		free_cutting = record.get("is_free_cutting")
		if free_cutting not in (None, "", False, True, 0, 1, "0", "1", "false", "true"):
			error("is_free_cutting", "Use a boolean checkbox value")
		if free_cutting not in (True, 1, "1", "true"):
			number("cut_increment_mm")
	elif doctype == "ilL-Spec-LED-Sheet":
		required("input_voltage", "input_protocol", "led_package", "cct")
		for field in ("sheet_width_ft", "sheet_height_ft"):
			number(field)
		# Full panel rating is preferred. Density is a valid full-load source too.
		try:
			has_full_rating = float(record.get("total_sheet_watts") or 0) != 0
		except (TypeError, ValueError):
			has_full_rating = True
		number("total_sheet_watts" if has_full_rating else "watts_per_sqft")
		if record.get("max_panels_per_feed") not in (None, "", 0, "0", "0.0"):
			number("max_panels_per_feed", integer=True)
	elif doctype == "ilL-Spec-Driver":
		required("voltage_output", "output_type", "output_protocol")
		for field in ("max_wattage", "max_wattage_per_output"):
			number(field)
		number("usable_load_factor", maximum=1)
		number("outputs_count", integer=True)
		if record.get("outputs_count") != 1:
			number("independent_outputs_count", integer=True)
		try:
			if float(record.get("independent_outputs_count") or 1) > float(record.get("outputs_count") or 0):
				error("independent_outputs_count", "Independent feeds cannot exceed physical outputs")
		except (TypeError, ValueError):
			pass
		if not any(row.get("protocol") for row in record.get("input_protocols") or []):
			error("input_protocols", "Declare supported input/dimming protocols")
	elif doctype == "ilL-Spec-Controller":
		required("controller_type", "mounting_type", "input_voltage_type")
		for field in ("input_voltage_min", "input_voltage_max", "channels", "zones"):
			number(field, integer=field in ("channels", "zones"))
		try:
			if float(record.get("input_voltage_min") or 0) > float(record.get("input_voltage_max") or 0):
				error("input_voltage_max", "Maximum voltage must be at least the minimum")
		except (TypeError, ValueError):
			pass
		for field in ("input_protocols", "output_protocols"):
			if not any(row.get("protocol") for row in record.get(field) or []):
				error(field, "Declare supported control protocols")
	if doctype in ("ilL-Fixture-Template", "ilL-Tape-Neon-Template"):
		for field in ("base_price_msrp", "price_per_ft_msrp"):
			number(field, positive=False)
		if doctype == "ilL-Fixture-Template":
			required("default_profile_spec")
			for field in ("default_profile_stock_len_mm", "assembled_max_len_mm"):
				number(field)
	elif doctype == "ilL-LED-Sheet-Template":
		required("sku_series_code", "leader_cable_item", "jumper_cable_item")
		number("price_per_sheet_msrp", positive=False)
	if doctype.endswith("-Template"):
		seen, defaults = {}, set()
		for row in record.get("allowed_options") or []:
			if not row.get("is_active", True):
				continue
			kind = row.get("option_type") or row.get("attribute_type")
			value = row.get("attribute_link") or row.get("attribute_value")
			code = row.get("option_code") or value
			if kind and code:
				key = (kind, code)
				if key in seen and seen[key] != value:
					error("allowed_options", f"{kind} code {code} maps to multiple choices")
				seen[key] = value
			if row.get("is_default"):
				if kind in defaults:
					error("allowed_options", f"Choose one default for {kind}")
				defaults.add(kind)
	return errors
