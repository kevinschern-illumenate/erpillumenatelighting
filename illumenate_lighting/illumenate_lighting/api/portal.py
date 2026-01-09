# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal API

This module provides API endpoints for the portal pages to interact with
the system. These endpoints are whitelisted for portal users.
"""

import json
from typing import Union

import frappe
from frappe import _


@frappe.whitelist()
def get_allowed_customers_for_project() -> dict:
	"""
	Get customers that the current user can create projects for.

	Returns customers that:
	1. System Manager: All customers
	2. The user's own company (Customer linked via their Contact)
	3. Customers that were created by contacts at the user's company

	Returns:
		dict: {
			"success": True/False,
			"user_customer": str or None,
			"allowed_customers": [{"value": name, "label": customer_name}]
		}
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
	)

	# System Manager can access all customers
	is_system_manager = "System Manager" in frappe.get_roles(frappe.session.user)
	if is_system_manager:
		all_customers = frappe.get_all(
			"Customer",
			fields=["name", "customer_name"],
			order_by="customer_name asc",
		)
		allowed_customers = [
			{"value": c.name, "label": c.customer_name or c.name}
			for c in all_customers
		]
		return {
			"success": True,
			"user_customer": None,
			"allowed_customers": allowed_customers,
		}

	user_customer = _get_user_customer(frappe.session.user)

	if not user_customer:
		return {
			"success": True,
			"user_customer": None,
			"allowed_customers": [],
		}

	# Get all contacts linked to the user's company (Customer)
	company_contacts = frappe.db.sql("""
		SELECT DISTINCT c.name as contact_name, c.user
		FROM `tabContact` c
		INNER JOIN `tabDynamic Link` dl ON dl.parent = c.name
			AND dl.parenttype = 'Contact'
			AND dl.link_doctype = 'Customer'
			AND dl.link_name = %(user_customer)s
	""", {"user_customer": user_customer}, as_dict=True)

	contact_names = [c.contact_name for c in company_contacts]

	# Get customers that were created by users at this company
	# A customer is considered "created by the company" if:
	# 1. The owner is a user linked to a contact at the company, OR
	# 2. There's a contact at the company linked to that customer
	allowed_customer_names = set()
	allowed_customer_names.add(user_customer)  # Always include user's own company

	if contact_names:
		# Get customers linked to contacts at the user's company
		linked_customers = frappe.db.sql("""
			SELECT DISTINCT dl.link_name as customer_name
			FROM `tabDynamic Link` dl
			WHERE dl.parenttype = 'Contact'
				AND dl.link_doctype = 'Customer'
				AND dl.parent IN (
					SELECT c.name FROM `tabContact` c
					INNER JOIN `tabDynamic Link` dl2 ON dl2.parent = c.name
						AND dl2.parenttype = 'Contact'
						AND dl2.link_doctype = 'Customer'
						AND dl2.link_name = %(user_customer)s
				)
		""", {"user_customer": user_customer}, as_dict=True)

		for row in linked_customers:
			allowed_customer_names.add(row.customer_name)

		# Also get customers created by users at this company
		company_users = [c.user for c in company_contacts if c.user]
		if company_users:
			created_customers = frappe.get_all(
				"Customer",
				filters={"owner": ["in", company_users]},
				pluck="name",
			)
			for cust in created_customers:
				allowed_customer_names.add(cust)

	# Build the response with customer details
	allowed_customers = []
	for cust_name in allowed_customer_names:
		customer_name_display = frappe.db.get_value("Customer", cust_name, "customer_name")
		allowed_customers.append({
			"value": cust_name,
			"label": customer_name_display or cust_name,
		})

	# Sort by label
	allowed_customers.sort(key=lambda x: x["label"])

	return {
		"success": True,
		"user_customer": user_customer,
		"allowed_customers": allowed_customers,
	}


@frappe.whitelist()
def get_template_options(template_code: str) -> dict:
	"""
	Get allowed options for a fixture template.

	Args:
		template_code: Code of the fixture template

	Returns:
		dict: Options available for each attribute type
	"""
	if not frappe.db.exists("ilL-Fixture-Template", template_code):
		return {}

	template = frappe.get_doc("ilL-Fixture-Template", template_code)

	options = {
		"finish": [],
		"lens_appearance": [],
		"mounting_method": [],
		"endcap_style": [],
		"power_feed_type": [],
		"environment_rating": [],
		"tape_offerings": [],
		"endcap_colors": [],
	}

	# Parse allowed options from template
	for row in template.get("allowed_options", []):
		if not row.is_active:
			continue

		option_type = row.option_type
		if option_type == "Finish" and row.finish:
			options["finish"].append({"value": row.finish, "label": row.finish})
		elif option_type == "Lens Appearance" and row.lens_appearance:
			options["lens_appearance"].append({"value": row.lens_appearance, "label": row.lens_appearance})
		elif option_type == "Mounting Method" and row.mounting_method:
			options["mounting_method"].append({"value": row.mounting_method, "label": row.mounting_method})
		elif option_type == "Endcap Style" and row.endcap_style:
			options["endcap_style"].append({"value": row.endcap_style, "label": row.endcap_style})
		elif option_type == "Power Feed Type" and row.power_feed_type:
			options["power_feed_type"].append({"value": row.power_feed_type, "label": row.power_feed_type})
		elif option_type == "Environment Rating" and row.environment_rating:
			options["environment_rating"].append({"value": row.environment_rating, "label": row.environment_rating})

	# Get tape offerings from template
	for row in template.get("allowed_tape_offerings", []):
		if row.tape_offering:
			options["tape_offerings"].append({"value": row.tape_offering, "label": row.tape_offering})

	# Get all endcap colors (not template-specific in MVP)
	endcap_colors = frappe.get_all(
		"ilL-Attribute-Endcap Color",
		fields=["code", "display_name"],
	)
	for color in endcap_colors:
		options["endcap_colors"].append({
			"value": color.code,
			"label": color.display_name or color.code,
		})

	return options


