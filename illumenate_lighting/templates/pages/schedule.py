# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe

no_cache = 1


def get_context(context):
	"""Get context for the schedule detail portal page."""
	if frappe.session.user == "Guest":
		frappe.throw("Please login to view schedules", frappe.PermissionError)

	# Check if this is a new schedule creation (routed from /portal/projects/<project>/schedules/new)
	project_name = frappe.form_dict.get("project")
	if project_name:
		# This is the new schedule creation flow
		return _get_new_schedule_context(context, project_name)

	# Get schedule name from path
	schedule_name = frappe.form_dict.get("schedule")
	if not schedule_name:
		frappe.throw("Schedule not specified", frappe.DoesNotExistError)

	# Get schedule with permission check
	if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		frappe.throw("Schedule not found", frappe.DoesNotExistError)

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Check permission via schedule permission hook
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		has_permission,
	)

	if not has_permission(schedule, "read", frappe.session.user):
		frappe.throw("You don't have permission to view this schedule", frappe.PermissionError)

	# Check if user can edit
	can_edit = has_permission(schedule, "write", frappe.session.user)

	# Check if user can view pricing
	from illumenate_lighting.illumenate_lighting.api.exports import _check_pricing_permission
	can_view_pricing = _check_pricing_permission(frappe.session.user)

	# Check if user is a dealer (can create sales orders directly without quote)
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_is_dealer_user,
		_is_internal_user,
	)
	is_dealer = _is_dealer_user(frappe.session.user)
	is_internal = _is_internal_user(frappe.session.user)

	# Get project
	project = None
	if schedule.ill_project:
		project = frappe.get_doc("ilL-Project", schedule.ill_project)

	# Get lines
	lines = schedule.lines or []

	# Calculate summary stats
	total_qty = sum(line.qty or 0 for line in lines)
	illumenate_count = sum(1 for line in lines if line.manufacturer_type == "ILLUMENATE")
	other_count = sum(1 for line in lines if line.manufacturer_type == "OTHER")

	# Create enriched line data for template display
	# We'll add cf_details directly to each line for easy access in the template
	lines_with_details = []
	lines_json = []
	for line in lines:
		# Create a dict representation with all needed fields
		line_dict = {
			"idx": line.idx,
			"line_id": line.line_id,
			"qty": line.qty,
			"location": line.location,
			"manufacturer_type": line.manufacturer_type,
			"notes": line.notes,
			"configured_fixture": line.configured_fixture,
			"ill_item_code": line.ill_item_code,
			"manufacturable_length_mm": line.manufacturable_length_mm,
			# Other manufacturer fields
			"manufacturer_name": line.manufacturer_name,
			"fixture_model_number": line.fixture_model_number,
			"trim_info": line.trim_info,
			"housing_model_number": line.housing_model_number,
			"driver_model_number": line.driver_model_number,
			"lamp_info": line.lamp_info,
			"dimming_protocol": line.dimming_protocol,
			"input_voltage": line.input_voltage,
			"other_finish": line.other_finish,
			"spec_sheet": line.spec_sheet,
			"cf_details": {},
		}

		# For ilLumenate fixtures, fetch enriched details from configured fixture
		if line.manufacturer_type == "ILLUMENATE" and line.configured_fixture:
			cf_details = _get_configured_fixture_display_details(line.configured_fixture)
			line_dict["cf_details"] = cf_details

		lines_with_details.append(line_dict)
		lines_json.append(line_dict)

	context.schedule = schedule
	context.project = project
	context.lines = lines_with_details  # Use enriched lines instead of raw child table
	context.lines_json = lines_json
	context.can_edit = can_edit
	context.can_view_pricing = can_view_pricing
	context.is_dealer = is_dealer
	context.is_internal = is_internal
	context.total_qty = total_qty
	context.illumenate_count = illumenate_count
	context.other_count = other_count
	context.schedule_status_class = schedule_status_class
	context.title = schedule.schedule_name
	context.no_cache = 1

	return context


def _get_new_schedule_context(context, project_name):
	"""Get context for creating a new schedule."""
	# Validate project exists
	if not frappe.db.exists("ilL-Project", project_name):
		frappe.throw("Project not found", frappe.DoesNotExistError)

	project = frappe.get_doc("ilL-Project", project_name)

	# Check permission on project (user must be able to write to project to create schedules)
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		has_permission as project_has_permission,
	)

	if not project_has_permission(project, "write", frappe.session.user):
		frappe.throw("You don't have permission to create schedules in this project", frappe.PermissionError)

	context.is_new = True
	context.project = project
	context.title = "Create Schedule"
	context.no_cache = 1

	return context


def schedule_status_class(status):
	"""Return CSS class for schedule status badge."""
	class_map = {
		"DRAFT": "warning",
		"READY": "info",
		"QUOTED": "primary",
		"ORDERED": "success",
		"CLOSED": "secondary",
	}
	return class_map.get(status, "secondary")


