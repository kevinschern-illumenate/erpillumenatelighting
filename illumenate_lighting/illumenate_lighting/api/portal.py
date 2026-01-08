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
	1. The user's own company (Customer linked via their Contact)
	2. Customers that were created by contacts at the user's company

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
			line.model_number = line_data.get("model_number")

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

		# Get item code from configured fixture if available
		configured_fixture = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_id)
		if configured_fixture.configured_item:
			line.ill_item_code = configured_fixture.configured_item

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

	# Validate the chosen customer is in the allowed list for this user
	allowed_result = get_allowed_customers_for_project()
	allowed_customer_names = [c["value"] for c in allowed_result.get("allowed_customers", [])]

	chosen_customer = project_data.get("customer")
	if chosen_customer not in allowed_customer_names:
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
