# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe

from illumenate_lighting.illumenate_lighting.api.unit_conversion import convert_build_description_to_inches

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

	# If user can view pricing, pre-fetch pricing data for configured fixtures
	pricing_map = {}  # configured_fixture_id -> unit_price
	ctn_pricing_map = {}  # configured_tape_neon_id -> unit_price
	schedule_total = 0.0
	if can_view_pricing:
		# Collect all configured fixture IDs for batch pricing lookup
		cf_ids = [
			line.configured_fixture for line in lines
			if line.manufacturer_type == "ILLUMENATE" and line.configured_fixture
		]
		if cf_ids:
			# Batch fetch all pricing snapshots in a single query
			all_snapshots = frappe.get_all(
				"ilL-Child-Pricing-Snapshot",
				filters={"parent": ["in", cf_ids], "parenttype": "ilL-Configured-Fixture"},
				fields=["parent", "msrp_unit", "timestamp"],
				order_by="timestamp desc",
			)
			# Pick the latest snapshot per parent
			for snap in all_snapshots:
				if snap.parent not in pricing_map and snap.msrp_unit:
					pricing_map[snap.parent] = float(snap.msrp_unit)

		# Collect all configured tape/neon IDs for batch pricing lookup
		ctn_ids = [
			line.configured_tape_neon for line in lines
			if line.manufacturer_type == "ILLUMENATE" and line.configured_tape_neon
		]
		if ctn_ids:
			ctn_snapshots = frappe.get_all(
				"ilL-Child-Pricing-Snapshot",
				filters={"parent": ["in", ctn_ids], "parenttype": "ilL-Configured-Tape-Neon"},
				fields=["parent", "msrp_unit", "timestamp"],
				order_by="timestamp desc",
			)
			for snap in ctn_snapshots:
				if snap.parent not in ctn_pricing_map and snap.msrp_unit:
					ctn_pricing_map[snap.parent] = float(snap.msrp_unit)

	# Batch-fetch stock availability for all configured fixtures (Phase 3 - Stock Level Visibility)
	from illumenate_lighting.illumenate_lighting.api.pricing_utils import (
		batch_stock_for_fixtures,
		get_bom_stock_for_items,
	)
	stock_cf_ids = [
		line.configured_fixture for line in lines
		if line.manufacturer_type == "ILLUMENATE" and line.configured_fixture
	]
	fixture_stock_map = batch_stock_for_fixtures(stock_cf_ids) if stock_cf_ids else {}

	# Batch-fetch stock for accessory items
	accessory_items_for_stock = [
		{"item_code": line.accessory_item, "qty": line.qty or 1}
		for line in lines
		if line.manufacturer_type == "ACCESSORY" and line.accessory_item
	]
	accessory_stock_result = get_bom_stock_for_items(accessory_items_for_stock) if accessory_items_for_stock else {"items": []}
	# Build a lookup: item_code -> stock entry
	accessory_stock_map = {}
	for idx, entry in enumerate(accessory_stock_result.get("items", [])):
		accessory_stock_map[entry.get("item_code", "")] = entry

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
			# ilLumenate fixture fields
			"product_type": line.product_type,
			"configuration_status": getattr(line, "configuration_status", None),
			"kit_template": getattr(line, "kit_template", None),
			"fixture_template": line.fixture_template,
			"fixture_template_name": None,  # Will be populated below
			# Tape/Neon fields
			"tape_neon_template": line.tape_neon_template,
			"tape_neon_template_name": None,  # Will be populated below
			"tape_neon_template_code": None,  # Will be populated below
			"tape_neon_template_description": "",  # Will be populated below
			"configured_tape_neon": line.configured_tape_neon,
			"ctn_details": {},  # Configured tape/neon details
			# Accessory/Component fields
			"accessory_product_type": line.accessory_product_type,
			"accessory_item": line.accessory_item,
			"accessory_item_name": line.accessory_item_name,
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

		# For ilLumenate fixtures with a fixture template, fetch the template name
		if line.manufacturer_type == "ILLUMENATE" and line.fixture_template:
			template_name = frappe.db.get_value(
				"ilL-Fixture-Template",
				line.fixture_template,
				"template_name"
			)
			if template_name:
				line_dict["fixture_template_name"] = template_name

		# For ilLumenate tape/neon lines, fetch template name/code/description and configured details
		if line.manufacturer_type == "ILLUMENATE" and line.tape_neon_template:
			tn_fields = frappe.db.get_value(
				"ilL-Tape-Neon-Template",
				line.tape_neon_template,
				["template_name", "template_code", "description"],
				as_dict=True,
			)
			if tn_fields:
				line_dict["tape_neon_template_name"] = tn_fields.template_name
				line_dict["tape_neon_template_code"] = tn_fields.template_code
				line_dict["tape_neon_template_description"] = tn_fields.description or ""

		# For configured tape/neon, fetch display details
		if line.manufacturer_type == "ILLUMENATE" and line.configured_tape_neon:
			ctn_details = _get_configured_tape_neon_display_details(line.configured_tape_neon)
			line_dict["ctn_details"] = ctn_details

		# For accessory/component items, fetch item description
		if line.manufacturer_type == "ACCESSORY" and line.accessory_item:
			item_desc = frappe.db.get_value(
				"Item",
				line.accessory_item,
				["description", "item_name"],
				as_dict=True
			)
			if item_desc:
				line_dict["accessory_item_description"] = item_desc.description or ""
				# Update item name if not set
				if not line_dict.get("accessory_item_name"):
					line_dict["accessory_item_name"] = item_desc.item_name

			# Parse variant_selections JSON if present
			variant_selections_raw = getattr(line, "variant_selections", None)
			if variant_selections_raw:
				import json as _json
				try:
					line_dict["variant_selections"] = _json.loads(variant_selections_raw)
				except (ValueError, TypeError):
					line_dict["variant_selections"] = {}

		# Parse variant_selections for Extrusion Kit lines to extract display selections
		if getattr(line, "product_type", None) == "Extrusion Kit":
			import json as _json
			vs_raw = getattr(line, "variant_selections", None)
			if vs_raw:
				try:
					vs_data = _json.loads(vs_raw) if isinstance(vs_raw, str) else vs_raw
					line_dict["kit_selections"] = vs_data.get("selections", {})
					line_dict["kit_part_number"] = vs_data.get("part_number", "")
					line_dict["kit_build_description"] = vs_data.get("build_description", "")
				except (ValueError, TypeError):
					pass

		# Populate pricing if user can view pricing
		if can_view_pricing:
			unit_price = None
			if line.manufacturer_type == "ILLUMENATE" and line.configured_fixture:
				unit_price = pricing_map.get(line.configured_fixture)
			elif line.manufacturer_type == "ILLUMENATE" and line.configured_tape_neon:
				unit_price = ctn_pricing_map.get(line.configured_tape_neon)
				# Fallback: read from variant_selections when snapshot pricing is missing
				if not unit_price:
					unit_price = _get_msrp_from_variant_selections(line)
			elif getattr(line, "product_type", None) in ("LED Tape", "LED Neon") and getattr(line, "tape_neon_template", None):
				# Tape/neon template line without configured record – read from variant_selections
				unit_price = _get_msrp_from_variant_selections(line)
			elif getattr(line, "product_type", None) == "Extrusion Kit":
				# Kit pricing stored in variant_selections JSON
				vs_raw = getattr(line, "variant_selections", None)
				if vs_raw:
					import json as _json_kit
					try:
						vs_data = _json_kit.loads(vs_raw) if isinstance(vs_raw, str) else vs_raw
						kit_pricing = vs_data.get("pricing", {})
						kit_msrp = kit_pricing.get("total_price_msrp")
						if kit_msrp:
							unit_price = float(kit_msrp)
					except (ValueError, TypeError):
						pass
			elif line.manufacturer_type == "ACCESSORY" and line.accessory_item:
				item_price = frappe.db.get_value(
					"Item Price",
					{"item_code": line.accessory_item, "price_list": "Standard Selling", "selling": 1},
					"price_list_rate",
				)
				if item_price:
					unit_price = float(item_price)

			if unit_price:
				line_dict["unit_price"] = unit_price
				line_dict["line_total"] = unit_price * (line.qty or 1)
				schedule_total += line_dict["line_total"]

			# Add driver MSRP as separate sub-line pricing for ilLumenate fixtures
			if line.manufacturer_type == "ILLUMENATE" and line.configured_fixture:
				driver_msrp = line_dict.get("cf_details", {}).get("driver_msrp_unit")
				if driver_msrp:
					line_dict["driver_unit_price"] = driver_msrp
					line_dict["driver_line_total"] = driver_msrp * (line.qty or 1)
					schedule_total += line_dict["driver_line_total"]

		# Attach stock availability
		if line.manufacturer_type == "ILLUMENATE" and line.configured_fixture:
			line_dict["stock_availability"] = fixture_stock_map.get(line.configured_fixture, {})
		elif getattr(line, "product_type", None) == "Extrusion Kit":
			kit_stock = _compute_kit_stock_for_line(line, is_dealer or is_internal)
			if kit_stock:
				line_dict["stock_availability"] = kit_stock
		elif line.manufacturer_type == "ACCESSORY" and line.accessory_item:
			acc_stock = accessory_stock_map.get(line.accessory_item)
			if acc_stock:
				line_dict["stock_availability"] = {
					"all_in_stock": acc_stock.get("is_sufficient", False),
					"items": [acc_stock],
				}

		lines_with_details.append(line_dict)
		lines_json.append(line_dict)

	# Schedule-level stock summary
	stock_lines_total = sum(
		1 for ld in lines_with_details
		if ld.get("stock_availability")
	)
	stock_lines_in_stock = sum(
		1 for ld in lines_with_details
		if ld.get("stock_availability", {}).get("all_in_stock")
	)

	context.schedule = schedule
	context.schedule_total = schedule_total
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
	context.stock_lines_total = stock_lines_total
	context.stock_lines_in_stock = stock_lines_in_stock
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
		frappe.log_error(
			message=f"Fixture ID: {configured_fixture_id}",
			title="Missing Configured Fixture"
		)
		return {}

	try:
		cf = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_id)

		# Calculate length in inches
		length_mm = cf.manufacturable_overall_length_mm or 0
		length_inches = length_mm / 25.4 if length_mm else 0
		
		# Get fixture template code and name for SPEC display
		fixture_template_code = cf.fixture_template or None
		fixture_template_name = None
		if fixture_template_code:
			fixture_template_name = frappe.db.get_value(
				"ilL-Fixture-Template",
				fixture_template_code,
				"template_name"
			)

		details = {
			"part_number": cf.configured_item or cf.config_hash,
			"fixture_template_code": fixture_template_code,
			"fixture_template_name": fixture_template_name,
			"environment_rating": cf.environment_rating if hasattr(cf, "environment_rating") else None,
			"mounting_method": cf.mounting_method if hasattr(cf, "mounting_method") else None,
			"power_feed_type": cf.power_feed_type if hasattr(cf, "power_feed_type") else None,
			"finish": None,
			"lens_appearance": None,
			"cct": None,
			"cri": None,
			"led_package": None,
			"output_level": None,
			"estimated_delivered_output": cf.estimated_delivered_output if hasattr(cf, "estimated_delivered_output") else None,
			"include_power_supply": getattr(cf, "include_power_supply", 1),
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
			"build_description_display": convert_build_description_to_inches(cf.build_description if hasattr(cf, "build_description") else ""),
			"total_endcaps": cf.total_endcaps if hasattr(cf, "total_endcaps") else 0,
			"total_mounting_accessories": cf.total_mounting_accessories if hasattr(cf, "total_mounting_accessories") else 0,
		}

		# Get finish display name
		if cf.finish:
			finish_doc = frappe.db.get_value(
				"ilL-Attribute-Finish",
				cf.finish,
				["code", "finish_name"],
				as_dict=True,
			)
			if finish_doc:
				details["finish"] = finish_doc.finish_name or finish_doc.code or cf.finish
			else:
				# Fallback to raw value
				details["finish"] = cf.finish

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
			else:
				# Fallback to raw value
				details["lens_appearance"] = cf.lens_appearance

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
					else:
						details["cri"] = tape_offering.cri
				
				# Get fixture input voltage from tape spec
				if tape_offering.tape_spec:
					tape_spec_data = frappe.db.get_value(
						"ilL-Spec-LED Tape",
						tape_offering.tape_spec,
						["input_voltage"],
						as_dict=True,
					)
					if tape_spec_data and tape_spec_data.input_voltage:
						details["fixture_input_voltage"] = tape_spec_data.input_voltage

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
						# (for older fixtures that don't have the field populated)
						if not details["estimated_delivered_output"] and output_level_doc.value:
							delivered = output_level_doc.value * lens_transmission
							details["estimated_delivered_output"] = round(delivered, 1)
						else:
							# Fallback to raw value
							details["output_level"] = tape_offering.output_level
			else:
				# Tape offering doc not found - try to parse CCT from tape_offering name
				# Format is typically: LED-HD-SW-I-30K-750-3M-WH
				# Try to extract CCT (e.g., "30K")
				import re
				cct_match = re.search(r'(\d{2}K)', cf.tape_offering)
				if cct_match:
					details["cct"] = cct_match.group(1)

		# Get driver/power supply info from drivers child table
		if cf.drivers:
			driver_items = []
			driver_input_voltages = []
			total_driver_qty = 0
			driver_msrp_total = 0.0
			for driver_alloc in cf.drivers:
				if driver_alloc.driver_item:
					# driver_alloc.driver_item is the Item code (ID)
					# Find the ilL-Spec-Driver linked to this Item
					driver_spec = frappe.db.get_value(
						"ilL-Spec-Driver",
						{"item": driver_alloc.driver_item},
						["input_voltage", "max_wattage"],
						as_dict=True,
					)

					# Build driver display string with ID and quantity in parentheses
					driver_qty = driver_alloc.driver_qty or 1
					total_driver_qty += driver_qty
					# Use the item code (driver_alloc.driver_item) as the display ID
					if driver_qty > 1:
						driver_items.append(f"{driver_alloc.driver_item} ({driver_qty})")
					else:
						driver_items.append(driver_alloc.driver_item)

					# Get input voltage from driver spec
					if driver_spec and driver_spec.input_voltage:
						driver_input_voltages.append(driver_spec.input_voltage)

					# Look up driver MSRP from Item Price
					driver_price = frappe.db.get_value(
						"Item Price",
						{"item_code": driver_alloc.driver_item, "price_list": "Standard Selling", "selling": 1},
						"price_list_rate",
					)
					if driver_price:
						driver_msrp_total += float(driver_price) * driver_qty

			if driver_items:
				details["power_supply"] = ", ".join(driver_items)
				details["power_supply_qty"] = total_driver_qty
			if driver_input_voltages:
				# Remove duplicates and join
				unique_voltages = list(dict.fromkeys(driver_input_voltages))
				details["driver_input_voltage"] = ", ".join(unique_voltages)
			if driver_msrp_total > 0:
				details["driver_msrp_unit"] = round(driver_msrp_total, 2)

		return details
	except Exception as e:
		frappe.log_error(
			message=f"Fixture: {configured_fixture_id}\nError: {str(e)}",
			title="Schedule Display Error"
		)
		return {}


