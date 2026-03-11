# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Webflow Portal API

Provides API endpoints for the Webflow marketing site to interact with
ERPNext projects, fixture schedules, and pricing. All endpoints verify
user→customer ownership to enforce data isolation.

Endpoints:
- get_projects: Return all ILL Projects for the user's customer
- get_fixture_schedules: Return fixture schedules for a project
- get_line_ids: Return line items for a fixture schedule
- add_fixture_to_schedule: Add or overwrite a fixture line
- get_pricing: Return price for Dealers only
- get_stock_status: Return stock status (public, qty gated to Dealers)
- get_msrp: Return public MSRP pricing
"""

import json

import frappe
from frappe import _


# =============================================================================
# HELPER: Verify user→customer ownership
# =============================================================================


def _get_user_customer_or_fail(user: str) -> str:
	"""
	Get the Customer linked to a user, or raise an error.

	Args:
		user: The user email/name

	Returns:
		str: Customer name

	Raises:
		Returns None if no customer is linked.
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
		_is_internal_user,
	)

	# Internal users can access all data
	if _is_internal_user(user):
		return None  # None signals "no filtering needed"

	return _get_user_customer(user)


def _verify_project_ownership(project_name: str, user: str) -> dict | None:
	"""
	Verify that the user's customer matches the project's customer.

	Returns None on success, or an error dict on failure.
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_is_internal_user,
		_get_user_customer,
	)

	if _is_internal_user(user):
		return None  # Internal users bypass ownership check

	user_customer = _get_user_customer(user)
	if not user_customer:
		return {"success": False, "error": _("No customer linked to your account")}

	if not frappe.db.exists("ilL-Project", project_name):
		return {"success": False, "error": _("Project not found")}

	project_customer = frappe.db.get_value("ilL-Project", project_name, "customer")
	owner_customer = frappe.db.get_value("ilL-Project", project_name, "owner_customer")

	if user_customer not in (project_customer, owner_customer):
		return {"success": False, "error": _("Permission denied")}

	return None


# =============================================================================
# PUBLIC API ENDPOINTS
# =============================================================================


@frappe.whitelist(allow_guest=False)
def get_projects() -> dict:
	"""
	Return all ILL Projects linked to the authenticated user's Customer.

	For internal users (System Manager), returns all projects.
	For portal users, returns only projects linked to their Customer
	(either as the customer or owner_customer field).

	Returns:
		dict: {
			"success": True/False,
			"projects": [
				{
					"name": str,
					"project_name": str,
					"customer": str,
					"status": str,
					"location": str or None,
				}
			]
		}
	"""
	user = frappe.session.user
	if user == "Guest":
		return {"success": False, "error": _("Authentication required")}

	user_customer = _get_user_customer_or_fail(user)

	filters = {"is_active": 1}
	if user_customer is not None:
		# Portal user: filter by their customer
		filters["customer"] = user_customer

	projects = frappe.get_all(
		"ilL-Project",
		filters=filters,
		fields=["name", "project_name", "customer", "status", "location"],
		order_by="modified desc",
	)

	return {
		"success": True,
		"projects": projects,
	}


@frappe.whitelist(allow_guest=False)
def get_fixture_schedules(project: str) -> dict:
	"""
	Return fixture schedules for a given project.

	Verifies the user has access to the project before returning schedules.

	Args:
		project: Name of the ilL-Project

	Returns:
		dict: {
			"success": True/False,
			"schedules": [
				{
					"name": str,
					"schedule_name": str,
					"status": str,
					"line_count": int,
				}
			]
		}
	"""
	user = frappe.session.user
	if user == "Guest":
		return {"success": False, "error": _("Authentication required")}

	if not project:
		return {"success": False, "error": _("Project is required")}

	# Verify ownership
	err = _verify_project_ownership(project, user)
	if err:
		return err

	schedules = frappe.get_all(
		"ilL-Project-Fixture-Schedule",
		filters={"ill_project": project},
		fields=["name", "schedule_name", "status"],
		order_by="modified desc",
	)

	# Add line count for each schedule
	for sched in schedules:
		sched["line_count"] = frappe.db.count(
			"ilL-Child-Fixture-Schedule-Line",
			filters={"parent": sched["name"]},
		)

	return {
		"success": True,
		"schedules": schedules,
	}


@frappe.whitelist(allow_guest=False)
def get_line_ids(project: str, fixture_schedule: str) -> dict:
	"""
	Return all line items for a fixture schedule.

	Verifies the user has access to the project before returning lines.

	Args:
		project: Name of the ilL-Project
		fixture_schedule: Name of the ilL-Project-Fixture-Schedule

	Returns:
		dict: {
			"success": True/False,
			"lines": [
				{
					"name": str (child table row name),
					"line_id": str,
					"fixture_part_number": str or None,
					"qty": int,
					"location": str or None,
					"manufacturer_type": str,
					"configuration_status": str,
				}
			]
		}
	"""
	user = frappe.session.user
	if user == "Guest":
		return {"success": False, "error": _("Authentication required")}

	if not project or not fixture_schedule:
		return {"success": False, "error": _("Project and fixture_schedule are required")}

	# Verify ownership
	err = _verify_project_ownership(project, user)
	if err:
		return err

	# Verify schedule belongs to project
	if not frappe.db.exists("ilL-Project-Fixture-Schedule", fixture_schedule):
		return {"success": False, "error": _("Fixture schedule not found")}

	schedule_project = frappe.db.get_value(
		"ilL-Project-Fixture-Schedule", fixture_schedule, "ill_project"
	)
	if schedule_project != project:
		return {"success": False, "error": _("Schedule does not belong to this project")}

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", fixture_schedule)
	lines = []
	for line in schedule.lines or []:
		# Build the fixture part number from configured fixture or item code
		fixture_part_number = line.ill_item_code or None
		if not fixture_part_number and line.configured_fixture:
			fixture_part_number = frappe.db.get_value(
				"ilL-Configured-Fixture", line.configured_fixture, "item_code"
			)

		line_data = {
			"name": line.name,
			"line_id": line.line_id or f"Line {line.idx}",
			"fixture_part_number": fixture_part_number,
			"qty": line.qty or 1,
			"location": line.location or "",
			"manufacturer_type": line.manufacturer_type or "ILLUMENATE",
			"configuration_status": line.configuration_status or "Pending",
		}

		# Attach kit component stock for Extrusion Kit lines
		if getattr(line, "product_type", None) == "Extrusion Kit":
			line_data["kit_stock"] = _resolve_kit_stock_for_line(line, user)

		lines.append(line_data)

	return {
		"success": True,
		"lines": lines,
	}


@frappe.whitelist(allow_guest=False)
def add_fixture_to_schedule(
	project: str,
	fixture_schedule: str,
	fixture_part_number: str,
	line_id: str = None,
	overwrite: str = "0",
) -> dict:
	"""
	Add or overwrite a fixture line in a schedule.

	If overwrite is True and line_id is provided, the existing line's fixture
	part number is replaced. Otherwise, a new line is created with an
	auto-generated Line ID.

	Args:
		project: Name of the ilL-Project
		fixture_schedule: Name of the ilL-Project-Fixture-Schedule
		fixture_part_number: The configured fixture part number
		line_id: Optional existing line_id to overwrite
		overwrite: "1" to overwrite, "0" to create new line

	Returns:
		dict: {
			"success": True/False,
			"line_id": str (the line ID created or updated),
			"action": "created" or "overwritten",
		}
	"""
	user = frappe.session.user
	if user == "Guest":
		return {"success": False, "error": _("Authentication required")}

	if not project or not fixture_schedule or not fixture_part_number:
		return {
			"success": False,
			"error": _("project, fixture_schedule, and fixture_part_number are required"),
		}

	# Verify ownership
	err = _verify_project_ownership(project, user)
	if err:
		return err

	# Verify schedule belongs to project
	if not frappe.db.exists("ilL-Project-Fixture-Schedule", fixture_schedule):
		return {"success": False, "error": _("Fixture schedule not found")}

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", fixture_schedule)
	if schedule.ill_project != project:
		return {"success": False, "error": _("Schedule does not belong to this project")}

	# Check write permission
	if not schedule.has_permission("write"):
		return {"success": False, "error": _("Permission denied")}

	should_overwrite = str(overwrite) == "1"

	if should_overwrite and line_id:
		# Find and overwrite the existing line
		found = False
		for line in schedule.lines or []:
			if line.line_id == line_id:
				line.ill_item_code = fixture_part_number
				line.manufacturer_type = "ILLUMENATE"
				line.configuration_status = "Pending"
				# Clear the configured fixture link — it needs re-configuration
				line.configured_fixture = None
				found = True
				break

		if not found:
			return {"success": False, "error": _("Line ID not found: {0}").format(line_id)}

		schedule.save(ignore_permissions=True)
		return {
			"success": True,
			"line_id": line_id,
			"action": "overwritten",
		}
	else:
		# Create a new line with auto-generated Line ID
		existing_count = len(schedule.lines or [])
		new_line_id = line_id or f"L{existing_count + 1:03d}"

		schedule.append("lines", {
			"line_id": new_line_id,
			"ill_item_code": fixture_part_number,
			"qty": 1,
			"manufacturer_type": "ILLUMENATE",
			"configuration_status": "Pending",
		})
		schedule.save(ignore_permissions=True)

		return {
			"success": True,
			"line_id": new_line_id,
			"action": "created",
		}


@frappe.whitelist(allow_guest=False)
def get_pricing(item_code: str) -> dict:
	"""
	Return pricing for an item. Only accessible to users with the Dealer role.

	Non-Dealers or unauthenticated users receive no price data.

	Args:
		item_code: The item code to get pricing for

	Returns:
		dict: {
			"success": True/False,
			"price": float or None,
			"currency": str or None,
			"price_list": str or None,
		}
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_is_dealer_user,
		_is_internal_user,
	)

	user = frappe.session.user
	if user == "Guest":
		return {"success": False, "error": _("Authentication required")}

	if not item_code:
		return {"success": False, "error": _("item_code is required")}

	# Only Dealers and internal users can see pricing
	if not _is_dealer_user(user) and not _is_internal_user(user):
		return {"success": False, "error": _("Pricing is only available to authorized users")}

	if not frappe.db.exists("Item", item_code):
		return {"success": False, "error": _("Item not found")}

	# Get default selling price list
	default_price_list = frappe.db.get_single_value(
		"Selling Settings", "selling_price_list"
	) or "Standard Selling"

	# Look up Item Price
	price_entry = frappe.db.get_value(
		"Item Price",
		{
			"item_code": item_code,
			"price_list": default_price_list,
			"selling": 1,
		},
		["price_list_rate", "currency"],
		as_dict=True,
	)

	if not price_entry:
		# Try any selling price list
		price_entry = frappe.db.get_value(
			"Item Price",
			{
				"item_code": item_code,
				"selling": 1,
			},
			["price_list_rate", "currency", "price_list"],
			as_dict=True,
		)

	if price_entry:
		return {
			"success": True,
			"price": price_entry.price_list_rate,
			"currency": price_entry.currency,
			"price_list": price_entry.get("price_list", default_price_list),
		}

	return {
		"success": True,
		"price": None,
		"currency": None,
		"price_list": None,
	}


