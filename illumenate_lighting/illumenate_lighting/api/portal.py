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

from illumenate_lighting.illumenate_lighting.utils import (
	parse_positive_int,
	VALID_ACCESS_LEVELS,
)


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
def get_user_projects_for_configurator() -> dict:
	"""
	Get projects accessible to the current user for the configurator page.

	Returns projects where:
	- The user owns the project
	- The project's owner_customer matches the user's customer (company-level)
	- The user is a collaborator on a private project

	Returns:
		dict: {
			"success": True/False,
			"projects": [{"value": name, "label": project_name, "customer": customer}]
		}
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
		_is_internal_user,
	)

	user = frappe.session.user

	# System Manager / internal users: get all active projects
	if _is_internal_user(user):
		projects = frappe.get_all(
			"ilL-Project",
			filters={"is_active": 1},
			fields=["name", "project_name", "customer"],
			order_by="project_name asc",
		)
		return {
			"success": True,
			"projects": [
				{"value": p.name, "label": p.project_name or p.name, "customer": p.customer}
				for p in projects
			],
		}

	user_customer = _get_user_customer(user)

	conditions = []
	params = {"user": user}

	if user_customer:
		params["user_customer"] = user_customer
		# Company-level projects (non-private) + private ones user owns or collaborates on
		conditions.append("""
			(
				(`tabilL-Project`.owner_customer = %(user_customer)s AND `tabilL-Project`.is_private = 0)
				OR `tabilL-Project`.owner = %(user)s
				OR `tabilL-Project`.name IN (
					SELECT parent FROM `tabilL-Child-Project-Collaborator`
					WHERE user = %(user)s AND is_active = 1
				)
			)
		""")
	else:
		# No customer link — only own projects or collaborations
		conditions.append("""
			(
				`tabilL-Project`.owner = %(user)s
				OR `tabilL-Project`.name IN (
					SELECT parent FROM `tabilL-Child-Project-Collaborator`
					WHERE user = %(user)s AND is_active = 1
				)
			)
		""")

	where_clause = " AND ".join(conditions) if conditions else "1=1"

	projects = frappe.db.sql(f"""
		SELECT name, project_name, customer
		FROM `tabilL-Project`
		WHERE is_active = 1 AND {where_clause}
		ORDER BY project_name ASC
	""", params, as_dict=True)

	return {
		"success": True,
		"projects": [
			{"value": p.name, "label": p.project_name or p.name, "customer": p.customer}
			for p in projects
		],
	}


@frappe.whitelist()
def get_schedules_for_project(project_name: str) -> dict:
	"""
	Get fixture schedules accessible to the current user for the given project.

	Args:
		project_name: Name of the ilL-Project

	Returns:
		dict: {
			"success": True/False,
			"schedules": [{"value": name, "label": schedule_name, "status": status}]
		}
	"""
	if not frappe.db.exists("ilL-Project", project_name):
		return {"success": False, "schedules": [], "error": "Project not found"}

	# Check project-level permission
	project = frappe.get_doc("ilL-Project", project_name)
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		has_permission as project_has_permission,
	)
	if not project_has_permission(project, "read", frappe.session.user):
		return {"success": False, "schedules": [], "error": "Permission denied"}

	schedules = frappe.get_all(
		"ilL-Project-Fixture-Schedule",
		filters={"ill_project": project_name},
		fields=["name", "schedule_name", "status"],
		order_by="modified desc",
	)

	return {
		"success": True,
		"schedules": [
			{"value": s.name, "label": s.schedule_name or s.name, "status": s.status}
			for s in schedules
		],
	}


@frappe.whitelist()
def get_schedule_lines_for_configurator(schedule_name: str) -> dict:
	"""
	Get all fixture schedule lines for a schedule, for display in the configurator.

	Returns all lines including OTHER manufacturer lines so users can
	override them with ilLumenate configurations.

	Args:
		schedule_name: Name of the ilL-Project-Fixture-Schedule

	Returns:
		dict: {
			"success": True/False,
			"lines": [
				{
					"idx": int,
					"line_id": str,
					"manufacturer_type": str,
					"qty": int,
					"location": str,
					"notes": str,
					"configuration_status": str,
					"configured_fixture": str or None,
					"fixture_template": str or None,
					"manufacturer_name": str or None,
					"fixture_model_number": str or None,
					"summary": str  -- human-readable summary of current content
				}
			],
			"can_save": bool
		}
	"""
	if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		return {"success": False, "lines": [], "can_save": False, "error": "Schedule not found"}

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		has_permission,
	)

	can_read = has_permission(schedule, "read", frappe.session.user)
	if not can_read:
		return {"success": False, "lines": [], "can_save": False, "error": "Permission denied"}

	can_save = has_permission(schedule, "write", frappe.session.user)

	lines = []
	for idx, line in enumerate(schedule.lines or []):
		line_data = {
			"idx": idx,
			"line_id": line.line_id or f"Line {idx + 1}",
			"manufacturer_type": line.manufacturer_type or "ILLUMENATE",
			"qty": line.qty or 1,
			"location": line.location or "",
			"notes": line.notes or "",
			"configuration_status": line.configuration_status or "Pending",
			"configured_fixture": line.configured_fixture or None,
			"fixture_template": line.fixture_template or None,
			"manufacturer_name": line.manufacturer_name or None,
			"fixture_model_number": line.fixture_model_number or None,
			"ill_item_code": line.ill_item_code or None,
			"manufacturable_length_mm": line.manufacturable_length_mm or None,
		}

		# Build a human-readable summary of what's currently stored
		summary_parts = []
		if line.manufacturer_type == "ILLUMENATE":
			if line.configured_fixture:
				summary_parts.append(f"Configured: {line.configured_fixture}")
				if line.ill_item_code:
					summary_parts.append(f"Item: {line.ill_item_code}")
				if line.manufacturable_length_mm:
					length_in = round(line.manufacturable_length_mm / 25.4, 1)
					summary_parts.append(f"Length: {length_in}\"")
			elif line.fixture_template:
				summary_parts.append(f"Template: {line.fixture_template} (not configured)")
			else:
				summary_parts.append("Empty ILLUMENATE line")
		elif line.manufacturer_type == "OTHER":
			if line.manufacturer_name:
				summary_parts.append(f"Manufacturer: {line.manufacturer_name}")
			if line.fixture_model_number:
				summary_parts.append(f"Model: {line.fixture_model_number}")
			if line.trim_info:
				summary_parts.append(f"Trim: {line.trim_info}")
			if line.housing_model_number:
				summary_parts.append(f"Housing: {line.housing_model_number}")
			if line.driver_model_number:
				summary_parts.append(f"Driver: {line.driver_model_number}")
			if not summary_parts:
				summary_parts.append("Empty OTHER line")
		elif line.manufacturer_type == "ACCESSORY":
			if line.accessory_item:
				summary_parts.append(f"Accessory: {line.accessory_item}")
			else:
				summary_parts.append("Empty ACCESSORY line")

		if line.location:
			summary_parts.append(f"Location: {line.location}")

		line_data["summary"] = " | ".join(summary_parts)
		lines.append(line_data)

	return {
		"success": True,
		"lines": lines,
		"can_save": can_save,
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
		# New cascading configurator options
		"led_packages": [],
		"ccts": [],
	}

	# Parse allowed options from template
	for row in template.get("allowed_options", []):
		if not row.is_active:
			continue

		option_type = row.option_type
		if option_type == "Finish" and row.finish:
			options["finish"].append({"value": row.finish, "label": row.finish})
		elif option_type == "Lens Appearance" and row.lens_appearance:
			# Get lens transmission for cascading configurator
			# Transmission is stored as decimal (0.56 = 56%), convert to percentage for display
			lens_transmission_pct = 100
			lens_transmission_decimal = 1.0
			if frappe.db.exists("ilL-Attribute-Lens Appearance", row.lens_appearance):
				lens_doc = frappe.get_doc("ilL-Attribute-Lens Appearance", row.lens_appearance)
				if lens_doc.transmission:
					lens_transmission_decimal = lens_doc.transmission
					lens_transmission_pct = lens_doc.transmission * 100
			options["lens_appearance"].append({
				"value": row.lens_appearance,
				"label": row.lens_appearance,
				"transmission": lens_transmission_decimal,  # Keep decimal for calculations
				"transmission_pct": lens_transmission_pct,  # Percentage for display
			})
		elif option_type == "Mounting Method" and row.mounting_method:
			options["mounting_method"].append({"value": row.mounting_method, "label": row.mounting_method})
		elif option_type == "Endcap Style" and row.endcap_style:
			options["endcap_style"].append({"value": row.endcap_style, "label": row.endcap_style})
		elif option_type == "Power Feed Type" and row.power_feed_type:
			options["power_feed_type"].append({"value": row.power_feed_type, "label": row.power_feed_type})
		elif option_type == "Environment Rating" and row.environment_rating:
			options["environment_rating"].append({"value": row.environment_rating, "label": row.environment_rating})

	# Get feed direction options from ilL-Attribute-Feed-Direction
	if frappe.db.exists("DocType", "ilL-Attribute-Feed-Direction"):
		feed_dirs = frappe.get_all(
			"ilL-Attribute-Feed-Direction",
			filters={"is_active": 1},
			fields=["direction_name as name", "code"],
			order_by="direction_name",
		)
		options["feed_directions"] = [
			{"value": d.name, "label": d.name, "code": d.code}
			for d in feed_dirs
		]
	else:
		options["feed_directions"] = [
			{"value": "End", "label": "End", "code": "E"},
			{"value": "Back", "label": "Back", "code": "B"},
			{"value": "Left", "label": "Left", "code": "L"},
			{"value": "Right", "label": "Right", "code": "R"},
		]

	# Get tape offerings from template
	for row in template.get("allowed_tape_offerings", []):
		if row.tape_offering:
			options["tape_offerings"].append({"value": row.tape_offering, "label": row.tape_offering})

	# Extract LED packages from tape offerings (for cascading configurator)
	tape_offering_names = [row.tape_offering for row in template.get("allowed_tape_offerings", []) if row.tape_offering]
	if tape_offering_names:
		tape_offerings = frappe.get_all(
			"ilL-Rel-Tape Offering",
			filters={"name": ["in", tape_offering_names], "is_active": 1},
			fields=["led_package", "cct"],
			distinct=True,
		)

		# Get unique LED packages
		led_package_codes = list({t.led_package for t in tape_offerings if t.led_package})
		if led_package_codes:
			led_packages = frappe.get_all(
				"ilL-Attribute-LED Package",
				filters={"name": ["in", led_package_codes]},
				fields=["name", "code", "spectrum_type"],
			)
			for pkg in led_packages:
				options["led_packages"].append({
					"value": pkg.name,
					"label": pkg.name,
					"code": pkg.code,
					"spectrum_type": pkg.spectrum_type,
				})

		# Get unique CCTs
		cct_codes = list({t.cct for t in tape_offerings if t.cct})
		if cct_codes:
			ccts = frappe.get_all(
				"ilL-Attribute-CCT",
				filters={"name": ["in", cct_codes], "is_active": 1},
				fields=["name", "code", "label", "kelvin", "sort_order"],
				order_by="sort_order asc, kelvin asc",
			)
			for cct in ccts:
				options["ccts"].append({
					"value": cct.name,
					"label": cct.label or cct.name,
					"code": cct.code,
					"kelvin": cct.kelvin,
				})

	# Get all endcap colors (kept for backward compatibility)
	endcap_colors = frappe.get_all(
		"ilL-Attribute-Endcap Color",
		fields=["code", "display_name"],
	)
	for color in endcap_colors:
		options["endcap_colors"].append({
			"value": color.code,
			"label": color.display_name or color.code,
		})

	# Build finish → endcap color mapping from ilL-Rel-Finish Endcap Color
	options["finish_endcap_color_map"] = {}
	finish_endcap_mappings = frappe.get_all(
		"ilL-Rel-Finish Endcap Color",
		filters={"is_active": 1},
		fields=["finish", "endcap_color", "is_default"],
		order_by="is_default DESC, modified DESC",
	)
	for mapping in finish_endcap_mappings:
		if mapping.finish not in options["finish_endcap_color_map"]:
			ec_code = frappe.db.get_value("ilL-Attribute-Endcap Color", mapping.endcap_color, "code")
			ec_display = frappe.db.get_value("ilL-Attribute-Endcap Color", mapping.endcap_color, "display_name")
			options["finish_endcap_color_map"][mapping.finish] = {
				"endcap_color": mapping.endcap_color,
				"endcap_color_code": ec_code or mapping.endcap_color,
				"endcap_color_label": ec_display or ec_code or mapping.endcap_color,
			}

	return options


@frappe.whitelist()
def get_product_types(include_subgroups: bool = True) -> dict:
	"""
	Get product types from Item Groups under the root Item Group.

	This dynamically discovers all top-level Item Groups (children of
	"All Item Groups") and builds a nested tree for each one, including
	categories like "Products", "Raw Materials", etc.
	If include_subgroups is True, also includes child groups (up to 2 levels deep)
	with visual indentation.

	Args:
		include_subgroups: Whether to include child groups with indentation

	Returns:
		dict: {
			"success": True/False,
			"product_types": [
				{
					"value": name,
					"label": display_name,
					"item_group": item_group_name,
					"level": 0|1|2,  # Depth level for indentation
					"parent": parent_group_name or None,
					"root_group": "Products" or "Raw Materials",
					"is_header": True/False  # If True, this is a non-selectable group header
				}
			]
		}
	"""
	try:
		# Define which item groups should show fixture templates instead of items
		# Match by checking if name contains "Linear Fixture" (case-insensitive)
		def is_fixture_group(name):
			name_lower = (name or "").lower()
			return "linear fixture" in name_lower or "linear fixtures" in name_lower

		def _build_group_tree(parent_group_name, root_group_label):
			"""Build a nested tree of item groups under a parent."""
			if not frappe.db.exists("Item Group", parent_group_name):
				return []

			items = []

			# Get immediate children of this parent item group
			child_groups = frappe.get_all(
				"Item Group",
				filters={"parent_item_group": parent_group_name},
				fields=["name", "item_group_name"],
				order_by="item_group_name asc",
			)

			for child in child_groups:
				# Add the child group (level 0 under parent header)
				items.append({
					"value": child.name,
					"label": child.item_group_name or child.name,
					"item_group": child.name,
					"level": 0,
					"parent": parent_group_name,
					"root_group": root_group_label,
					"is_header": False,
					"is_fixture_type": is_fixture_group(child.name) or is_fixture_group(child.item_group_name),
				})

				# If include_subgroups, fetch sub-groups
				if include_subgroups:
					sub_groups = frappe.get_all(
						"Item Group",
						filters={"parent_item_group": child.name},
						fields=["name", "item_group_name"],
						order_by="item_group_name asc",
					)

					for sub in sub_groups:
						items.append({
							"value": sub.name,
							"label": sub.item_group_name or sub.name,
							"item_group": sub.name,
							"level": 1,
							"parent": child.name,
							"root_group": root_group_label,
							"is_header": False,
							"is_fixture_type": is_fixture_group(sub.name) or is_fixture_group(sub.item_group_name),
						})

						# Grandchild groups (level 2)
						grandchild_groups = frappe.get_all(
							"Item Group",
							filters={"parent_item_group": sub.name},
							fields=["name", "item_group_name"],
							order_by="item_group_name asc",
						)

						for grandchild in grandchild_groups:
							items.append({
								"value": grandchild.name,
								"label": grandchild.item_group_name or grandchild.name,
								"item_group": grandchild.name,
								"level": 2,
								"parent": sub.name,
								"root_group": root_group_label,
								"is_header": False,
								"is_fixture_type": is_fixture_group(grandchild.name) or is_fixture_group(grandchild.item_group_name),
							})

			return items

		# Dynamically discover all top-level Item Groups instead of hardcoding names.
		# In ERPNext the root is usually "All Item Groups"; find its children to use
		# as category headers (e.g., "Products", "Raw Materials", etc.).
		root_item_group = None
		# Find the actual root – try common names
		for candidate_root in ["All Item Groups", "All Products"]:
			if frappe.db.exists("Item Group", candidate_root):
				root_item_group = candidate_root
				break

		if root_item_group:
			# Get all children of the root as our top-level category headers
			root_children = frappe.get_all(
				"Item Group",
				filters={"parent_item_group": root_item_group},
				fields=["name", "item_group_name"],
				order_by="item_group_name asc",
			)
			root_groups = [(child.name, child.item_group_name or child.name) for child in root_children]
		else:
			# Fallback to the original hardcoded list
			root_groups = [("Products", "Products"), ("Raw Materials", "Raw Materials")]

		result = []

		for root_name, root_label in root_groups:
			group_items = _build_group_tree(root_name, root_label)
			if group_items:
				# Add a non-selectable header for this root group
				result.append({
					"value": "__header_" + root_name,
					"label": root_label,
					"item_group": root_name,
					"level": -1,
					"parent": None,
					"root_group": root_label,
					"is_header": True,
					"is_fixture_type": False,
				})
				result.extend(group_items)

		# If no groups found, return default
		if not result:
			result = [{
				"value": "Linear Fixture",
				"label": "Linear Fixture",
				"item_group": None,
				"level": 0,
				"parent": None,
				"root_group": "Products",
				"is_header": False,
				"is_fixture_type": True,
			}]

		return {"success": True, "product_types": result}

	except Exception as e:
		frappe.log_error(f"Error fetching product types: {str(e)}")
		return {
			"success": False,
			"error": str(e),
			"product_types": [{"value": "Linear Fixture", "label": "Linear Fixture", "item_group": None, "level": 0, "parent": None}],
		}


@frappe.whitelist()
def get_items_by_product_type(product_type: str, exclude_variants: bool = True) -> dict:
	"""
	Get items within a specific product type (Item Group).

	This fetches all sellable items within the specified Item Group,
	allowing customers to add accessories like profiles, lenses, etc.
	to their fixture schedule.

	Args:
		product_type: The Item Group name to fetch items from
		exclude_variants: If True, only return template items (not variant items)

	Returns:
		dict: {
			"success": True/False,
			"items": [
				{
					"item_code": str,
					"item_name": str,
					"description": str,
					"stock_uom": str,
					"image": str or None,
					"standard_rate": float,
					"has_variants": bool,  # True if this item is a template with variants
					"variant_of": str or None  # Parent template if this is a variant
				}
			]
		}
	"""
	try:
		if not product_type:
			return {"success": False, "error": "Product type is required", "items": []}

		# Fetch items from this item group and its descendants
		# First, get all descendant item groups
		item_groups = [product_type]

		# Get child groups recursively (up to 3 levels)
		for _ in range(3):
			child_groups = frappe.get_all(
				"Item Group",
				filters={"parent_item_group": ["in", item_groups]},
				fields=["name"],
			)
			new_groups = [g.name for g in child_groups if g.name not in item_groups]
			if not new_groups:
				break
			item_groups.extend(new_groups)

		# Build filters
		filters = {
			"item_group": ["in", item_groups],
			"disabled": 0,
			"is_sales_item": 1,
		}

		# If exclude_variants is True, only get non-variant items (templates and regular items)
		if exclude_variants:
			filters["variant_of"] = ["is", "not set"]

		# Fetch items from these groups
		items = frappe.get_all(
			"Item",
			filters=filters,
			fields=[
				"item_code",
				"item_name",
				"description",
				"stock_uom",
				"image",
				"standard_rate",
				"has_variants",
				"variant_of",
			],
			order_by="item_name asc",
		)

		result = []
		for item in items:
			result.append({
				"item_code": item.item_code,
				"item_name": item.item_name,
				"description": item.description or "",
				"stock_uom": item.stock_uom or "Nos",
				"image": item.image,
				"standard_rate": float(item.standard_rate or 0),
				"has_variants": bool(item.has_variants),
				"variant_of": item.variant_of or None,
			})

		return {"success": True, "items": result}

	except Exception as e:
		frappe.log_error(f"Error fetching items for product type {product_type}: {str(e)}")
		return {"success": False, "error": str(e), "items": []}


@frappe.whitelist()
def get_item_variant_attributes(template_item: str) -> dict:
	"""
	Get the available variant attributes for a template item.

	This returns the attributes and their possible values that can be used
	to configure a variant of the given template item.

	Args:
		template_item: The item_code of the template item

	Returns:
		dict: {
			"success": True/False,
			"template_item": str,
			"attributes": [
				{
					"attribute": str,  # Attribute name (e.g., "Color", "Size")
					"values": [str]    # List of possible values
				}
			]
		}
	"""
	try:
		if not template_item:
			return {"success": False, "error": "Template item is required", "attributes": []}

		# Check if item exists and has variants
		item = frappe.db.get_value(
			"Item",
			template_item,
			["item_code", "item_name", "has_variants"],
			as_dict=True,
		)

		if not item:
			return {"success": False, "error": "Item not found", "attributes": []}

		if not item.has_variants:
			return {"success": True, "template_item": template_item, "attributes": [], "message": "Item has no variants"}

		# Get the item attributes for this template
		item_doc = frappe.get_doc("Item", template_item)

		# Collect attribute values actually used by existing variants
		variants = frappe.get_all(
			"Item",
			filters={"variant_of": template_item, "disabled": 0},
			fields=["item_code"],
		)

		# Build a map of attribute -> set of values used across all variants
		variant_attr_values = {}
		for variant in variants:
			variant_doc = frappe.get_doc("Item", variant.item_code)
			for va in variant_doc.get("attributes", []):
				variant_attr_values.setdefault(va.attribute, set()).add(va.attribute_value)

		attributes = []

		for attr in item_doc.get("attributes", []):
			if attr.numeric_values:
				# For numeric attributes, we need a different approach
				values = [{
					"value": str(attr.from_range) + " - " + str(attr.to_range),
					"abbr": "",
					"is_numeric": True,
					"from_range": attr.from_range,
					"to_range": attr.to_range,
					"increment": attr.increment,
				}]
			else:
				# Get all possible values for this attribute (for ordering)
				attr_values = frappe.get_all(
					"Item Attribute Value",
					filters={"parent": attr.attribute},
					fields=["attribute_value", "abbr"],
					order_by="idx asc",
				)

				# Filter to only values that exist in actual variants
				used_values = variant_attr_values.get(attr.attribute, set())
				values = [
					{"value": v.attribute_value, "abbr": v.abbr or v.attribute_value}
					for v in attr_values
					if v.attribute_value in used_values
				]

			attributes.append({
				"attribute": attr.attribute,
				"values": values,
			})

		return {
			"success": True,
			"template_item": template_item,
			"item_name": item.item_name,
			"attributes": attributes,
		}

	except Exception as e:
		frappe.log_error(f"Error fetching variant attributes for {template_item}: {str(e)}")
		return {"success": False, "error": str(e), "attributes": []}


@frappe.whitelist()
def get_filtered_variant_attributes(template_item: str, selected_attributes: Union[str, dict] = None) -> dict:
	"""
	Get variant attribute values filtered by currently selected attributes.

	Given the current selections, returns only the attribute values that would
	still lead to a valid variant match. This enables cascading dropdown filtering.

	Args:
		template_item: The item_code of the template item
		selected_attributes: Dict of {attribute_name: attribute_value} for currently selected attributes

	Returns:
		dict: {
			"success": True/False,
			"attributes": [
				{
					"attribute": str,
					"values": [{"value": str, "abbr": str}]
				}
			]
		}
	"""
	try:
		if not template_item:
			return {"success": False, "error": "Template item is required", "attributes": []}

		if isinstance(selected_attributes, str):
			selected_attributes = json.loads(selected_attributes) if selected_attributes else {}
		if not selected_attributes:
			selected_attributes = {}

		# Get all variants with their attributes
		variants = frappe.get_all(
			"Item",
			filters={"variant_of": template_item, "disabled": 0},
			fields=["item_code"],
		)

		variant_attr_list = []
		for variant in variants:
			variant_doc = frappe.get_doc("Item", variant.item_code)
			attrs = {}
			for va in variant_doc.get("attributes", []):
				attrs[va.attribute] = va.attribute_value
			variant_attr_list.append(attrs)

		# Get template attributes for ordering
		item_doc = frappe.get_doc("Item", template_item)
		template_attrs = [attr.attribute for attr in item_doc.get("attributes", [])]

		attributes = []
		for attr_name in template_attrs:
			# For each attribute, find which values are still valid given the other selections
			valid_values = set()
			for variant_attrs in variant_attr_list:
				# Check if this variant matches all OTHER selected attributes
				matches_others = True
				for sel_attr, sel_val in selected_attributes.items():
					if sel_attr == attr_name:
						continue  # Skip the current attribute
					if variant_attrs.get(sel_attr) != sel_val:
						matches_others = False
						break
				if matches_others and attr_name in variant_attrs:
					valid_values.add(variant_attrs[attr_name])

			# Get ordered attribute values
			attr_values = frappe.get_all(
				"Item Attribute Value",
				filters={"parent": attr_name},
				fields=["attribute_value", "abbr"],
				order_by="idx asc",
			)

			values = [
				{"value": v.attribute_value, "abbr": v.abbr or v.attribute_value}
				for v in attr_values
				if v.attribute_value in valid_values
			]

			attributes.append({
				"attribute": attr_name,
				"values": values,
			})

		return {"success": True, "attributes": attributes}

	except Exception as e:
		frappe.log_error(f"Error fetching filtered variant attributes for {template_item}: {str(e)}")
		return {"success": False, "error": str(e), "attributes": []}


@frappe.whitelist()
def get_item_variants(template_item: str) -> dict:
	"""
	Get all variants of a template item with their attribute values.

	Args:
		template_item: The item_code of the template item

	Returns:
		dict: {
			"success": True/False,
			"template_item": str,
			"variants": [
				{
					"item_code": str,
					"item_name": str,
					"attributes": {attribute_name: attribute_value, ...},
					"standard_rate": float,
					"image": str or None
				}
			]
		}
	"""
	try:
		if not template_item:
			return {"success": False, "error": "Template item is required", "variants": []}

		# Check if item exists and has variants
		if not frappe.db.get_value("Item", template_item, "has_variants"):
			return {"success": True, "template_item": template_item, "variants": []}

		# Get all variants of this template
		variants = frappe.get_all(
			"Item",
			filters={
				"variant_of": template_item,
				"disabled": 0,
			},
			fields=["item_code", "item_name", "standard_rate", "image"],
			order_by="item_name asc",
		)

		result = []
		for variant in variants:
			# Get the attribute values for this variant
			variant_doc = frappe.get_doc("Item", variant.item_code)
			attributes = {}
			for attr in variant_doc.get("attributes", []):
				attributes[attr.attribute] = attr.attribute_value

			result.append({
				"item_code": variant.item_code,
				"item_name": variant.item_name,
				"attributes": attributes,
				"standard_rate": float(variant.standard_rate or 0),
				"image": variant.image,
			})

		return {"success": True, "template_item": template_item, "variants": result}

	except Exception as e:
		frappe.log_error(f"Error fetching variants for {template_item}: {str(e)}")
		return {"success": False, "error": str(e), "variants": []}


@frappe.whitelist()
def find_matching_variant(template_item: str, selected_attributes: Union[str, dict]) -> dict:
	"""
	Find a variant that matches the selected attribute values.

	Args:
		template_item: The item_code of the template item
		selected_attributes: Dict of {attribute_name: attribute_value} or JSON string

	Returns:
		dict: {
			"success": True/False,
			"found": True/False,
			"variant": {
				"item_code": str,
				"item_name": str,
				"standard_rate": float,
				"image": str or None
			} or None
		}
	"""
	try:
		if not template_item:
			return {"success": False, "error": "Template item is required"}

		# Parse selected_attributes if it's a string
		if isinstance(selected_attributes, str):
			selected_attributes = json.loads(selected_attributes)

		if not selected_attributes:
			return {"success": False, "error": "Selected attributes are required"}

		# Get all variants of this template
		variants_result = get_item_variants(template_item)
		if not variants_result.get("success"):
			return variants_result

		variants = variants_result.get("variants", [])

		# Find the variant that matches all selected attributes
		for variant in variants:
			variant_attrs = variant.get("attributes", {})
			# Check if all selected attributes match
			matches = True
			for attr_name, attr_value in selected_attributes.items():
				if variant_attrs.get(attr_name) != attr_value:
					matches = False
					break

			if matches:
				return {
					"success": True,
					"found": True,
					"variant": {
						"item_code": variant["item_code"],
						"item_name": variant["item_name"],
						"standard_rate": variant["standard_rate"],
						"image": variant["image"],
					},
				}

		return {"success": True, "found": False, "variant": None, "message": "No matching variant found"}

	except Exception as e:
		frappe.log_error(f"Error finding variant for {template_item}: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_fixture_templates(product_type: str = None) -> dict:
	"""
	Get available fixture templates for the portal.

	Args:
		product_type: Optional filter by product type (e.g., "Linear Fixture")

	Returns:
		dict: {
			"templates": [{"name": template_code, "template_name": name, "template_code": code, "image": url or None}]
		}
	"""
	# Get active fixture templates
	filters = {"is_active": 1}

	templates = frappe.get_all(
		"ilL-Fixture-Template",
		filters=filters,
		fields=["name", "template_code", "template_name", "webflow_product"],
		order_by="template_name asc",
	)

	# Batch-fetch featured images for templates that have a linked Webflow product
	webflow_product_names = [t.webflow_product for t in templates if t.webflow_product]
	webflow_product_images = {}
	if webflow_product_names:
		webflow_products = frappe.get_all(
			"ilL-Webflow-Product",
			filters={"name": ["in", webflow_product_names]},
			fields=["name", "featured_image"],
		)
		webflow_product_images = {r.name: r.featured_image for r in webflow_products if r.featured_image}

	result = []
	for t in templates:
		result.append({
			"name": t.name,
			"template_code": t.template_code,
			"template_name": t.template_name,
			"image": webflow_product_images.get(t.webflow_product) if t.webflow_product else None,
		})

	return {"templates": result}


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
		try:
			line_data = json.loads(line_data)
		except json.JSONDecodeError:
			return {"success": False, "error": "Invalid line_data format"}

	# Add the line
	try:
		line = schedule.append("lines", {})
		line.line_id = line_data.get("line_id")
		line.qty = parse_positive_int(line_data.get("qty", 1), default=1, minimum=1)
		line.location = line_data.get("location")
		line.manufacturer_type = line_data.get("manufacturer_type", "ILLUMENATE")
		line.notes = line_data.get("notes")

		if line.manufacturer_type == "ILLUMENATE":
			line.product_type = line_data.get("product_type")
			line.fixture_template = line_data.get("fixture_template")
			line.configuration_status = line_data.get("configuration_status", "Pending")

		if line.manufacturer_type == "ACCESSORY":
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

	try:
		line_idx = int(line_idx)
	except (ValueError, TypeError):
		return {"success": False, "error": "Invalid line index"}

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

	try:
		line_idx = int(line_idx)
	except (ValueError, TypeError):
		return {"success": False, "error": "Invalid line index"}

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
		try:
			line_data = json.loads(line_data)
		except json.JSONDecodeError:
			return {"success": False, "error": "Invalid line_data format"}

	try:
		line_idx = int(line_idx)
	except (ValueError, TypeError):
		return {"success": False, "error": "Invalid line index"}

	if line_idx < 0 or line_idx >= len(schedule.lines):
		return {"success": False, "error": "Invalid line index"}

	try:
		line = schedule.lines[line_idx]

		# Update allowed fields
		if "line_id" in line_data:
			line.line_id = line_data.get("line_id")
		if "qty" in line_data:
			line.qty = parse_positive_int(line_data.get("qty", 1), default=1, minimum=1)
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
			"estimated_delivered_output": cf.estimated_delivered_output if hasattr(cf, "estimated_delivered_output") else None,
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
		lens_transmission = 1.0  # Default 100% if not found (as decimal)
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

				# Get output level display name
				if tape_offering.output_level:
					output_level_doc = frappe.db.get_value(
						"ilL-Attribute-Output Level",
						tape_offering.output_level,
						["output_level_name", "value"],
						as_dict=True,
					)
					if output_level_doc:
						details["output_level"] = output_level_doc.output_level_name
						# Fallback: calculate estimated delivered output if not stored on fixture
						if not details["estimated_delivered_output"] and output_level_doc.value:
							delivered = output_level_doc.value * lens_transmission
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
			try:
				line_idx = int(line_idx)
			except (ValueError, TypeError):
				return {"success": False, "error": "Invalid line index"}
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
		try:
			line.manufacturable_length_mm = int(manufacturable_length_mm)
		except (ValueError, TypeError):
			return {"success": False, "error": "Invalid manufacturable_length_mm"}

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
def build_configured_fixture_and_item(configured_fixture_id: str) -> dict:
	"""
	Build a configured fixture's Item (and update fixture links).

	Only accessible to System Manager users. This allows creating the
	configured Item directly from the portal Configure page without
	needing to create a Sales Order first.

	Args:
		configured_fixture_id: Name of the ilL-Configured-Fixture document

	Returns:
		dict: {"success": True/False, "item_code": str, "error": "message if error"}
	"""
	# Only System Managers can use this endpoint
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		return {"success": False, "error": "Only System Managers can build configured fixtures and items"}

	# Validate configured fixture exists
	if not frappe.db.exists("ilL-Configured-Fixture", configured_fixture_id):
		return {"success": False, "error": "Configured fixture not found"}

	try:
		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
			_create_or_get_configured_item,
			_update_fixture_links,
		)

		fixture = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_id)

		item_result = _create_or_get_configured_item(fixture, skip_if_exists=True)
		if not item_result.get("success"):
			error_msgs = [m["text"] for m in item_result.get("messages", []) if m.get("severity") == "error"]
			return {"success": False, "error": "; ".join(error_msgs) or "Failed to create item"}

		item_code = item_result["item_code"]

		# Update the fixture with the item link
		_update_fixture_links(fixture, item_code=item_code, bom_name=None, work_order_name=None)

		return {
			"success": True,
			"item_code": item_code,
			"created": item_result.get("created", False),
			"skipped": item_result.get("skipped", False),
			"messages": item_result.get("messages", []),
		}
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
		try:
			project_data = json.loads(project_data)
		except json.JSONDecodeError:
			return {"success": False, "error": "Invalid project_data format"}

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
		try:
			schedule_data = json.loads(schedule_data)
		except json.JSONDecodeError:
			return {"success": False, "error": "Invalid schedule_data format"}

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
def rename_schedule(schedule_name: str, new_schedule_name: str) -> dict:
	"""
	Rename an existing ilL-Project-Fixture-Schedule.

	Args:
		schedule_name: Name (ID) of the schedule to rename
		new_schedule_name: New display name for the schedule

	Returns:
		dict: {"success": True/False, "error": "message if error"}
	"""
	if not new_schedule_name or not new_schedule_name.strip():
		return {"success": False, "error": "Schedule name cannot be empty"}

	new_schedule_name = new_schedule_name.strip()

	if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		return {"success": False, "error": "Schedule not found"}

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		has_permission,
	)

	if not has_permission(schedule, "write", frappe.session.user):
		return {"success": False, "error": "You don't have permission to rename this schedule"}

	try:
		schedule.schedule_name = new_schedule_name
		schedule.save()
		return {"success": True}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def delete_schedule(schedule_name: str) -> dict:
	"""
	Delete an existing ilL-Project-Fixture-Schedule.

	Only schedules in DRAFT status can be deleted.

	Args:
		schedule_name: Name (ID) of the schedule to delete

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
		return {"success": False, "error": "You don't have permission to delete this schedule"}

	# Only allow deletion of DRAFT schedules
	if schedule.status != "DRAFT":
		return {"success": False, "error": "Only schedules in DRAFT status can be deleted"}

	try:
		frappe.delete_doc("ilL-Project-Fixture-Schedule", schedule_name)
		return {"success": True}
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
		try:
			collaborators = json.loads(collaborators)
		except json.JSONDecodeError:
			return {"success": False, "error": "Invalid collaborators format"}

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

	Portal users can create customers (e.g., end-clients for projects) without
	being linked as a contact to them. The customer is just created and made
	available for project assignment. The creator is tracked via the 'owner' field.

	Args:
		customer_data: Dict with customer fields (customer_name, customer_type, territory, etc.)

	Returns:
		dict: {"success": True/False, "customer_name": name, "error": "message if error"}
	"""
	# Parse customer_data if it's a string
	if isinstance(customer_data, str):
		try:
			customer_data = json.loads(customer_data)
		except json.JSONDecodeError:
			return {"success": False, "error": "Invalid customer_data format"}

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

		# NOTE: We intentionally do NOT link the current user to this customer.
		# The user's primary company association should remain unchanged.
		# The 'owner' field on the Customer record tracks who created it,
		# which is used in get_allowed_customers_for_project() to give the
		# creator access to this customer for project assignment.

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
		try:
			request_data = json.loads(request_data)
		except json.JSONDecodeError:
			return {"success": False, "error": "Invalid request_data format"}

	if not request_data.get("description"):
		return {"success": False, "error": "Description is required"}

	try:
		# Check if Document Request doctype exists, if not create the request as an Issue
		if frappe.db.exists("DocType", "ilL-Document-Request"):
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
		try:
			ticket_data = json.loads(ticket_data)
		except json.JSONDecodeError:
			return {"success": False, "error": "Invalid ticket_data format"}

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
		try:
			profile_data = json.loads(profile_data)
		except json.JSONDecodeError:
			return {"success": False, "error": "Invalid profile_data format"}

	try:
		user = frappe.get_doc("User", frappe.session.user)

		if "first_name" in profile_data:
			user.first_name = profile_data.get("first_name")
		if "last_name" in profile_data:
			user.last_name = profile_data.get("last_name")
		if "phone" in profile_data:
			user.phone = profile_data.get("phone")
		if "job_title" in profile_data:
			# Update job_title on the linked Contact, not on User
			_update_contact_job_title(frappe.session.user, profile_data.get("job_title"))

		user.save()
		return {"success": True}
	except Exception as e:
		frappe.log_error(f"Error updating user profile: {str(e)}")
		return {"success": False, "error": str(e)}


def _update_contact_job_title(user, job_title):
	"""Update job_title on the Contact linked to this user."""
	contacts = frappe.get_all(
		"Contact",
		filters={"user": user},
		fields=["name"],
		limit=1,
	)
	if contacts:
		frappe.db.set_value("Contact", contacts[0].name, "designation", job_title)


def _get_or_create_portal_settings(user=None):
	"""
	Get or create the ilL-Portal-User-Settings record for a user.

	Args:
		user: User email. Defaults to current session user.

	Returns:
		Document: The ilL-Portal-User-Settings document.
	"""
	if not user:
		user = frappe.session.user

	settings_name = frappe.db.get_value(
		"ilL-Portal-User-Settings", {"user": user}, "name"
	)

	if settings_name:
		return frappe.get_doc("ilL-Portal-User-Settings", settings_name)

	# Create with defaults
	settings = frappe.new_doc("ilL-Portal-User-Settings")
	settings.user = user
	settings.insert(ignore_permissions=True)
	frappe.db.commit()
	return settings


@frappe.whitelist()
def get_account_settings() -> dict:
	"""
	Get the current user's portal account settings.

	Returns all notification preferences and display preferences
	persisted in the ilL-Portal-User-Settings DocType.

	Returns:
		dict: {"success": True, "settings": { ... }}
	"""
	try:
		settings = _get_or_create_portal_settings()
		return {
			"success": True,
			"settings": {
				"notify_orders": bool(settings.notify_orders),
				"notify_quotes": bool(settings.notify_quotes),
				"notify_drawings": bool(settings.notify_drawings),
				"notify_shipping": bool(settings.notify_shipping),
				"notify_marketing": bool(settings.notify_marketing),
				"language": settings.language or "en",
				"units": settings.units or "imperial",
				"date_format": settings.date_format or "mm/dd/yyyy",
				"timezone": settings.timezone or "America/New_York",
			},
		}
	except Exception as e:
		frappe.log_error(f"Error getting account settings: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def save_notification_preferences(preferences: Union[str, dict]) -> dict:
	"""
	Save notification preferences for the current user.

	Persists to the ilL-Portal-User-Settings DocType so prefs are
	visible in /desk and survive cache clears.

	Args:
		preferences: Dict with notification preference booleans

	Returns:
		dict: {"success": True/False, "error": "message if error"}
	"""
	if isinstance(preferences, str):
		try:
			preferences = json.loads(preferences)
		except json.JSONDecodeError:
			return {"success": False, "error": "Invalid preferences format"}

	notification_fields = [
		"notify_orders", "notify_quotes", "notify_drawings",
		"notify_shipping", "notify_marketing",
	]

	try:
		settings = _get_or_create_portal_settings()
		for field in notification_fields:
			if field in preferences:
				setattr(settings, field, 1 if preferences[field] else 0)

		settings.save(ignore_permissions=True)
		frappe.db.commit()
		return {"success": True}
	except Exception as e:
		frappe.log_error(f"Error saving notification preferences: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def save_portal_preferences(preferences: Union[str, dict]) -> dict:
	"""
	Save display/locale preferences for the current user.

	Persists language, units, date_format, and timezone to the
	ilL-Portal-User-Settings DocType.

	Args:
		preferences: Dict with preference values

	Returns:
		dict: {"success": True/False, "error": "message if error"}
	"""
	if isinstance(preferences, str):
		try:
			preferences = json.loads(preferences)
		except json.JSONDecodeError:
			return {"success": False, "error": "Invalid preferences format"}

	preference_fields = ["language", "units", "date_format", "timezone"]

	try:
		settings = _get_or_create_portal_settings()
		for field in preference_fields:
			if field in preferences:
				setattr(settings, field, preferences[field])

		settings.save(ignore_permissions=True)
		frappe.db.commit()
		return {"success": True}
	except Exception as e:
		frappe.log_error(f"Error saving portal preferences: {str(e)}")
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

	# Validate access_level
	if access_level not in VALID_ACCESS_LEVELS:
		return {"success": False, "error": f"Invalid access_level. Must be one of: {', '.join(VALID_ACCESS_LEVELS)}"}

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
		try:
			contact_data = json.loads(contact_data)
		except json.JSONDecodeError:
			return {"success": False, "error": "Invalid contact_data format"}

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



@frappe.whitelist()
def get_contacts_for_project() -> dict:
	"""
	Get contacts that can be used in projects.

	Returns contacts that:
	1. System Manager: All contacts
	2. Non-System Manager: Contacts linked to the user's own customer
	   or linked to customers created by users at the user's company

	Returns:
		dict: {
			"success": True/False,
			"contacts": [{"name": contact_name, "first_name": str, "last_name": str, "company_name": str}]
		}
	"""
	try:
		from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
			_get_user_customer,
		)
		
		user_customer = _get_user_customer(frappe.session.user)
		
		# System Manager can access all contacts
		is_system_manager = "System Manager" in frappe.get_roles(frappe.session.user)
		
		contact_fields = ["name", "first_name", "last_name", "company_name", "email_id", "phone"]
		
		if is_system_manager:
			contacts = frappe.get_all(
				"Contact",
				fields=contact_fields,
				order_by="first_name asc",
				limit=1000
			)
		elif not user_customer:
			contacts = []
		else:
			# Get the allowed customers (same logic as get_allowed_customers_for_project)
			allowed_customer_names = set()
			allowed_customer_names.add(user_customer)

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

			# Get contacts linked to any of the allowed customers
			contacts = frappe.db.sql("""
				SELECT DISTINCT c.name, c.first_name, c.last_name,
					c.company_name, c.email_id, c.phone
				FROM `tabContact` c
				INNER JOIN `tabDynamic Link` dl ON dl.parent = c.name
					AND dl.parenttype = 'Contact'
					AND dl.link_doctype = 'Customer'
					AND dl.link_name IN %(allowed_customers)s
				ORDER BY c.first_name ASC
				LIMIT 1000
			""", {"allowed_customers": list(allowed_customer_names)}, as_dict=True)
		
		return {"success": True, "contacts": contacts}
		
	except Exception as e:
		frappe.log_error(f"Error getting contacts: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def create_contact(contact_data: Union[str, dict]) -> dict:
	"""
	Create a new contact.
	
	Args:
		contact_data: Dictionary containing contact information:
			- first_name (required)
			- last_name (optional)
			- email_id (optional)
			- phone (optional)
			- company_name (optional)
			- designation (optional)
	
	Returns:
		dict: {
			"success": True/False,
			"contact_name": str (contact name if successful),
			"error": str (if failed)
		}
	"""
	try:
		# Parse JSON if needed
		if isinstance(contact_data, str):
			contact_data = json.loads(contact_data)
		
		# Validate required fields
		if not contact_data.get("first_name"):
			return {"success": False, "error": "First name is required"}
		
		# Create contact
		contact = frappe.get_doc({
			"doctype": "Contact",
			"first_name": contact_data.get("first_name"),
			"last_name": contact_data.get("last_name"),
			"email_id": contact_data.get("email_id"),
			"phone": contact_data.get("phone"),
			"company_name": contact_data.get("company_name"),
			"designation": contact_data.get("designation")
		})
		
		# Add email to child table if provided
		if contact_data.get("email_id"):
			contact.append("email_ids", {
				"email_id": contact_data.get("email_id"),
				"is_primary": 1
			})
		
		# Add phone to child table if provided
		if contact_data.get("phone"):
			contact.append("phone_nos", {
				"phone": contact_data.get("phone"),
				"is_primary_phone": 1
			})
		
		contact.insert(ignore_permissions=False)
		frappe.db.commit()
		
		return {
			"success": True,
			"contact_name": contact.name
		}
		
	except frappe.DuplicateEntryError:
		return {"success": False, "error": "A contact with this information already exists"}
	except Exception as e:
		frappe.log_error(f"Error creating contact: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_configured_fixture_for_editing(configured_fixture_id: str) -> dict:
	"""
	Get the full configuration of an existing fixture for editing in the configurator.

	This returns all the user-selected options and segment data needed to
	pre-populate the configurator form so users can modify and re-validate
	the fixture before saving changes.

	Args:
		configured_fixture_id: ID of the ilL-Configured-Fixture

	Returns:
		dict: {
			"success": True/False,
			"configuration": {
				"fixture_template_code": str,
				"led_package_code": str,
				"environment_rating_code": str,
				"cct_code": str,
				"lens_appearance_code": str,
				"delivered_output_value": int,
				"mounting_method_code": str,
				"finish_code": str,
				"endcap_color_code": str,
				"segments": [...],  # User-defined segments
				"is_multi_segment": bool
			},
			"fixture_details": {...},  # Display info like part number, pricing
			"error": str (if failed)
		}
	"""
	if not frappe.db.exists("ilL-Configured-Fixture", configured_fixture_id):
		return {"success": False, "error": "Configured fixture not found"}

	try:
		cf = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_id)

		# Get option codes from linked doctypes
		configuration = {
			"fixture_template_code": cf.fixture_template,
			"is_multi_segment": cf.is_multi_segment or 0,
		}

		# Get LED package code from tape offering
		led_package_code = None
		cct_code = None
		output_level_value = None
		if cf.tape_offering:
			tape_data = frappe.db.get_value(
				"ilL-Rel-Tape Offering",
				cf.tape_offering,
				["led_package", "cct", "output_level"],
				as_dict=True,
			)
			if tape_data:
				if tape_data.led_package:
					led_package_code = frappe.db.get_value(
						"ilL-Attribute-LED Package", tape_data.led_package, "code"
					)
				if tape_data.cct:
					cct_code = frappe.db.get_value(
						"ilL-Attribute-CCT", tape_data.cct, "code"
					)
				if tape_data.output_level:
					output_level_value = frappe.db.get_value(
						"ilL-Attribute-Output Level", tape_data.output_level, "value"
					)

		configuration["led_package_code"] = led_package_code
		configuration["cct_code"] = cct_code

		# Calculate delivered output from tape output * lens transmission
		lens_transmission = 1.0
		lens_appearance_code = None
		if cf.lens_appearance:
			lens_data = frappe.db.get_value(
				"ilL-Attribute-Lens Appearance",
				cf.lens_appearance,
				["code", "transmission"],
				as_dict=True,
			)
			if lens_data:
				lens_appearance_code = lens_data.code
				if lens_data.transmission:
					lens_transmission = lens_data.transmission

		configuration["lens_appearance_code"] = lens_appearance_code

		# Calculate the delivered output value (what user selected)
		if output_level_value and lens_transmission:
			# Round to nearest 50 to match how options are presented
			delivered = output_level_value * lens_transmission
			delivered_rounded = round(delivered / 50) * 50
			configuration["delivered_output_value"] = int(delivered_rounded)
		else:
			configuration["delivered_output_value"] = cf.estimated_delivered_output

		# Get environment rating code
		if cf.environment_rating:
			configuration["environment_rating_code"] = frappe.db.get_value(
				"ilL-Attribute-Environment Rating", cf.environment_rating, "code"
			)
		else:
			configuration["environment_rating_code"] = None

		# Get mounting method code
		if cf.mounting_method:
			configuration["mounting_method_code"] = frappe.db.get_value(
				"ilL-Attribute-Mounting Method", cf.mounting_method, "code"
			)
		else:
			configuration["mounting_method_code"] = None

		# Get finish code
		if cf.finish:
			configuration["finish_code"] = frappe.db.get_value(
				"ilL-Attribute-Finish", cf.finish, "code"
			)
		else:
			configuration["finish_code"] = None

		# Get endcap color code
		if cf.endcap_color:
			configuration["endcap_color_code"] = frappe.db.get_value(
				"ilL-Attribute-Endcap Color", cf.endcap_color, "code"
			)
		else:
			configuration["endcap_color_code"] = None

		# Get power feed type code (for single segment fixtures)
		if cf.power_feed_type:
			configuration["power_feed_type_code"] = frappe.db.get_value(
				"ilL-Attribute-Power Feed Type", cf.power_feed_type, "code"
			)
		else:
			configuration["power_feed_type_code"] = None

		# Build segments data from user_segments child table
		segments = []
		if cf.user_segments:
			for seg in cf.user_segments:
				segment_data = {
					"segment_index": seg.segment_index,
					"requested_length_mm": seg.requested_length_mm,
					"end_type": seg.end_type,
				}

				# Get power feed type code for start
				if seg.start_power_feed_type:
					segment_data["start_power_feed_type"] = frappe.db.get_value(
						"ilL-Attribute-Power Feed Type", seg.start_power_feed_type, "code"
					) or seg.start_power_feed_type
				else:
					segment_data["start_power_feed_type"] = None

				# Get feed direction for start
				segment_data["start_feed_direction"] = getattr(seg, "start_feed_direction", None) or None

				segment_data["start_leader_cable_length_mm"] = seg.start_leader_cable_length_mm or 300

				# Get end power feed type code (for jumpers)
				if seg.end_type == "Jumper" and seg.end_power_feed_type:
					segment_data["end_power_feed_type"] = frappe.db.get_value(
						"ilL-Attribute-Power Feed Type", seg.end_power_feed_type, "code"
					) or seg.end_power_feed_type
					segment_data["end_jumper_cable_length_mm"] = seg.end_jumper_cable_length_mm or 300
					segment_data["end_feed_direction"] = getattr(seg, "end_feed_direction", None) or None
				else:
					segment_data["end_power_feed_type"] = None
					segment_data["end_jumper_cable_length_mm"] = None
					segment_data["end_feed_direction"] = None

				segments.append(segment_data)
		else:
			# Single segment fixture - build from fixture-level data
			segment_data = {
				"segment_index": 1,
				"requested_length_mm": cf.requested_overall_length_mm,
				"end_type": "Endcap",
				"start_power_feed_type": configuration.get("power_feed_type_code"),
				"start_leader_cable_length_mm": 300,  # Default
			}
			segments.append(segment_data)

		configuration["segments"] = segments

		# Build fixture details for display
		fixture_details = {
			"config_hash": cf.config_hash,
			"part_number": cf.configured_item or cf.name,
			"manufacturable_length_mm": cf.manufacturable_overall_length_mm,
			"manufacturable_length_in": round(cf.manufacturable_overall_length_mm / 25.4, 1) if cf.manufacturable_overall_length_mm else None,
			"requested_length_mm": cf.requested_overall_length_mm,
			"requested_length_in": round(cf.requested_overall_length_mm / 25.4, 1) if cf.requested_overall_length_mm else None,
			"total_watts": cf.total_watts,
			"estimated_delivered_output": cf.estimated_delivered_output,
			"runs_count": cf.runs_count,
			"user_segment_count": cf.user_segment_count or 1,
			"assembly_mode": cf.assembly_mode,
			"build_description": cf.build_description,
		}

		return {
			"success": True,
			"configuration": configuration,
			"fixture_details": fixture_details,
		}

	except Exception as e:
		frappe.log_error(f"Error getting fixture configuration: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def update_configured_fixture_on_schedule(
	schedule_name: str,
	line_idx: int,
	new_configured_fixture_id: str,
	manufacturable_length_mm: int,
) -> dict:
	"""
	Update a schedule line with a new/modified configured fixture.

	This is called after the user has re-validated their fixture modifications
	and wants to save the changes back to the schedule line.

	Args:
		schedule_name: Name of the schedule
		line_idx: Index of the line to update
		new_configured_fixture_id: ID of the new/modified configured fixture
		manufacturable_length_mm: Manufacturable length from validation

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
		return {"success": False, "error": "Permission denied"}

	# Check schedule status allows editing
	if schedule.status not in ["DRAFT", "READY"]:
		return {"success": False, "error": "Cannot edit lines in a schedule in this status"}

	# Validate line_idx
	try:
		line_idx = int(line_idx)
	except (ValueError, TypeError):
		return {"success": False, "error": "Invalid line index"}

	if line_idx < 0 or line_idx >= len(schedule.lines):
		return {"success": False, "error": "Invalid line index"}

	# Validate the new configured fixture exists
	if not frappe.db.exists("ilL-Configured-Fixture", new_configured_fixture_id):
		return {"success": False, "error": "Configured fixture not found"}

	try:
		line = schedule.lines[line_idx]

		# Ensure it's an ILLUMENATE line
		if line.manufacturer_type != "ILLUMENATE":
			return {"success": False, "error": "Can only update ILLUMENATE fixture lines"}

		# Update the line with the new configured fixture
		line.configured_fixture = new_configured_fixture_id
		line.manufacturable_length_mm = int(manufacturable_length_mm)

		# Get the configured fixture document to update item code
		configured_fixture = frappe.get_doc("ilL-Configured-Fixture", new_configured_fixture_id)

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
		frappe.db.commit()

		return {"success": True}

	except Exception as e:
		frappe.log_error(f"Error updating fixture on schedule: {str(e)}")
		return {"success": False, "error": str(e)}