def _get_msrp_from_variant_selections(line):
	"""Extract total_price_msrp from a schedule line's variant_selections JSON.

	Checks ``pricing.total_price_msrp`` first, then falls back to
	``computed.total_price_msrp``.  Returns ``None`` when unavailable.
	"""
	vs_raw = getattr(line, "variant_selections", None)
	if not vs_raw:
		return None
	import json as _json_vs
	try:
		vs_data = _json_vs.loads(vs_raw) if isinstance(vs_raw, str) else vs_raw
		msrp = (vs_data.get("pricing") or {}).get("total_price_msrp")
		if not msrp:
			msrp = (vs_data.get("computed") or {}).get("total_price_msrp")
		return float(msrp) if msrp else None
	except (ValueError, TypeError):
		return None


def _get_configured_tape_neon_display_details(configured_tape_neon_id):
	"""
	Get display-ready details for a configured tape/neon product.

	Returns dict with computed values for portal display.
	"""
	if not frappe.db.exists("ilL-Configured-Tape-Neon", configured_tape_neon_id):
		frappe.log_error(
			message=f"Tape/Neon ID: {configured_tape_neon_id}",
			title="Missing Configured Tape/Neon"
		)
		return {}

	try:
		ctn = frappe.get_doc("ilL-Configured-Tape-Neon", configured_tape_neon_id)

		# Calculate length in inches
		length_mm = ctn.manufacturable_length_mm or 0
		length_inches = length_mm / 25.4 if length_mm else 0

		details = {
			"part_number": ctn.part_number or ctn.config_hash,
			"product_category": ctn.product_category,
			"tape_neon_template": ctn.tape_neon_template,
			"cct": ctn.cct,
			"output_level": ctn.output_level,
			"environment_rating": ctn.environment_rating,
			"mounting_method": ctn.mounting_method,
			"finish": ctn.finish,
			"pcb_mounting": ctn.pcb_mounting,
			"pcb_finish": ctn.pcb_finish,
			"feed_type": ctn.feed_type,
			"total_watts": ctn.total_watts,
			"watts_per_foot": ctn.watts_per_foot,
			"total_segments": ctn.total_segments,
			"assembly_mode": ctn.assembly_mode,
			"build_description": ctn.build_description,
			"manufacturable_length_mm": length_mm,
			"manufacturable_length_inches": round(length_inches, 1) if length_inches else None,
		}

		return details
	except Exception as e:
		frappe.log_error(
			message=f"Tape/Neon: {configured_tape_neon_id}\nError: {str(e)}",
			title="Schedule Display Error"
		)
		return {}