@frappe.whitelist(allow_guest=True)
def get_stock_status(item_code: str) -> dict:
	"""
	Return stock status for an item.  Public (guest-accessible) but only
	exposes lead-time class and basic in_stock flag.  Detailed available qty
	is only returned for authenticated Dealer / internal users.

	Args:
		item_code: The item code to check stock for

	Returns:
		dict: {
			"success": True/False,
			"in_stock": bool,
			"lead_time_class": str  ("in-stock" | "made-to-order" | "special-order"),
			"available_qty": float | None  (only for dealers/internal)
		}
	"""
	if not item_code:
		return {"success": False, "error": _("item_code is required")}

	if not frappe.db.exists("Item", item_code):
		return {"success": False, "error": _("Item not found")}

	# Determine stock qty across all warehouses
	from frappe.utils import flt

	total_qty = flt(
		frappe.db.sql(
			"""SELECT IFNULL(SUM(actual_qty), 0)
			   FROM `tabBin`
			   WHERE item_code = %s""",
			item_code,
		)[0][0]
	)

	in_stock = total_qty > 0

	# Classify lead time
	if in_stock:
		lead_time_class = "in-stock"
	else:
		# Check if item has a default lead time or is MTO
		lead_days = frappe.db.get_value("Item", item_code, "lead_time_days") or 0
		lead_time_class = "made-to-order" if lead_days > 0 else "special-order"

	result: dict = {
		"success": True,
		"in_stock": in_stock,
		"lead_time_class": lead_time_class,
	}

	# Only expose qty to dealers / internal users
	user = frappe.session.user
	if user and user != "Guest":
		from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
			_is_dealer_user,
			_is_internal_user,
		)

		if _is_dealer_user(user) or _is_internal_user(user):
			result["available_qty"] = total_qty

	return result


