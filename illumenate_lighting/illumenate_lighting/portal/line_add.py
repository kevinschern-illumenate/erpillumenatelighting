"""Append one new line to a schedule document (extracted verbatim from ``api.portal.add_schedule_line``).

This is the single-line validator shared by "Add line" and the schedule import (plan 3.4). It
returns an error message, or None once the line is appended; the caller saves the schedule.
"""

import json

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.configuration_contract import TAPE_NEON_CATEGORIES
from illumenate_lighting.illumenate_lighting.utils import parse_positive_int


def append_line(schedule, line_data, is_sales_staff):
	from illumenate_lighting.illumenate_lighting.api.portal import (
		is_extrusion_kit_group,
		is_power_supply_group,
	)

	line = schedule.append("lines", {})
	line.line_id = line_data.get("line_id")
	line.qty = parse_positive_int(line_data.get("qty", 1), default=1, minimum=1)
	line.location = line_data.get("location")
	line.manufacturer_type = line_data.get("manufacturer_type", "ILLUMENATE")
	line.notes = line_data.get("notes")

	if line.manufacturer_type == "ILLUMENATE":
		line.product_type = line_data.get("product_type")
		line.fixture_template = line_data.get("fixture_template")
		line.tape_neon_template = line_data.get("tape_neon_template")
		if line.tape_neon_template:
			# The series decides LED Tape / COB Tape / LED Neon, whatever the group is called.
			category = frappe.db.get_value("ilL-Tape-Neon-Template", line.tape_neon_template, "product_category")
			if category in TAPE_NEON_CATEGORIES:
				line.product_type = category
		line.led_sheet_template = line_data.get("led_sheet_template")
		line.kit_template = line_data.get("kit_template")
		if line.kit_template or is_extrusion_kit_group(line.product_type):
			# Kit lines are always configured later through the kit configurator.
			if not line.kit_template or not frappe.db.get_value(
				"ilL-Extrusion-Kit-Template", line.kit_template, "is_active"
			):
				return _("Choose an active Extrusion Kit")
			line.product_type = "Extrusion Kit"
			line.configuration_status = "Pending"
		else:
			line.configuration_status = (
				line_data.get("configuration_status", "Pending") if is_sales_staff else "Pending"
			)

	if line.manufacturer_type == "ACCESSORY" and (
		line_data.get("driver_template") or is_power_supply_group(line_data.get("accessory_product_type"))
	):
		# Power supply lines pick an ilL-Driver-Template and are configured later in the
		# power supply configurator, which resolves the ilL-Spec-Driver Item.
		line.driver_template = line_data.get("driver_template")
		if not line.driver_template or not frappe.db.get_value(
			"ilL-Driver-Template", line.driver_template, "is_active"
		):
			return _("Choose an active power supply")
		line.accessory_product_type = line_data.get("accessory_product_type")
		line.configuration_status = "Pending"
	elif line.manufacturer_type == "ACCESSORY":
		line.accessory_product_type = line_data.get("accessory_product_type")
		line.accessory_item = line_data.get("accessory_item")
		line.accessory_item_name = line_data.get("accessory_item_name")
		# Store variant attribute selections as JSON for display
		variant_selections = line_data.get("variant_selections")
		if variant_selections:
			if isinstance(variant_selections, str):
				line.variant_selections = variant_selections
			else:
				line.variant_selections = json.dumps(variant_selections)
		# For accessories, set configuration_status to Configured since no config needed
		line.configuration_status = "Configured"

	if line.manufacturer_type == "OTHER":
		line.manufacturer_name = line_data.get("manufacturer_name")
		line.fixture_model_number = line_data.get("fixture_model_number")
		line.trim_info = line_data.get("trim_info")
		line.housing_model_number = line_data.get("housing_model_number")
		line.driver_model_number = line_data.get("driver_model_number")
		line.lamp_info = line_data.get("lamp_info")
		line.dimming_protocol = line_data.get("dimming_protocol")
		line.input_voltage = line_data.get("input_voltage")
		line.other_finish = line_data.get("other_finish")
		from illumenate_lighting.illumenate_lighting.system_design import dealer_data

		dealer_data.apply(line, line_data)
		from illumenate_lighting.illumenate_lighting.portal.files import finalize_spec

		if line_data.get("spec_sheet"):
			frappe.throw(_("Upload the specification and provide its File ID."))
		if line_data.get("spec_sheet_file_id"):
			line.spec_sheet = finalize_spec(line_data["spec_sheet_file_id"], schedule.name)

	return None