def _compute_kit_stock_for_line(line, show_qty: bool) -> dict | None:
	"""
	Compute stock availability for an Extrusion Kit schedule line.

	Extracts attribute selections from the line's ``variant_selections`` JSON,
	resolves kit components via ``get_kit_component_stock``, and transforms
	the result into the standard ``stock_availability`` format used by the
	schedule template.

	Args:
		line: Child table row from ilL-Project-Fixture-Schedule.
		show_qty: Whether to include numeric quantities (for dealers/internal).

	Returns:
		dict matching the ``stock_availability`` shape, or None if resolution fails.
	"""
	import json as _json

	vs_raw = getattr(line, "variant_selections", None)
	if not vs_raw:
		return None

	try:
		vs = _json.loads(vs_raw) if isinstance(vs_raw, str) else vs_raw
	except (ValueError, TypeError):
		return None

	selections = vs.get("selections", {})
	kt = (
		selections.get("kit_template")
		or getattr(line, "kit_template", None)
	)
	if not kt:
		return None

	from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
		get_kit_component_stock,
	)

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

	components = stock_result.get("components", [])
	all_in_stock = all(c.get("in_stock", False) for c in components)

	items = []
	for c in components:
		entry = {
			"item_code": c.get("item_code") or "",
			"item_name": c.get("item_name") or "",
			"component_type": c.get("component", ""),
			"is_sufficient": c.get("in_stock", False),
			"lead_time_class": c.get("lead_time_class", ""),
		}
		if show_qty:
			entry["qty_required"] = c.get("qty_per_kit", 0)
			entry["qty_available"] = c.get("stock_qty", 0)
		items.append(entry)

	return {"all_in_stock": all_in_stock, "items": items}