@frappe.whitelist(allow_guest=False)
def get_schedule_kit_stock(schedule_name: str) -> dict:
	"""
	Return kit component stock for all Extrusion Kit lines in a schedule.

	Finds kit lines, extracts attribute selections from ``variant_selections``
	JSON, resolves components, and queries stock.  Respects role-based
	visibility: dealers/internal users see full quantities, other authenticated
	users see only boolean ``in_stock`` per component.

	Args:
		schedule_name: Name of the ilL-Project-Fixture-Schedule

	Returns:
		dict: {
			"success": True/False,
			"lines": {
				"<child_row_name>": {
					"components": [...],
					"total_kits_fulfillable": int,
					"limiting_component": str or None,
				} or None (if variant_selections missing)
			}
		}
	"""
	user = frappe.session.user
	if user == "Guest":
		return {"success": False, "error": _("Authentication required")}

	if not schedule_name:
		return {"success": False, "error": _("schedule_name is required")}

	if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		return {"success": False, "error": _("Fixture schedule not found")}

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Verify project ownership
	project_name = schedule.ill_project
	if project_name:
		err = _verify_project_ownership(project_name, user)
		if err:
			return err

	result_lines = {}
	for line in schedule.lines or []:
		if getattr(line, "product_type", None) != "Extrusion Kit":
			continue
		result_lines[line.name] = _resolve_kit_stock_for_line(line, user)

	return {
		"success": True,
		"lines": result_lines,
	}