def _get_configured_fixture_display_details(configured_fixture_id):
	"""
	Get display-ready details for a configured fixture.

	Returns dict with computed values for portal display.
	"""
	if not frappe.db.exists("ilL-Configured-Fixture", configured_fixture_id):
		return {}

	try:
		cf = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_id)

		# Calculate length in inches
		length_mm = cf.manufacturable_overall_length_mm or 0
		length_inches = length_mm / 25.4 if length_mm else 0
		
		details = {
			"part_number": cf.configured_item or cf.config_hash,
			"finish": None,
			"lens_appearance": None,
			"cct": None,
			"cri": None,
			"led_package": None,
			"output_level": None,
			"estimated_delivered_output": None,
			"power_supply": None,
			"power_supply_qty": None,
			"driver_input_voltage": None,
			"fixture_input_voltage": None,
			"manufacturable_length_mm": length_mm,
			"manufacturable_length_inches": round(length_inches, 1) if length_inches else None,
			"total_watts": cf.total_watts,
			# Multi-segment fields
			"is_multi_segment": cf.is_multi_segment if hasattr(cf, "is_multi_segment") else 0,
			"user_segment_count": cf.user_segment_count if hasattr(cf, "user_segment_count") else 0,
			"build_description": cf.build_description if hasattr(cf, "build_description") else "",
			"total_endcaps": cf.total_endcaps if hasattr(cf, "total_endcaps") else 0,
			"total_mounting_accessories": cf.total_mounting_accessories if hasattr(cf, "total_mounting_accessories") else 0,
		}

		# Get finish display name
		if cf.finish:
			finish_doc = frappe.db.get_value(
				"ilL-Attribute-Finish",
				cf.finish,
				["code", "display_name"],
				as_dict=True,
			)
			if finish_doc:
				details["finish"] = finish_doc.display_name or finish_doc.code or cf.finish

		# Get lens appearance and transmission
		lens_transmission = 100  # Default 100% if not found
		if cf.lens_appearance:
			lens_doc = frappe.db.get_value(
				"ilL-Attribute-Lens Appearance",
				cf.lens_appearance,
				["label", "transmission"],
				as_dict=True,
			)
			if lens_doc:
				details["lens_appearance"] = lens_doc.label or cf.lens_appearance
				if lens_doc.transmission:
					lens_transmission = lens_doc.transmission

		# Get tape offering details (CCT, LED Package, Output Level, CRI)
		if cf.tape_offering:
			tape_offering = frappe.db.get_value(
				"ilL-Rel-Tape Offering",
				cf.tape_offering,
				["cct", "led_package", "output_level", "tape_spec", "cri"],
				as_dict=True,
			)
			if tape_offering:
				details["cct"] = tape_offering.cct
				details["led_package"] = tape_offering.led_package
				
				# Get CRI display value
				if tape_offering.cri:
					cri_doc = frappe.db.get_value(
						"ilL-Attribute-CRI",
						tape_offering.cri,
						["cri_name", "code"],
						as_dict=True,
					)
					if cri_doc:
						details["cri"] = cri_doc.cri_name or cri_doc.code or tape_offering.cri
				
				# Get fixture input voltage from tape spec
				if tape_offering.tape_spec:
					tape_spec_voltage = frappe.db.get_value(
						"ilL-Spec-LED Tape",
						tape_offering.tape_spec,
						"input_voltage",
					)
					if tape_spec_voltage:
						details["fixture_input_voltage"] = tape_spec_voltage

				# Get output level numeric value for calculation
				if tape_offering.output_level:
					output_level_doc = frappe.db.get_value(
						"ilL-Attribute-Output Level",
						tape_offering.output_level,
						["output_level_name", "value"],
						as_dict=True,
					)
					if output_level_doc:
						details["output_level"] = output_level_doc.output_level_name
						# Calculate estimated delivered output (output_level * lens_transmission)
						if output_level_doc.value:
							delivered = (output_level_doc.value * lens_transmission) / 100
							details["estimated_delivered_output"] = round(delivered, 1)

		# Get driver/power supply info from drivers child table
		if cf.drivers:
			driver_items = []
			driver_input_voltages = []
			total_driver_qty = 0
			for driver_alloc in cf.drivers:
				if driver_alloc.driver_item:
					# driver_alloc.driver_item is the Item code
					# Get item_name from Item doctype
					item_name = frappe.db.get_value("Item", driver_alloc.driver_item, "item_name")

					# Find the ilL-Spec-Driver linked to this Item
					driver_spec = frappe.db.get_value(
						"ilL-Spec-Driver",
						{"item": driver_alloc.driver_item},
						["input_voltage", "max_wattage"],
						as_dict=True,
					)

					# Build driver display string with part number
					driver_qty = driver_alloc.driver_qty or 1
					total_driver_qty += driver_qty
					display_name = item_name or driver_alloc.driver_item
					if driver_qty > 1:
						driver_items.append(f"{display_name} x{driver_qty}")
					else:
						driver_items.append(display_name)

					# Get input voltage from driver spec
					if driver_spec and driver_spec.input_voltage:
						driver_input_voltages.append(driver_spec.input_voltage)

			if driver_items:
				details["power_supply"] = ", ".join(driver_items)
				details["power_supply_qty"] = total_driver_qty
			if driver_input_voltages:
				# Remove duplicates and join
				unique_voltages = list(dict.fromkeys(driver_input_voltages))
				details["driver_input_voltage"] = ", ".join(unique_voltages)

		return details
	except Exception:
		return {}