@frappe.whitelist()
def add_schedule_line(schedule_name: str, line_data: Union[str, dict]) -> dict:
	"""
	Add a new line to a fixture schedule.

	Args:
		schedule_name: Name of the schedule
		line_data: Dict with line fields (line_id, qty, location, manufacturer_type, etc.)

	Returns:
		dict: {"success": True/False, "error": "message if error"}
	"""
	# Validate schedule exists
	if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		return {"success": False, "error": "Schedule not found"}

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		has_permission,
	)

	if not has_permission(schedule, "write", frappe.session.user):
		return {"success": False, "error": "You don't have permission to edit this schedule"}

	# Validate status
	if schedule.status not in ["DRAFT", "READY"]:
		return {"success": False, "error": "Cannot add lines to a schedule in this status"}

	# Parse line_data if it's a string (from form submission)
	if isinstance(line_data, str):
		line_data = json.loads(line_data)

	# Add the line
	try:
		line = schedule.append("lines", {})
		line.line_id = line_data.get("line_id")
		line.qty = int(line_data.get("qty", 1))
		line.location = line_data.get("location")
		line.manufacturer_type = line_data.get("manufacturer_type", "ILLUMENATE")
		line.notes = line_data.get("notes")

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
			line.spec_sheet = line_data.get("spec_sheet")

		schedule.save()
		return {"success": True, "line_idx": len(schedule.lines) - 1}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def delete_schedule_line(schedule_name: str, line_idx: int) -> dict:
	"""
	Delete a line from a fixture schedule.

	Args:
		schedule_name: Name of the schedule
		line_idx: Index of the line to delete

	Returns:
		dict: {"success": True/False, "error": "message if error"}
	"""
	# Validate schedule exists
	if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		return {"success": False, "error": "Schedule not found"}

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		has_permission,
	)

	if not has_permission(schedule, "write", frappe.session.user):
		return {"success": False, "error": "You don't have permission to edit this schedule"}

	# Validate status
	if schedule.status not in ["DRAFT", "READY"]:
		return {"success": False, "error": "Cannot delete lines from a schedule in this status"}

	line_idx = int(line_idx)
	if line_idx < 0 or line_idx >= len(schedule.lines):
		return {"success": False, "error": "Invalid line index"}

	try:
		# Remove the line
		schedule.lines.pop(line_idx)
		schedule.save()
		return {"success": True}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def duplicate_schedule_line(schedule_name: str, line_idx: int) -> dict:
	"""
	Duplicate a line in a fixture schedule.

	Args:
		schedule_name: Name of the schedule
		line_idx: Index of the line to duplicate

	Returns:
		dict: {"success": True/False, "new_line_idx": index, "error": "message if error"}
	"""
	# Validate schedule exists
	if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		return {"success": False, "error": "Schedule not found"}

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		has_permission,
	)

	if not has_permission(schedule, "write", frappe.session.user):
		return {"success": False, "error": "You don't have permission to edit this schedule"}

	# Validate status
	if schedule.status not in ["DRAFT", "READY"]:
		return {"success": False, "error": "Cannot duplicate lines in a schedule in this status"}

	line_idx = int(line_idx)
	if line_idx < 0 or line_idx >= len(schedule.lines):
		return {"success": False, "error": "Invalid line index"}

	try:
		# Call the DocType method to duplicate the line
		new_idx = schedule.duplicate_line(line_idx)
		return {"success": True, "new_line_idx": new_idx}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def update_schedule_line(schedule_name: str, line_idx: int, line_data: Union[str, dict]) -> dict:
	"""
	Update an existing line in a fixture schedule.

	Args:
		schedule_name: Name of the schedule
		line_idx: Index of the line to update
		line_data: Dict with line fields to update (line_id, qty, location, notes, etc.)

	Returns:
		dict: {"success": True/False, "error": "message if error"}
	"""
	# Validate schedule exists
	if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		return {"success": False, "error": "Schedule not found"}

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		has_permission,
	)

	if not has_permission(schedule, "write", frappe.session.user):
		return {"success": False, "error": "You don't have permission to edit this schedule"}

	# Validate status
	if schedule.status not in ["DRAFT", "READY"]:
		return {"success": False, "error": "Cannot edit lines in a schedule in this status"}

	# Parse line_data if it's a string (from form submission)
	if isinstance(line_data, str):
		line_data = json.loads(line_data)

	line_idx = int(line_idx)
	if line_idx < 0 or line_idx >= len(schedule.lines):
		return {"success": False, "error": "Invalid line index"}

	try:
		line = schedule.lines[line_idx]

		# Update allowed fields
		if "line_id" in line_data:
			line.line_id = line_data.get("line_id")
		if "qty" in line_data:
			line.qty = int(line_data.get("qty", 1))
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
			if "spec_sheet" in line_data:
				line.spec_sheet = line_data.get("spec_sheet")

		schedule.save()
		return {"success": True}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_configured_fixture_details(configured_fixture_id: str) -> dict:
	"""
	Get detailed information about a configured fixture for portal display.

	Fetches computed values from linked doctypes including:
	- Part Number
	- Estimated Delivered Output (LED tape output * lens transmission)
	- CCT (from LED tape)
	- Lamp/LED Package
	- Power Supply/Driver info
	- Finish
	- Input Voltage

	Args:
		configured_fixture_id: ID of the ilL-Configured-Fixture

	Returns:
		dict: {"success": True/False, "details": {...}, "error": "message if error"}
	"""
	if not frappe.db.exists("ilL-Configured-Fixture", configured_fixture_id):
		return {"success": False, "error": "Configured fixture not found"}

	try:
		cf = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_id)

		details = {
			"config_hash": cf.config_hash,
			"part_number": cf.configured_item or cf.config_hash,
			"finish": None,
			"lens_appearance": None,
			"cct": None,
			"led_package": None,
			"output_level": None,
			"estimated_delivered_output": None,
			"power_supply": None,
			"driver_input_voltage": None,
			"manufacturable_length_mm": cf.manufacturable_overall_length_mm,
			"total_watts": cf.total_watts,
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

		# Get tape offering details (CCT, LED Package, Output Level)
		if cf.tape_offering:
			tape_offering = frappe.db.get_value(
				"ilL-Rel-Tape Offering",
				cf.tape_offering,
				["cct", "led_package", "output_level", "tape_spec"],
				as_dict=True,
			)
			if tape_offering:
				details["cct"] = tape_offering.cct
				details["led_package"] = tape_offering.led_package

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
			for driver_alloc in cf.drivers:
				if driver_alloc.driver_item:
					# Get driver spec details
					driver_spec = frappe.db.get_value(
						"ilL-Spec-Driver",
						driver_alloc.driver_item,
						["item", "input_voltage", "max_wattage"],
						as_dict=True,
					)
					if driver_spec:
						item_name = frappe.db.get_value("Item", driver_alloc.driver_item, "item_name")
						if driver_alloc.driver_qty > 1:
							driver_items.append(f"{item_name} x{driver_alloc.driver_qty}")
						else:
							driver_items.append(item_name or driver_alloc.driver_item)
						if driver_spec.input_voltage:
							driver_input_voltages.append(driver_spec.input_voltage)

			if driver_items:
				details["power_supply"] = ", ".join(driver_items)
			if driver_input_voltages:
				# Remove duplicates and join
				unique_voltages = list(dict.fromkeys(driver_input_voltages))
				details["driver_input_voltage"] = ", ".join(unique_voltages)

		return {"success": True, "details": details}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def save_configured_fixture_to_schedule(
	schedule_name: str,
	configured_fixture_id: str,
	manufacturable_length_mm: int,
	line_idx: int = None,
) -> dict:
	"""
	Save a configured fixture to a schedule line.

	Args:
		schedule_name: Name of the schedule
		configured_fixture_id: ID of the ilL-Configured-Fixture
		manufacturable_length_mm: Manufacturable length to cache
		line_idx: Optional index of existing line to update (creates new if not provided)

	Returns:
		dict: {"success": True/False, "error": "message if error", "line_idx": index}
	"""
	# Validate schedule exists
	if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		return {"success": False, "error": "Schedule not found"}

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		has_permission,
	)

	if not has_permission(schedule, "write", frappe.session.user):
		return {"success": False, "error": "You don't have permission to edit this schedule"}

	# Validate configured fixture exists
	if not frappe.db.exists("ilL-Configured-Fixture", configured_fixture_id):
		return {"success": False, "error": "Configured fixture not found"}

	try:
		if line_idx is not None:
			line_idx = int(line_idx)
			if line_idx < 0 or line_idx >= len(schedule.lines):
				return {"success": False, "error": "Invalid line index"}
			line = schedule.lines[line_idx]
		else:
			# Create new line
			line = schedule.append("lines", {})
			line.manufacturer_type = "ILLUMENATE"
			line.qty = 1

		# Update line with configured fixture
		line.configured_fixture = configured_fixture_id
		line.manufacturable_length_mm = int(manufacturable_length_mm)

		# Get configured fixture document
		configured_fixture = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_id)

		# Get or create the configured item for this fixture
		if configured_fixture.configured_item:
			line.ill_item_code = configured_fixture.configured_item
		else:
			# Auto-create the configured item for this fixture
			from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
				_create_or_get_configured_item,
				_update_fixture_links,
			)

			item_result = _create_or_get_configured_item(configured_fixture, skip_if_exists=True)
			if item_result.get("success") and item_result.get("item_code"):
				line.ill_item_code = item_result["item_code"]
				# Update the fixture with the new item code
				_update_fixture_links(
					configured_fixture,
					item_code=item_result["item_code"],
					bom_name=None,
					work_order_name=None,
				)

		schedule.save()
		return {"success": True, "line_idx": len(schedule.lines) - 1 if line_idx is None else line_idx}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def create_project(project_data: Union[str, dict]) -> dict:
	"""
	Create a new ilL-Project.

	Args:
		project_data: Dict with project fields (project_name, customer, is_private, etc.)

	Returns:
		dict: {"success": True/False, "project_name": name, "error": "message if error"}
	"""
	# Parse project_data if it's a string
	if isinstance(project_data, str):
		project_data = json.loads(project_data)

	# Get user's customer
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
	)

	user_customer = _get_user_customer(frappe.session.user)

	if not project_data.get("customer"):
		return {"success": False, "error": "Customer is required"}

	# System Manager can create projects for any customer
	is_system_manager = "System Manager" in frappe.get_roles(frappe.session.user)

	# Validate the chosen customer is in the allowed list for this user
	allowed_result = get_allowed_customers_for_project()
	allowed_customer_names = [c["value"] for c in allowed_result.get("allowed_customers", [])]

	chosen_customer = project_data.get("customer")

	# System Manager bypass: allow any valid customer
	if is_system_manager and frappe.db.exists("Customer", chosen_customer):
		pass  # Allow the chosen customer
	elif chosen_customer not in allowed_customer_names:
		# If user doesn't have access to this customer, use their own company
		if user_customer:
			chosen_customer = user_customer
		else:
			return {"success": False, "error": "You don't have permission to create projects for this customer"}

	try:
		project = frappe.new_doc("ilL-Project")
		project.project_name = project_data.get("project_name")
		project.customer = chosen_customer
		project.description = project_data.get("description")
		project.is_private = project_data.get("is_private", 0)
		# owner_customer is set automatically in before_insert

		project.insert()
		return {"success": True, "project_name": project.name}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def create_schedule(schedule_data: Union[str, dict]) -> dict:
	"""
	Create a new ilL-Project-Fixture-Schedule.

	Args:
		schedule_data: Dict with schedule fields (schedule_name, ill_project, etc.)

	Returns:
		dict: {"success": True/False, "schedule_name": name, "error": "message if error"}
	"""
	# Parse schedule_data if it's a string
	if isinstance(schedule_data, str):
		schedule_data = json.loads(schedule_data)

	# Validate project exists and user has access
	project_name = schedule_data.get("ill_project")
	if not project_name:
		return {"success": False, "error": "Project is required"}

	if not frappe.db.exists("ilL-Project", project_name):
		return {"success": False, "error": "Project not found"}

	project = frappe.get_doc("ilL-Project", project_name)

	# Check permission on project
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		has_permission,
	)

	if not has_permission(project, "write", frappe.session.user):
		return {"success": False, "error": "You don't have permission to create schedules in this project"}

	try:
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = schedule_data.get("schedule_name")
		schedule.ill_project = project_name
		schedule.customer = project.customer  # Auto-sync from project
		schedule.notes = schedule_data.get("notes")
		schedule.inherits_project_privacy = 1  # Default to inherit

		schedule.insert()
		return {"success": True, "schedule_name": schedule.name}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def update_project_collaborators(project_name: str, collaborators: Union[str, list]) -> dict:
	"""
	Update collaborators for a project.

	Args:
		project_name: Name of the project
		collaborators: List of collaborator dicts [{user, access_level, is_active}]

	Returns:
		dict: {"success": True/False, "error": "message if error"}
	"""
	if not frappe.db.exists("ilL-Project", project_name):
		return {"success": False, "error": "Project not found"}

	project = frappe.get_doc("ilL-Project", project_name)

	# Only owner can update collaborators
	if project.owner != frappe.session.user and "System Manager" not in frappe.get_roles(frappe.session.user):
		return {"success": False, "error": "Only the project owner can manage collaborators"}

	# Parse collaborators if string
	if isinstance(collaborators, str):
		collaborators = json.loads(collaborators)

	try:
		# Clear existing collaborators
		project.collaborators = []

		# Add new collaborators
		for collab in collaborators:
			project.append("collaborators", {
				"user": collab.get("user"),
				"access_level": collab.get("access_level", "VIEW"),
				"is_active": collab.get("is_active", 1),
			})

		project.save()
		return {"success": True}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def toggle_project_privacy(project_name: str, is_private: int) -> dict:
	"""
	Toggle privacy setting for a project.

	Args:
		project_name: Name of the project
		is_private: 1 for private, 0 for company-visible

	Returns:
		dict: {"success": True/False, "error": "message if error"}
	"""
	if not frappe.db.exists("ilL-Project", project_name):
		return {"success": False, "error": "Project not found"}

	project = frappe.get_doc("ilL-Project", project_name)

	# Only owner can change privacy
	if project.owner != frappe.session.user and "System Manager" not in frappe.get_roles(frappe.session.user):
		return {"success": False, "error": "Only the project owner can change privacy settings"}

	try:
		project.is_private = int(is_private)
		project.save()
		return {"success": True}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def request_schedule_quote(schedule_name: str) -> dict:
	"""
	Request a quote for a fixture schedule.

	Args:
		schedule_name: Name of the schedule

	Returns:
		dict: {"success": True/False, "error": "message if error"}
	"""
	if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		return {"success": False, "error": "Schedule not found"}

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		has_permission,
	)

	if not has_permission(schedule, "write", frappe.session.user):
		return {"success": False, "error": "You don't have permission to request a quote for this schedule"}

	try:
		schedule.request_quote()
		return {"success": True}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def update_schedule_status(schedule_name: str, new_status: str) -> dict:
	"""
	Update the status of a fixture schedule.

	Status transitions allowed:
	- DRAFT -> READY (by anyone with write permission)
	- READY -> DRAFT (by anyone with write permission)
	- READY -> QUOTED (by internal/dealer users only)
	- QUOTED -> READY (by internal/dealer users only - e.g., to revise quote)
	- ORDERED and CLOSED statuses cannot be set via portal

	Args:
		schedule_name: Name of the schedule
		new_status: New status to set (DRAFT, READY, QUOTED)

	Returns:
		dict: {"success": True/False, "error": "message if error"}
	"""
	if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		return {"success": False, "error": "Schedule not found"}

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		has_permission,
		_is_dealer_user,
		_is_internal_user,
	)

	if not has_permission(schedule, "write", frappe.session.user):
		return {"success": False, "error": "You don't have permission to update this schedule"}

	# Validate status value
	valid_statuses = ["DRAFT", "READY", "QUOTED"]
	if new_status not in valid_statuses:
		return {"success": False, "error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}

	current_status = schedule.status
	is_privileged = _is_dealer_user(frappe.session.user) or _is_internal_user(frappe.session.user)

	# Define allowed transitions
	allowed_transitions = {
		"DRAFT": ["READY"],
		"READY": ["DRAFT", "QUOTED"] if is_privileged else ["DRAFT"],
		"QUOTED": ["READY"] if is_privileged else [],
	}

	# Check if transition is allowed
	if new_status == current_status:
		return {"success": True}  # No change needed

	if current_status not in allowed_transitions:
		return {"success": False, "error": f"Cannot change status from {current_status}"}

	if new_status not in allowed_transitions.get(current_status, []):
		return {"success": False, "error": f"Cannot change status from {current_status} to {new_status}"}

	try:
		schedule.db_set("status", new_status)
		frappe.db.commit()
		return {"success": True, "new_status": new_status}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def create_schedule_sales_order(schedule_name: str) -> dict:
	"""
	Create a Sales Order from a fixture schedule.

	Args:
		schedule_name: Name of the schedule

	Returns:
		dict: {"success": True/False, "sales_order": "SO name", "error": "message if error"}
	"""
	if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		return {"success": False, "error": "Schedule not found"}

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		has_permission,
	)

	if not has_permission(schedule, "write", frappe.session.user):
		return {"success": False, "error": "You don't have permission to create a Sales Order for this schedule"}

	try:
		sales_order = schedule.create_sales_order()
		return {"success": True, "sales_order": sales_order}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def create_customer(customer_data: Union[str, dict]) -> dict:
	"""
	Create a new Customer from the portal.

	Portal users can create customers that they will then be linked to.

	Args:
		customer_data: Dict with customer fields (customer_name, customer_type, territory, etc.)

	Returns:
		dict: {"success": True/False, "customer_name": name, "error": "message if error"}
	"""
	# Parse customer_data if it's a string
	if isinstance(customer_data, str):
		customer_data = json.loads(customer_data)

	if not customer_data.get("customer_name"):
		return {"success": False, "error": "Customer name is required"}

	# Check if customer already exists
	if frappe.db.exists("Customer", customer_data.get("customer_name")):
		return {"success": False, "error": "A customer with this name already exists"}

	try:
		customer = frappe.new_doc("Customer")
		customer.customer_name = customer_data.get("customer_name")
		customer.customer_type = customer_data.get("customer_type", "Company")
		customer.territory = customer_data.get("territory", frappe.db.get_single_value("Selling Settings", "territory") or "All Territories")
		customer.customer_group = customer_data.get("customer_group", frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups")

		# Set default currency if provided
		if customer_data.get("default_currency"):
			customer.default_currency = customer_data.get("default_currency")

		customer.insert(ignore_permissions=True)

		# Link the current user to this customer via Contact
		user = frappe.session.user
		user_doc = frappe.get_doc("User", user)

		# Check if user already has a Contact, if not create one
		existing_contact = frappe.db.get_value(
			"Dynamic Link",
			{"link_doctype": "User", "link_name": user, "parenttype": "Contact"},
			"parent"
		)

		if existing_contact:
			# Add the new customer link to existing contact
			contact = frappe.get_doc("Contact", existing_contact)
			contact.append("links", {
				"link_doctype": "Customer",
				"link_name": customer.name
			})
			contact.save(ignore_permissions=True)
		else:
			# Create a new contact for the user
			contact = frappe.new_doc("Contact")
			contact.first_name = user_doc.first_name or user_doc.name.split("@")[0]
			contact.last_name = user_doc.last_name or ""
			contact.email_id = user_doc.email
			contact.user = user

			# Link to the new customer
			contact.append("links", {
				"link_doctype": "Customer",
				"link_name": customer.name
			})
			contact.insert(ignore_permissions=True)

		return {"success": True, "customer_name": customer.name}
	except Exception as e:
		frappe.log_error(f"Error creating customer: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def create_drawing_request(request_data: Union[str, dict]) -> dict:
	"""
	Create a new drawing request from the portal.

	Args:
		request_data: Dict with request fields (drawing_type, project, description, priority, etc.)

	Returns:
		dict: {"success": True/False, "request_name": name, "error": "message if error"}
	"""
	# Parse request_data if it's a string
	if isinstance(request_data, str):
		request_data = json.loads(request_data)

	if not request_data.get("description"):
		return {"success": False, "error": "Description is required"}

	try:
		# Check if Document Request doctype exists, if not create the request as an Issue
		if frappe.db.table_exists("tabilL-Document-Request"):
			# Map drawing_type to a request type
			drawing_type = request_data.get("drawing_type", "shop_drawing")
			request_type = _get_or_create_request_type(drawing_type)

			doc = frappe.new_doc("ilL-Document-Request")
			doc.request_type = request_type
			doc.project = request_data.get("project") if request_data.get("project") != "_custom" else None
			doc.fixture_or_product_text = request_data.get("fixture_reference") or request_data.get("custom_reference")
			doc.description = request_data.get("description")
			# Map priority values
			priority_map = {"low": "Normal", "normal": "Normal", "high": "High", "rush": "Rush"}
			doc.priority = priority_map.get(request_data.get("priority", "normal").lower(), "Normal")
			doc.status = "Submitted"
			doc.requester_user = frappe.session.user
			doc.created_from_portal = 1
			doc.insert(ignore_permissions=True)
			frappe.db.commit()
			return {"success": True, "request_name": doc.name}
		else:
			# Fallback: Create as an Issue with drawing request info
			doc = frappe.new_doc("Issue")
			drawing_type = request_data.get("drawing_type", "shop_drawing")
			doc.subject = f"Drawing Request: {drawing_type.replace('_', ' ').title()}"
			doc.description = f"""
**Drawing Type:** {drawing_type.replace('_', ' ').title()}
**Project:** {request_data.get('project') or request_data.get('custom_reference') or 'N/A'}
**Fixture Reference:** {request_data.get('fixture_reference') or 'N/A'}
**Priority:** {request_data.get('priority', 'normal').title()}

**Description:**
{request_data.get('description')}
"""
			doc.raised_by = frappe.session.user
			doc.insert(ignore_permissions=True)
			frappe.db.commit()
			return {"success": True, "request_name": doc.name}
	except Exception as e:
		frappe.log_error(f"Error creating drawing request: {str(e)}")
		return {"success": False, "error": str(e)}


def _get_or_create_request_type(drawing_type: str) -> str:
	"""
	Get or create a request type based on drawing_type.

	Args:
		drawing_type: The type of drawing (shop_drawing, spec_sheet, etc.)

	Returns:
		str: The name of the request type
	"""
	type_name_map = {
		"shop_drawing": "Shop Drawing",
		"spec_sheet": "Spec Sheet",
		"installation": "Installation Guide",
		"ies_file": "IES File",
	}
	type_name = type_name_map.get(drawing_type, drawing_type.replace("_", " ").title())

	# Check if the request type exists
	if frappe.db.exists("ilL-Request-Type", type_name):
		return type_name

	# Create the request type if it doesn't exist
	request_type_doc = frappe.new_doc("ilL-Request-Type")
	request_type_doc.type_name = type_name
	request_type_doc.category = "Drawing"
	request_type_doc.is_active = 1
	request_type_doc.portal_label = type_name
	request_type_doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return type_name


@frappe.whitelist()
def create_support_ticket(ticket_data: Union[str, dict]) -> dict:
	"""
	Create a support ticket from the portal.

	Args:
		ticket_data: Dict with ticket fields (category, subject, description, order, etc.)

	Returns:
		dict: {"success": True/False, "ticket_name": name, "error": "message if error"}
	"""
	# Parse ticket_data if it's a string
	if isinstance(ticket_data, str):
		ticket_data = json.loads(ticket_data)

	if not ticket_data.get("subject"):
		return {"success": False, "error": "Subject is required"}

	if not ticket_data.get("description"):
		return {"success": False, "error": "Description is required"}

	try:
		doc = frappe.new_doc("Issue")
		doc.subject = ticket_data.get("subject")
		doc.description = f"""
**Category:** {ticket_data.get('category', 'Other').title()}
**Related Order:** {ticket_data.get('order') or 'N/A'}

**Description:**
{ticket_data.get('description')}
"""
		doc.raised_by = frappe.session.user

		# Try to set priority if the field exists
		category_priority_map = {
			"order": "Medium",
			"technical": "Medium",
			"returns": "High",
			"billing": "High",
			"other": "Low",
		}
		doc.priority = category_priority_map.get(ticket_data.get("category"), "Medium")

		doc.insert(ignore_permissions=True)
		return {"success": True, "ticket_name": doc.name}
	except Exception as e:
		frappe.log_error(f"Error creating support ticket: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def update_user_profile(profile_data: Union[str, dict]) -> dict:
	"""
	Update the current user's profile information.

	Args:
		profile_data: Dict with profile fields (first_name, last_name, phone, job_title)

	Returns:
		dict: {"success": True/False, "error": "message if error"}
	"""
	# Parse profile_data if it's a string
	if isinstance(profile_data, str):
		profile_data = json.loads(profile_data)

	try:
		user = frappe.get_doc("User", frappe.session.user)

		if "first_name" in profile_data:
			user.first_name = profile_data.get("first_name")
		if "last_name" in profile_data:
			user.last_name = profile_data.get("last_name")
		if "phone" in profile_data:
			user.phone = profile_data.get("phone")

		user.save()
		return {"success": True}
	except Exception as e:
		frappe.log_error(f"Error updating user profile: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def save_notification_preferences(preferences: Union[str, dict]) -> dict:
	"""
	Save notification preferences for the current user.

	Args:
		preferences: Dict with notification preference booleans

	Returns:
		dict: {"success": True/False, "error": "message if error"}
	"""
	# Parse preferences if it's a string
	if isinstance(preferences, str):
		preferences = json.loads(preferences)

	try:
		# Store preferences in user's custom fields or a settings doctype
		# For now, we'll store as a comment on the user for MVP
		user = frappe.session.user

		# Check if there's a custom doctype for notification prefs
		# If not, store in User's bio field or similar as JSON
		# This is a placeholder implementation
		frappe.cache().hset("portal_notification_prefs", user, json.dumps(preferences))

		return {"success": True}
	except Exception as e:
		frappe.log_error(f"Error saving notification preferences: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_order_details(order_name: str) -> dict:
	"""
	Get detailed information about a sales order for the portal.

	Args:
		order_name: Name of the Sales Order

	Returns:
		dict: Order details including items and status
	"""
	if not frappe.db.exists("Sales Order", order_name):
		return {"success": False, "error": "Order not found"}

	# Verify user has access to this order's customer
	order = frappe.get_doc("Sales Order", order_name)

	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
	)
	user_customer = _get_user_customer(frappe.session.user)

	# Check if System Manager or customer matches
	is_system_manager = "System Manager" in frappe.get_roles(frappe.session.user)
	if not is_system_manager and order.customer != user_customer:
		return {"success": False, "error": "You don't have permission to view this order"}

	# Get order items
	items = []
	for item in order.items:
		items.append({
			"item_code": item.item_code,
			"item_name": item.item_name,
			"qty": item.qty,
			"rate": item.rate,
			"amount": item.amount,
			"delivery_date": item.delivery_date,
			"configured_fixture": item.get("ill_configured_fixture"),
		})

	# Get delivery notes linked to this order
	delivery_notes = frappe.get_all(
		"Delivery Note Item",
		filters={"against_sales_order": order_name, "docstatus": 1},
		fields=["parent"],
		distinct=True,
	)
	deliveries = []
	for dn in delivery_notes:
		dn_doc = frappe.get_doc("Delivery Note", dn.parent)
		deliveries.append({
			"name": dn_doc.name,
			"posting_date": dn_doc.posting_date,
			"status": dn_doc.status,
			"tracking_no": dn_doc.get("tracking_no"),
			"transporter": dn_doc.get("transporter_name"),
		})

	return {
		"success": True,
		"order": {
			"name": order.name,
			"transaction_date": order.transaction_date,
			"delivery_date": order.delivery_date,
			"status": order.status,
			"grand_total": order.grand_total,
			"currency": order.currency,
			"customer": order.customer,
			"customer_name": order.customer_name,
			"po_no": order.po_no,
			"per_delivered": order.per_delivered,
			"per_billed": order.per_billed,
		},
		"items": items,
		"deliveries": deliveries,
	}


@frappe.whitelist()
def get_portal_notifications() -> dict:
	"""
	Get notifications and alerts for the current portal user.

	Returns:
		dict: List of notifications
	"""
	notifications = []

	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
	)
	customer = _get_user_customer(frappe.session.user)

	if customer:
		# Check for quotes ready
		quoted_schedules = frappe.db.count(
			"ilL-Project-Fixture-Schedule",
			{"status": "QUOTED"}
		)
		if quoted_schedules > 0:
			notifications.append({
				"type": "quote",
				"title": _("Quotes Ready"),
				"message": _("{0} schedule(s) have quotes ready for review").format(quoted_schedules),
				"link": "/portal/projects",
				"icon": "fa-file-text-o",
				"color": "success",
			})

		# Check for orders ready to ship
		ready_orders = frappe.db.count(
			"Sales Order",
			{"customer": customer, "status": "To Deliver", "docstatus": 1}
		)
		if ready_orders > 0:
			notifications.append({
				"type": "shipping",
				"title": _("Orders Ready to Ship"),
				"message": _("{0} order(s) are ready for shipment").format(ready_orders),
				"link": "/portal/orders",
				"icon": "fa-truck",
				"color": "info",
			})

	return {"success": True, "notifications": notifications}


# =============================================================================
# DEALER-SPECIFIC API FUNCTIONS
# =============================================================================


@frappe.whitelist()
def get_user_role_info() -> dict:
	"""
	Get role information for the current user.

	Returns:
		dict: {
			"is_dealer": bool,
			"is_internal": bool,
			"user_customer": str or None,
			"can_invite_collaborators": bool,
			"can_create_customers": bool,
		}
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
		_is_dealer_user,
		_is_internal_user,
	)

	is_dealer = _is_dealer_user(frappe.session.user)
	is_internal = _is_internal_user(frappe.session.user)
	user_customer = _get_user_customer(frappe.session.user)

	return {
		"success": True,
		"is_dealer": is_dealer,
		"is_internal": is_internal,
		"user_customer": user_customer,
		"can_invite_collaborators": is_dealer or is_internal,
		"can_create_customers": is_dealer or is_internal,
		"can_create_contacts": is_dealer or is_internal,
	}


@frappe.whitelist()
def invite_project_collaborator(
	project_name: str,
	email: str,
	first_name: str = None,
	last_name: str = None,
	access_level: str = "VIEW",
	send_invite: int = 1,
) -> dict:
	"""
	Invite an external collaborator to a specific project.

	Dealers can invite external collaborators. These collaborators:
	- Only have access to the specific project(s) they are invited to
	- Do not have the Dealer role
	- Cannot see other projects or company data

	Args:
		project_name: The project to invite the collaborator to
		email: Email address of the collaborator
		first_name: First name (used if creating new user)
		last_name: Last name (used if creating new user)
		access_level: VIEW or EDIT
		send_invite: 1 to send invitation email, 0 to skip

	Returns:
		dict: {"success": True/False, "user": email, "is_new_user": bool, "error": str}
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
		_is_dealer_user,
		_is_internal_user,
		has_permission as project_has_permission,
	)

	# Check if caller has permission to invite collaborators
	is_dealer = _is_dealer_user(frappe.session.user)
	is_internal = _is_internal_user(frappe.session.user)

	if not is_dealer and not is_internal:
		return {"success": False, "error": "You don't have permission to invite collaborators"}

	# Validate project exists
	if not frappe.db.exists("ilL-Project", project_name):
		return {"success": False, "error": "Project not found"}

	project = frappe.get_doc("ilL-Project", project_name)

	# Check permission on project
	if not project_has_permission(project, "write", frappe.session.user):
		return {"success": False, "error": "You don't have permission to manage this project"}

	# Validate email
	email = email.strip().lower()
	if not frappe.utils.validate_email_address(email):
		return {"success": False, "error": "Invalid email address"}

	# Check if user already exists
	is_new_user = False
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		# Create new user
		is_new_user = True
		try:
			user = frappe.new_doc("User")
			user.email = email
			user.first_name = first_name or email.split("@")[0]
			user.last_name = last_name or ""
			user.send_welcome_email = int(send_invite)
			user.enabled = 1
			# New collaborators get Website User role only (no Dealer role)
			user.append("roles", {"role": "Website User"})
			user.insert(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(f"Error creating user for collaborator: {str(e)}")
			return {"success": False, "error": f"Failed to create user: {str(e)}"}

	# Check if already a collaborator on this project
	existing_collab = None
	for c in project.collaborators or []:
		if c.user == email:
			existing_collab = c
			break

	if existing_collab:
		# Update existing collaborator
		existing_collab.access_level = access_level
		existing_collab.is_active = 1
	else:
		# Add new collaborator
		project.append("collaborators", {
			"user": email,
			"access_level": access_level,
			"is_active": 1,
		})

	try:
		project.save(ignore_permissions=True)
	except Exception as e:
		return {"success": False, "error": f"Failed to add collaborator: {str(e)}"}

	# Send invitation email if requested and user already existed (new users get welcome email)
	if send_invite and not is_new_user:
		_send_collaborator_invite_email(project, user.name, access_level)

	return {
		"success": True,
		"user": email,
		"is_new_user": is_new_user,
		"access_level": access_level,
	}


def _send_collaborator_invite_email(project, user_email: str, access_level: str):
	"""
	Send an email notification to a collaborator about project access.

	Args:
		project: The ilL-Project document
		user_email: Email of the collaborator
		access_level: VIEW or EDIT
	"""
	try:
		project_url = frappe.utils.get_url(f"/portal/projects/{project.name}")
		access_text = "view" if access_level == "VIEW" else "view and edit"

		frappe.sendmail(
			recipients=[user_email],
			subject=_("You've been invited to collaborate on {0}").format(project.project_name),
			message=_("""
<p>Hello,</p>

<p>You have been invited to collaborate on the project <strong>{project_name}</strong>.</p>

<p>You can now {access_text} this project. Click the link below to access it:</p>

<p><a href="{project_url}">{project_url}</a></p>

<p>Best regards,<br>
ilLumenate Lighting Team</p>
""").format(
				project_name=project.project_name,
				access_text=access_text,
				project_url=project_url,
			),
			delayed=False,
		)
	except Exception as e:
		frappe.log_error(f"Failed to send collaborator invite email: {str(e)}")


@frappe.whitelist()
def remove_project_collaborator(project_name: str, user_email: str) -> dict:
	"""
	Remove a collaborator from a project.

	Args:
		project_name: The project name
		user_email: Email of the collaborator to remove

	Returns:
		dict: {"success": True/False, "error": str}
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_is_dealer_user,
		_is_internal_user,
		has_permission as project_has_permission,
	)

	# Check if caller has permission
	is_dealer = _is_dealer_user(frappe.session.user)
	is_internal = _is_internal_user(frappe.session.user)

	if not is_dealer and not is_internal and frappe.session.user != frappe.db.get_value("ilL-Project", project_name, "owner"):
		return {"success": False, "error": "You don't have permission to manage collaborators"}

	if not frappe.db.exists("ilL-Project", project_name):
		return {"success": False, "error": "Project not found"}

	project = frappe.get_doc("ilL-Project", project_name)

	if not project_has_permission(project, "write", frappe.session.user):
		return {"success": False, "error": "You don't have permission to manage this project"}

	# Find and deactivate the collaborator
	found = False
	for c in project.collaborators or []:
		if c.user == user_email:
			c.is_active = 0
			found = True
			break

	if not found:
		return {"success": False, "error": "Collaborator not found on this project"}

	try:
		project.save(ignore_permissions=True)
		return {"success": True}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_company_contacts() -> dict:
	"""
	Get all contacts associated with the dealer's company.

	Dealers can see all contacts linked to their Customer.

	Returns:
		dict: {"success": True, "contacts": [...]}
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
		_is_dealer_user,
		_is_internal_user,
	)

	is_internal = _is_internal_user(frappe.session.user)
	is_dealer = _is_dealer_user(frappe.session.user)

	if is_internal:
		# Internal users see all contacts
		contacts = frappe.get_all(
			"Contact",
			fields=["name", "first_name", "last_name", "email_id", "phone", "user"],
			order_by="first_name asc",
		)
	elif is_dealer:
		# Dealers see contacts linked to their company
		user_customer = _get_user_customer(frappe.session.user)
		if not user_customer:
			return {"success": True, "contacts": []}

		# Get contacts linked to the user's customer
		linked_contact_names = frappe.db.sql("""
			SELECT DISTINCT dl.parent
			FROM `tabDynamic Link` dl
			WHERE dl.parenttype = 'Contact'
				AND dl.link_doctype = 'Customer'
				AND dl.link_name = %(customer)s
		""", {"customer": user_customer}, pluck="parent")

		if not linked_contact_names:
			return {"success": True, "contacts": []}

		contacts = frappe.get_all(
			"Contact",
			filters={"name": ["in", linked_contact_names]},
			fields=["name", "first_name", "last_name", "email_id", "phone", "user"],
			order_by="first_name asc",
		)
	else:
		# Regular portal users only see their own contact
		return {"success": True, "contacts": []}

	return {"success": True, "contacts": contacts}


@frappe.whitelist()
def create_contact(contact_data: Union[str, dict]) -> dict:
	"""
	Create a new contact for the dealer's company.

	Dealers can create contacts that are automatically linked to their Customer.

	Args:
		contact_data: Dict with contact fields (first_name, last_name, email_id, phone, etc.)

	Returns:
		dict: {"success": True/False, "contact_name": name, "error": str}
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
		_is_dealer_user,
		_is_internal_user,
	)

	is_internal = _is_internal_user(frappe.session.user)
	is_dealer = _is_dealer_user(frappe.session.user)

	if not is_dealer and not is_internal:
		return {"success": False, "error": "You don't have permission to create contacts"}

	if isinstance(contact_data, str):
		contact_data = json.loads(contact_data)

	if not contact_data.get("first_name"):
		return {"success": False, "error": "First name is required"}

	user_customer = _get_user_customer(frappe.session.user)

	try:
		contact = frappe.new_doc("Contact")
		contact.first_name = contact_data.get("first_name")
		contact.last_name = contact_data.get("last_name", "")
		contact.email_id = contact_data.get("email_id", "")
		contact.phone = contact_data.get("phone", "")
		contact.company_name = contact_data.get("company_name", "")
		contact.designation = contact_data.get("designation", "")

		# Link to user's customer (for dealers)
		if user_customer and not is_internal:
			contact.append("links", {
				"link_doctype": "Customer",
				"link_name": user_customer,
			})

		# If a specific customer was provided and user is internal, use that
		if is_internal and contact_data.get("customer"):
			contact.append("links", {
				"link_doctype": "Customer",
				"link_name": contact_data.get("customer"),
			})

		contact.insert(ignore_permissions=True)
		return {"success": True, "contact_name": contact.name}
	except Exception as e:
		frappe.log_error(f"Error creating contact: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_company_customers() -> dict:
	"""
	Get customers that the dealer's company has created or is linked to.

	Dealers see customers that:
	1. Were created by users at their company
	2. Have contacts from their company

	Returns:
		dict: {"success": True, "customers": [...]}
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
		_is_dealer_user,
		_is_internal_user,
	)

	is_internal = _is_internal_user(frappe.session.user)
	is_dealer = _is_dealer_user(frappe.session.user)

	if is_internal:
		# Internal users see all customers
		customers = frappe.get_all(
			"Customer",
			fields=["name", "customer_name", "customer_type", "territory"],
			order_by="customer_name asc",
			limit=500,
		)
		return {"success": True, "customers": customers}

	if not is_dealer:
		# Regular portal users only see their own customer
		user_customer = _get_user_customer(frappe.session.user)
		if user_customer:
			customer = frappe.get_doc("Customer", user_customer)
			return {"success": True, "customers": [{
				"name": customer.name,
				"customer_name": customer.customer_name,
				"customer_type": customer.customer_type,
				"territory": customer.territory,
			}]}
		return {"success": True, "customers": []}

	# Dealer: get allowed customers using the existing logic
	result = get_allowed_customers_for_project()
	if not result.get("success"):
		return {"success": True, "customers": []}

	allowed_names = [c["value"] for c in result.get("allowed_customers", [])]
	if not allowed_names:
		return {"success": True, "customers": []}

	customers = frappe.get_all(
		"Customer",
		filters={"name": ["in", allowed_names]},
		fields=["name", "customer_name", "customer_type", "territory"],
		order_by="customer_name asc",
	)

	return {"success": True, "customers": customers}

