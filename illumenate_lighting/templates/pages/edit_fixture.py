# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Edit Fixture Page Controller

This page allows users to edit an existing configured fixture from a schedule line.
It pre-loads the fixture's configuration so users can make modifications,
re-validate, and save changes back to the schedule.
"""

import frappe

no_cache = 1


def get_context(context):
	"""Get context for the edit fixture portal page."""
	if frappe.session.user == "Guest":
		frappe.throw("Please login to edit fixtures", frappe.PermissionError)

	# Required parameters
	schedule_name = frappe.form_dict.get("schedule")
	line_idx = frappe.form_dict.get("line_idx")
	configured_fixture_id = frappe.form_dict.get("fixture")

	if not schedule_name:
		frappe.throw("Schedule is required", frappe.ValidationError)

	if line_idx is None:
		frappe.throw("Line index is required", frappe.ValidationError)

	if not configured_fixture_id:
		frappe.throw("Configured fixture is required", frappe.ValidationError)

	# Validate schedule exists and user has permission
	schedule = None
	can_save = False

	if frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

		# Check permission
		from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
			has_permission,
		)

		if has_permission(schedule, "write", frappe.session.user):
			can_save = True
	else:
		frappe.throw("Schedule not found", frappe.DoesNotExistError)

	# Check schedule status allows editing
	if schedule.status not in ["DRAFT", "READY"]:
		frappe.throw("Cannot edit fixtures in a schedule with status: " + schedule.status)

	# Validate line index
	try:
		line_idx_int = int(line_idx)
	except (ValueError, TypeError):
		frappe.throw("Invalid line index", frappe.ValidationError)

	if line_idx_int < 0 or line_idx_int >= len(schedule.lines):
		frappe.throw("Line index out of range", frappe.ValidationError)

	# Get the line and verify it's an ILLUMENATE fixture
	line = schedule.lines[line_idx_int]
	if line.manufacturer_type != "ILLUMENATE":
		frappe.throw("Can only edit ILLUMENATE fixtures", frappe.ValidationError)

	if line.configured_fixture != configured_fixture_id:
		frappe.throw("Fixture ID does not match the schedule line", frappe.ValidationError)

	# Get the existing fixture configuration
	from illumenate_lighting.illumenate_lighting.api.portal import get_configured_fixture_for_editing

	fixture_config = get_configured_fixture_for_editing(configured_fixture_id)
	if not fixture_config.get("success"):
		frappe.throw(fixture_config.get("error") or "Failed to load fixture configuration")

	# Get available templates
	templates = frappe.get_all(
		"ilL-Fixture-Template",
		filters={"is_active": 1},
		fields=["template_code", "template_name"],
		order_by="template_name asc",
	)

	# Determine if pricing should be shown
	show_pricing = True

	context.schedule = schedule
	context.line_idx = line_idx_int
	context.line = line
	context.configured_fixture_id = configured_fixture_id
	context.can_save = can_save
	context.templates = templates
	context.fixture_config = fixture_config.get("configuration", {})
	context.fixture_details = fixture_config.get("fixture_details", {})
	context.show_pricing = show_pricing
	context.title = "Edit Fixture Configuration"
	context.no_cache = 1

	return context
