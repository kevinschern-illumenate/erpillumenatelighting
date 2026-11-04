"""Apply a dealer's edit to one schedule line (extracted from ``api.portal.update_schedule_line``).

This is the single-line validator shared by the per-row editor and bulk edit (plan 3.3): only
the keys present in ``line_data`` change.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.utils import parse_positive_int


def apply_line_data(schedule, line, line_data):
	# Update allowed fields
	if "line_id" in line_data:
		line.line_id = line_data.get("line_id")
	if "qty" in line_data:
		line.qty = parse_positive_int(line_data.get("qty", 1), default=1, minimum=1)
		# For a configured LED Sheet, the line qty is the bundle/fixture count.
		# Re-sync only this sheet's generated jumper/leader/power-supply rows so
		# their quantities scale with the new bundle quantity.
		if (
			line.manufacturer_type == "ILLUMENATE"
			and getattr(line, "product_type", None) == "LED Sheet"
			and getattr(line, "configured_led_sheet", None)
		):
			from illumenate_lighting.illumenate_lighting.api.led_sheet_configurator import (
				resync_led_sheet_line_accessories,
			)

			resync_led_sheet_line_accessories(schedule, line, line.qty)
	if "location" in line_data:
		line.location = line_data.get("location")
	if "notes" in line_data:
		line.notes = line_data.get("notes")

	# For OTHER manufacturer type, also allow updating these fields
	if line.manufacturer_type == "OTHER":
		if "manufacturer_name" in line_data:
			line.manufacturer_name = line_data.get("manufacturer_name")
		if "fixture_model_number" in line_data:
			line.fixture_model_number = line_data.get("fixture_model_number")
		if "trim_info" in line_data:
			line.trim_info = line_data.get("trim_info")
		if "housing_model_number" in line_data:
			line.housing_model_number = line_data.get("housing_model_number")
		if "driver_model_number" in line_data:
			line.driver_model_number = line_data.get("driver_model_number")
		if "lamp_info" in line_data:
			line.lamp_info = line_data.get("lamp_info")
		if "dimming_protocol" in line_data:
			line.dimming_protocol = line_data.get("dimming_protocol")
		if "input_voltage" in line_data:
			line.input_voltage = line_data.get("input_voltage")
		if "other_finish" in line_data:
			line.other_finish = line_data.get("other_finish")
		from illumenate_lighting.illumenate_lighting.system_design import dealer_data

		dealer_data.apply(line, line_data)
		from illumenate_lighting.illumenate_lighting.portal.files import finalize_spec

		if "spec_sheet" in line_data and line_data["spec_sheet"] != line.spec_sheet:
			frappe.throw(_("Upload the replacement specification and provide its File ID."))
		if line_data.get("spec_sheet_file_id"):
			line.spec_sheet = finalize_spec(line_data["spec_sheet_file_id"], schedule.name)