# =============================================================================
# HELPER: Kit stock resolution for a schedule line
# =============================================================================


def _resolve_kit_stock_for_line(line, user: str) -> dict | None:
	"""
	Resolve kit component stock for a single Extrusion Kit schedule line.

	Extracts selections from the line's ``variant_selections`` JSON and
	delegates to ``get_kit_component_stock`` from the configurator engine.
	Applies role-based visibility gating on the result.

	Returns None if the line has no variant_selections (unconfigured kit).
	"""
	from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
		get_kit_component_stock,
	)

	vs_raw = getattr(line, "variant_selections", None)
	if not vs_raw:
		return None

	try:
		vs = json.loads(vs_raw) if isinstance(vs_raw, str) else vs_raw
	except (json.JSONDecodeError, TypeError):
		return None

	selections = vs.get("selections", {})
	kt = selections.get("kit_template") if selections.get("kit_template") else getattr(line, "kit_template", None)
	if not kt:
		return None

	stock_result = get_kit_component_stock(
		kit_template=kt,
		finish=selections.get("finish", ""),
		lens_appearance=selections.get("lens_appearance", ""),
		mounting_method=selections.get("mounting_method", ""),
		endcap_style=selections.get("endcap_style", ""),
		endcap_color=selections.get("endcap_color", ""),
	)

	if not stock_result.get("success"):
		return None

	return _apply_stock_visibility(stock_result, user)


def _apply_stock_visibility(stock_result: dict, user: str) -> dict:
	"""
	Apply role-based visibility to kit stock data.

	Dealers / internal users see full quantities.
	Other authenticated users see only boolean ``in_stock`` per component.
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_is_dealer_user,
		_is_internal_user,
	)

	show_qty = _is_dealer_user(user) or _is_internal_user(user)

	if show_qty:
		return stock_result

	# Strip numeric quantities for non-privileged users
	filtered_components = []
	for comp in stock_result.get("components", []):
		filtered_components.append({
			"component": comp["component"],
			"item_code": comp.get("item_code"),
			"item_name": comp.get("item_name"),
			"in_stock": comp["in_stock"],
			"lead_time_class": comp["lead_time_class"],
		})

	return {
		"success": True,
		"components": filtered_components,
		"total_kits_fulfillable": stock_result["total_kits_fulfillable"],
		"limiting_component": stock_result.get("limiting_component"),
	}


@frappe.whitelist(allow_guest=True)
def get_msrp(item_code: str = None, fixture_template: str = None) -> dict:
	"""
	Return public MSRP pricing.  No authentication required.

	Pricing comes from the fixture template's base_price_msrp plus
	price_per_ft_msrp (if applicable), or from a public "MSRP" price list
	in ERPNext.  Dealer tier pricing remains gated behind get_pricing().

	Args:
		item_code: Optional item code for direct price look-up
		fixture_template: Optional fixture template code for template-level MSRP

	Returns:
		dict: {
			"success": True/False,
			"base_price_msrp": float | None,
			"price_per_ft_msrp": float | None,
			"currency": "USD"
		}
	"""
	if not item_code and not fixture_template:
		return {"success": False, "error": _("item_code or fixture_template is required")}

	result: dict = {
		"success": True,
		"base_price_msrp": None,
		"price_per_ft_msrp": None,
		"currency": "USD",
	}

	# Try fixture template MSRP fields first
	if fixture_template:
		if frappe.db.exists("ilL-Fixture-Template", fixture_template):
			tmpl = frappe.db.get_value(
				"ilL-Fixture-Template",
				fixture_template,
				["base_price_msrp", "price_per_ft_msrp"],
				as_dict=True,
			)
			if tmpl:
				result["base_price_msrp"] = tmpl.get("base_price_msrp")
				result["price_per_ft_msrp"] = tmpl.get("price_per_ft_msrp")
				if result["base_price_msrp"] is not None:
					return result

	# Fallback: look up item in an MSRP price list
	if item_code and frappe.db.exists("Item", item_code):
		msrp_price_list = "MSRP"
		if not frappe.db.exists("Price List", msrp_price_list):
			msrp_price_list = "Standard Selling"

		price_entry = frappe.db.get_value(
			"Item Price",
			{"item_code": item_code, "price_list": msrp_price_list, "selling": 1},
			["price_list_rate", "currency"],
			as_dict=True,
		)
		if price_entry:
			result["base_price_msrp"] = price_entry.price_list_rate
			result["currency"] = price_entry.currency or "USD"

	return result
