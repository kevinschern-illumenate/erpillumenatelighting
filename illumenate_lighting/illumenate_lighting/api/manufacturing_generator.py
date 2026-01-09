# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Manufacturing Artifacts Generator

This module provides APIs to generate manufacturing artifacts (Item, BOM, Work Order)
from a Configured Fixture. It implements:

- Epic 2: Configured Item generation (ILL-... code + reuse rules)
- Epic 3: BOM generation with BOM roles
- Epic 5: Work Order creation with operations + traveler notes
- Epic 6: Workflow trigger points (idempotency)
- Epic 7: Serial/Batch MVP wiring setup

API Endpoints:
- generate_manufacturing_artifacts: Main entry point to create Item/BOM/WO from configured fixture
- generate_from_sales_order: Generate artifacts for all configured fixtures on a Sales Order
"""

import math
from typing import Any, Optional

import frappe
from frappe import _

# Engine version for tracking
ENGINE_VERSION = "1.0.0"

# Item group for configured fixtures
CONFIGURED_ITEM_GROUP = "Configured Fixtures"

# Default UOM for configured fixtures
DEFAULT_UOM = "Nos"

# Operations template for work orders (MVP)
OPERATIONS_TEMPLATE = [
	{"operation": "Cut Profile", "workstation": "Cutting Station", "time_in_mins": 15},
	{"operation": "Cut Lens", "workstation": "Cutting Station", "time_in_mins": 10},
	{"operation": "Cut Tape", "workstation": "Cutting Station", "time_in_mins": 10},
	{"operation": "Solder/Terminate", "workstation": "Assembly Station", "time_in_mins": 20},
	{"operation": "Assemble", "workstation": "Assembly Station", "time_in_mins": 30},
	{"operation": "Test", "workstation": "Test Station", "time_in_mins": 15},
	{"operation": "Label", "workstation": "Packaging Station", "time_in_mins": 5},
	{"operation": "Pack", "workstation": "Packaging Station", "time_in_mins": 10},
	{"operation": "Ship", "workstation": "Shipping Station", "time_in_mins": 5},
]


@frappe.whitelist()
def generate_manufacturing_artifacts(
	configured_fixture_id: str,
	qty: int = 1,
	skip_if_exists: bool = True,
) -> dict[str, Any]:
	"""
	Generate manufacturing artifacts (Item, BOM, Work Order) for a Configured Fixture.

	This is the main entry point for manufacturing artifact generation. It implements:
	- Epic 2: Configured Item generation with ILL-... naming
	- Epic 3: BOM generation with all component roles
	- Epic 5: Work Order with operations and traveler notes
	- Epic 6: Idempotency (skip/warn if artifacts exist)

	Args:
		configured_fixture_id: Name of the ilL-Configured-Fixture document
		qty: Quantity to manufacture (default: 1)
		skip_if_exists: If True, skip creation if artifacts already exist (default: True)

	Returns:
		dict: Response with created/existing artifact references and status messages
	"""
	try:
		qty = int(qty)
	except (ValueError, TypeError):
		qty = 1

	response = {
		"success": True,
		"messages": [],
		"item_code": None,
		"bom_name": None,
		"work_order_name": None,
		"created": {"item": False, "bom": False, "work_order": False},
		"skipped": {"item": False, "bom": False, "work_order": False},
	}

	# Validate configured fixture exists
	if not frappe.db.exists("ilL-Configured-Fixture", configured_fixture_id):
		response["success"] = False
		response["messages"].append({
			"severity": "error",
			"text": f"Configured Fixture '{configured_fixture_id}' not found",
		})
		return response

	fixture = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_id)

	# Step 1: Create or get configured Item (Epic 2)
	item_result = _create_or_get_configured_item(fixture, skip_if_exists)
	response["item_code"] = item_result["item_code"]
	response["messages"].extend(item_result["messages"])
	response["created"]["item"] = item_result["created"]
	response["skipped"]["item"] = item_result["skipped"]

	if not item_result["success"]:
		response["success"] = False
		return response

	# Step 2: Create or get BOM (Epic 3)
	bom_result = _create_or_get_bom(fixture, item_result["item_code"], skip_if_exists)
	response["bom_name"] = bom_result["bom_name"]
	response["messages"].extend(bom_result["messages"])
	response["created"]["bom"] = bom_result["created"]
	response["skipped"]["bom"] = bom_result["skipped"]

	if not bom_result["success"]:
		response["success"] = False
		return response

	# Step 3: Create or get Work Order (Epic 5)
	wo_result = _create_or_get_work_order(
		fixture, item_result["item_code"], bom_result["bom_name"], qty, skip_if_exists
	)
	response["work_order_name"] = wo_result["work_order_name"]
	response["messages"].extend(wo_result["messages"])
	response["created"]["work_order"] = wo_result["created"]
	response["skipped"]["work_order"] = wo_result["skipped"]

	if not wo_result["success"]:
		response["success"] = False
		return response

	# Update configured fixture with links (Epic 6)
	_update_fixture_links(fixture, item_result["item_code"], bom_result["bom_name"], wo_result["work_order_name"])

	response["messages"].append({
		"severity": "info",
		"text": f"Manufacturing artifacts generated successfully for {configured_fixture_id}",
	})

	return response


@frappe.whitelist()
def generate_from_sales_order(sales_order: str) -> dict[str, Any]:
	"""
	Generate manufacturing artifacts for all configured fixtures on a Sales Order.

	Implements Epic 6 Task 6.1: Button on Sales Order to generate Item/BOM/WO.

	Args:
		sales_order: Name of the Sales Order document

	Returns:
		dict: Response with results for each line item
	"""
	response = {
		"success": True,
		"messages": [],
		"results": [],
	}

	if not frappe.db.exists("Sales Order", sales_order):
		response["success"] = False
		response["messages"].append({
			"severity": "error",
			"text": f"Sales Order '{sales_order}' not found",
		})
		return response

	so_doc = frappe.get_doc("Sales Order", sales_order)

	# Process each line item with a configured fixture
	processed_count = 0
	for item in so_doc.items:
		# Check if this line has a configured fixture
		configured_fixture_id = item.get("ill_configured_fixture")
		if not configured_fixture_id:
			continue

		# Generate artifacts for this fixture
		result = generate_manufacturing_artifacts(
			configured_fixture_id=configured_fixture_id,
			qty=item.qty or 1,
			skip_if_exists=True,
		)

		response["results"].append({
			"idx": item.idx,
			"item_code": item.item_code,
			"configured_fixture_id": configured_fixture_id,
			"result": result,
		})

		if not result["success"]:
			response["success"] = False

		processed_count += 1

	if processed_count == 0:
		response["messages"].append({
			"severity": "warning",
			"text": "No configured fixtures found on this Sales Order",
		})
	else:
		response["messages"].append({
			"severity": "info",
			"text": f"Processed {processed_count} configured fixtures",
		})

	return response


def on_sales_order_submit(doc, method):
	"""
	Hook called when a Sales Order is submitted.
	Automatically generates manufacturing artifacts (Item, BOM, Work Order)
	for all configured fixtures on the Sales Order.

	Args:
		doc: The Sales Order document being submitted
		method: The hook method name (on_submit)
	"""
	# Check if any line items have configured fixtures
	has_configured_fixtures = False
	for item in doc.items:
		if item.get("ill_configured_fixture"):
			has_configured_fixtures = True
			break

	if not has_configured_fixtures:
		return

	# Generate manufacturing artifacts
	result = generate_from_sales_order(doc.name)

	if not result["success"]:
		# Log errors but don't block submission
		error_messages = [
			msg["text"] for msg in result.get("messages", [])
			if msg.get("severity") == "error"
		]
		if error_messages:
			frappe.log_error(
				title=f"Manufacturing Generation Errors for {doc.name}",
				message="\n".join(error_messages)
			)
			frappe.msgprint(
				_("Some manufacturing artifacts could not be generated. Check Error Log for details."),
				indicator="orange",
				alert=True
			)
	else:
		# Success message
		created_count = sum(
			1 for r in result.get("results", [])
			if r.get("result", {}).get("created", {}).get("work_order")
		)
		if created_count > 0:
			frappe.msgprint(
				_(f"Created {created_count} Work Order(s) for configured fixtures."),
				indicator="green",
				alert=True
			)


def _create_or_get_configured_item(
	fixture,
	skip_if_exists: bool = True,
) -> dict[str, Any]:
	"""
	Create or retrieve configured Item for a fixture (Epic 2).

	Item naming convention: ILL-{config_hash_short}
	Where config_hash_short is the first 8 characters of the config_hash.

	Args:
		fixture: ilL-Configured-Fixture document
		skip_if_exists: If True, return existing item without modification

	Returns:
		dict: {"success": bool, "item_code": str, "created": bool, "skipped": bool, "messages": list}
	"""
	result = {
		"success": True,
		"item_code": None,
		"created": False,
		"skipped": False,
		"messages": [],
	}

	# Check if fixture already has a configured item
	if fixture.configured_item and skip_if_exists:
		if frappe.db.exists("Item", fixture.configured_item):
			result["item_code"] = fixture.configured_item
			result["skipped"] = True
			result["messages"].append({
				"severity": "info",
				"text": f"Using existing configured Item: {fixture.configured_item}",
			})
			return result

	# Use the fixture name (part number) as the item code
	# The fixture name is now formatted as: ILL-{Profile}-{LED}-{CCT}-{Output}-{Lens}-{Mount}-{Finish}-{Length}
	item_code = fixture.name

	# Check if item already exists
	if frappe.db.exists("Item", item_code):
		if skip_if_exists:
			result["item_code"] = item_code
			result["skipped"] = True
			result["messages"].append({
				"severity": "info",
				"text": f"Using existing Item: {item_code}",
			})
			return result
		else:
			# Update existing item
			result["item_code"] = item_code
			result["messages"].append({
				"severity": "info",
				"text": f"Item {item_code} already exists, updating",
			})
			return result

	# Generate friendly item name
	template_name = frappe.db.get_value(
		"ilL-Fixture-Template", fixture.fixture_template, "template_name"
	) or fixture.fixture_template

	length_mm = fixture.manufacturable_overall_length_mm or fixture.requested_overall_length_mm or 0
	item_name = (
		f"{template_name} - "
		f"{fixture.finish or 'STD'} - "
		f"{fixture.lens_appearance or 'STD'} - "
		f"{length_mm}mm"
	)

	# Ensure item group exists
	_ensure_item_group_exists(CONFIGURED_ITEM_GROUP)

	# Create the Item
	try:
		item_doc = frappe.get_doc({
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_name,
			"item_group": CONFIGURED_ITEM_GROUP,
			"stock_uom": DEFAULT_UOM,
			"is_stock_item": 1,
			"has_serial_no": 1,  # Epic 7: Enable serial tracking for finished goods
			"description": _generate_item_description(fixture),
			"custom_ill_configured_fixture": fixture.name,  # Link back to fixture
		})
		item_doc.insert(ignore_permissions=True)

		result["item_code"] = item_code
		result["created"] = True
		result["messages"].append({
			"severity": "info",
			"text": f"Created configured Item: {item_code}",
		})

	except Exception as e:
		result["success"] = False
		result["messages"].append({
			"severity": "error",
			"text": f"Failed to create Item: {e!s}",
		})

	return result


def _create_or_get_bom(
	fixture,
	item_code: str,
	skip_if_exists: bool = True,
) -> dict[str, Any]:
	"""
	Create or retrieve BOM for a configured fixture (Epic 3).

	BOM roles implemented:
	- Profile (stock sticks + cut instructions)
	- Lens (sticks)
	- Endcaps (2 + extra pair rule = 4 total)
	- Mounting accessories (qty rule)
	- LED tape (total length in UOM)
	- Leader cables (qty = runs)
	- Drivers (from driver plan)

	Args:
		fixture: ilL-Configured-Fixture document
		item_code: The configured item code
		skip_if_exists: If True, return existing BOM without modification

	Returns:
		dict: {"success": bool, "bom_name": str, "created": bool, "skipped": bool, "messages": list}
	"""
	result = {
		"success": True,
		"bom_name": None,
		"created": False,
		"skipped": False,
		"messages": [],
	}

	# Check if fixture already has a BOM
	if fixture.bom and skip_if_exists:
		if frappe.db.exists("BOM", fixture.bom):
			result["bom_name"] = fixture.bom
			result["skipped"] = True
			result["messages"].append({
				"severity": "info",
				"text": f"Using existing BOM: {fixture.bom}",
			})
			return result

	# Check if a default BOM already exists for this item
	existing_bom = frappe.db.get_value(
		"BOM",
		{"item": item_code, "is_active": 1, "is_default": 1},
		"name",
	)

	if existing_bom and skip_if_exists:
		result["bom_name"] = existing_bom
		result["skipped"] = True
		result["messages"].append({
			"severity": "info",
			"text": f"Using existing default BOM: {existing_bom}",
		})
		return result

	# Build BOM items list
	bom_items = []

	# --- Role 1: Profile ---
	if fixture.profile_item:
		# Calculate profile quantity based on segments
		profile_qty = _calculate_profile_quantity(fixture)
		if profile_qty > 0:
			bom_items.append({
				"item_code": fixture.profile_item,
				"qty": profile_qty,
				"uom": "Nos",
				"stock_uom": "Nos",
			})

	# --- Role 2: Lens ---
	if fixture.lens_item:
		# Lens quantity mirrors profile for stick-type lenses
		lens_qty = _calculate_lens_quantity(fixture)
		if lens_qty > 0:
			bom_items.append({
				"item_code": fixture.lens_item,
				"qty": lens_qty,
				"uom": "Nos",
				"stock_uom": "Nos",
			})

	# --- Role 3: Endcaps (with extra pair rule - Task 3.3) ---
	# Start endcap
	if fixture.endcap_item_start:
		# 2 endcaps: 1 for use + 1 extra
		bom_items.append({
			"item_code": fixture.endcap_item_start,
			"qty": 2,
			"uom": "Nos",
			"stock_uom": "Nos",
		})
	# End endcap (if different from start)
	if fixture.endcap_item_end and fixture.endcap_item_end != fixture.endcap_item_start:
		bom_items.append({
			"item_code": fixture.endcap_item_end,
			"qty": 2,
			"uom": "Nos",
			"stock_uom": "Nos",
		})
	elif fixture.endcap_item_end == fixture.endcap_item_start and fixture.endcap_item_start:
		# Same endcap for both ends, add 2 more (total 4)
		bom_items[-1]["qty"] = 4

	# --- Role 4: Mounting Accessories ---
	if fixture.mounting_item:
		mounting_qty = _calculate_mounting_quantity(fixture)
		if mounting_qty > 0:
			bom_items.append({
				"item_code": fixture.mounting_item,
				"qty": mounting_qty,
				"uom": "Nos",
				"stock_uom": "Nos",
			})

	# --- Role 5: LED Tape (Task 3.2 - Option A: total length in one line) ---
	tape_item = _get_tape_item(fixture)
	if tape_item:
		# Convert tape_cut_length_mm to feet (or meters based on UOM)
		tape_length_ft = (fixture.tape_cut_length_mm or 0) / 304.8
		if tape_length_ft > 0:
			bom_items.append({
				"item_code": tape_item,
				"qty": round(tape_length_ft, 2),
				"uom": "Foot",  # Use Foot as UOM
				"stock_uom": "Foot",
			})

	# --- Role 6: Leader Cables ---
	if fixture.leader_item:
		# Leader qty = runs_count
		leader_qty = fixture.runs_count or 1
		bom_items.append({
			"item_code": fixture.leader_item,
			"qty": leader_qty,
			"uom": "Nos",
			"stock_uom": "Nos",
		})

	# --- Role 7: Drivers ---
	if fixture.drivers:
		for driver in fixture.drivers:
			if driver.driver_item and driver.driver_qty > 0:
				bom_items.append({
					"item_code": driver.driver_item,
					"qty": driver.driver_qty,
					"uom": "Nos",
					"stock_uom": "Nos",
				})

	# Validate we have at least one BOM item
	if not bom_items:
		result["success"] = False
		result["messages"].append({
			"severity": "error",
			"text": "No BOM items could be generated - check component mappings",
		})
		return result

	# Create the BOM
	try:
		bom_doc = frappe.get_doc({
			"doctype": "BOM",
			"item": item_code,
			"quantity": 1,
			"is_active": 1,
			"is_default": 1,
			"with_operations": 0,  # Operations are in Work Order
			"items": bom_items,
			"remarks": _generate_bom_remarks(fixture),
		})
		bom_doc.insert(ignore_permissions=True)
		bom_doc.submit()

		result["bom_name"] = bom_doc.name
		result["created"] = True
		result["messages"].append({
			"severity": "info",
			"text": f"Created BOM: {bom_doc.name} with {len(bom_items)} items",
		})

	except Exception as e:
		result["success"] = False
		result["messages"].append({
			"severity": "error",
			"text": f"Failed to create BOM: {e!s}",
		})

	return result


def _create_or_get_work_order(
	fixture,
	item_code: str,
	bom_name: str,
	qty: int = 1,
	skip_if_exists: bool = True,
) -> dict[str, Any]:
	"""
	Create or retrieve Work Order for a configured fixture (Epic 5).

	Includes:
	- Operations template (Cut profile, Cut lens, Cut tape, Solder, Assemble, Test, Label, Pack, Ship)
	- Traveler notes with manufacturing instructions

	Args:
		fixture: ilL-Configured-Fixture document
		item_code: The configured item code
		bom_name: The BOM name
		qty: Quantity to manufacture
		skip_if_exists: If True, return existing WO without modification

	Returns:
		dict: {"success": bool, "work_order_name": str, "created": bool, "skipped": bool, "messages": list}
	"""
	result = {
		"success": True,
		"work_order_name": None,
		"created": False,
		"skipped": False,
		"messages": [],
	}

	# Check if fixture already has a Work Order
	if fixture.work_order and skip_if_exists:
		if frappe.db.exists("Work Order", fixture.work_order):
			existing_wo = frappe.get_doc("Work Order", fixture.work_order)
			# Validate qty matches
			if existing_wo.qty == qty:
				result["work_order_name"] = fixture.work_order
				result["skipped"] = True
				result["messages"].append({
					"severity": "info",
					"text": f"Using existing Work Order: {fixture.work_order}",
				})
				return result
			else:
				result["messages"].append({
					"severity": "warning",
					"text": f"Existing Work Order qty ({existing_wo.qty}) differs from requested ({qty})",
				})

	# Check for existing draft Work Orders for this item
	existing_wo = frappe.db.get_value(
		"Work Order",
		{
			"production_item": item_code,
			"bom_no": bom_name,
			"qty": qty,
			"docstatus": ["<", 2],  # Not cancelled
		},
		"name",
	)

	if existing_wo and skip_if_exists:
		result["work_order_name"] = existing_wo
		result["skipped"] = True
		result["messages"].append({
			"severity": "info",
			"text": f"Using existing Work Order: {existing_wo}",
		})
		return result

	# Generate traveler notes (Task 5.2)
	traveler_notes = _generate_traveler_notes(fixture)

	# Create the Work Order
	try:
		wo_doc = frappe.get_doc({
			"doctype": "Work Order",
			"production_item": item_code,
			"bom_no": bom_name,
			"qty": qty,
			"use_multi_level_bom": 0,
			"skip_transfer": 0,
			"remarks": traveler_notes,
			# Epic 7: Custom field to link back to configured fixture
			"ill_configured_fixture": fixture.name,
		})

		wo_doc.insert(ignore_permissions=True)

		result["work_order_name"] = wo_doc.name
		result["created"] = True
		result["messages"].append({
			"severity": "info",
			"text": f"Created Work Order: {wo_doc.name}",
		})

	except Exception as e:
		result["success"] = False
		result["messages"].append({
			"severity": "error",
			"text": f"Failed to create Work Order: {e!s}",
		})

	return result


def _update_fixture_links(fixture, item_code: str, bom_name: str, work_order_name: str):
	"""Update the configured fixture with links to generated artifacts."""
	try:
		fixture.configured_item = item_code
		fixture.bom = bom_name
		fixture.work_order = work_order_name
		fixture.save(ignore_permissions=True)
	except Exception:
		pass  # Non-critical, links are convenience


def _ensure_item_group_exists(group_name: str):
	"""Ensure the item group exists, creating it if necessary."""
	if not frappe.db.exists("Item Group", group_name):
		try:
			frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": group_name,
				"parent_item_group": "All Item Groups",
			}).insert(ignore_permissions=True)
		except Exception:
			pass  # May already exist from race condition


def _generate_item_description(fixture) -> str:
	"""Generate a detailed description for the configured Item."""
	length_mm = fixture.manufacturable_overall_length_mm or fixture.requested_overall_length_mm or 0
	requested_mm = fixture.requested_overall_length_mm or 0
	lines = [
		f"Configured Fixture: {fixture.name}",
		f"Template: {fixture.fixture_template or 'N/A'}",
		f"Length: {length_mm}mm (requested: {requested_mm}mm)",
		f"Finish: {fixture.finish or 'N/A'}",
		f"Lens: {fixture.lens_appearance or 'N/A'}",
		f"Mounting: {fixture.mounting_method or 'N/A'}",
		f"Endcaps: {fixture.endcap_style_start or 'N/A'} / {fixture.endcap_style_end or 'N/A'} ({fixture.endcap_color or 'N/A'})",
		f"Environment: {fixture.environment_rating or 'N/A'}",
		f"Runs: {fixture.runs_count or 0}",
		f"Total Watts: {fixture.total_watts or 0}W",
		f"Assembly Mode: {fixture.assembly_mode or 'N/A'}",
	]
	return "\n".join(lines)


def _generate_bom_remarks(fixture) -> str:
	"""Generate BOM remarks with run plan details (Task 3.2 Option A)."""
	tape_cut_length = fixture.tape_cut_length_mm or 0
	runs_count = fixture.runs_count or 0

	lines = [
		"=== RUN PLAN / CUT INSTRUCTIONS ===",
		f"Tape Cut Length: {tape_cut_length}mm ({tape_cut_length / 304.8:.2f}ft)",
		f"Number of Runs: {runs_count}",
		"",
		"Run Breakdown:",
	]

	if fixture.runs:
		for run in fixture.runs:
			run_len = run.run_len_mm or 0
			run_watts = run.run_watts or 0
			lines.append(
				f"  Run {run.run_index}: {run_len}mm ({run_len / 304.8:.2f}ft) - {run_watts}W"
			)
	else:
		lines.append("  No run data available")

	lines.extend([
		"",
		"=== SEGMENT PLAN ===",
	])

	if fixture.segments:
		for segment in fixture.segments:
			profile_len = segment.profile_cut_len_mm or 0
			lens_len = segment.lens_cut_len_mm or 0
			lines.append(
				f"  Segment {segment.segment_index}: Profile {profile_len}mm, Lens {lens_len}mm"
			)
			if segment.notes:
				lines.append(f"    Note: {segment.notes}")
	else:
		lines.append("  No segment data available")

	return "\n".join(lines)


def _generate_traveler_notes(fixture) -> str:
	"""Generate comprehensive traveler notes for the Work Order (Task 5.2)."""
	requested_length = fixture.requested_overall_length_mm or 0
	mfg_length = fixture.manufacturable_overall_length_mm or 0
	tape_cut_length = fixture.tape_cut_length_mm or 0
	runs_count = fixture.runs_count or 0

	lines = [
		"=" * 60,
		"MANUFACTURING TRAVELER",
		"=" * 60,
		"",
		"--- FIXTURE IDENTITY ---",
		f"Config ID: {fixture.name}",
		f"Template: {fixture.fixture_template or 'N/A'}",
		f"Engine Version: {fixture.engine_version or ENGINE_VERSION}",
		"",
		"--- LENGTH SPECIFICATIONS ---",
		f"Requested Length: {requested_length}mm",
		f"Manufacturable Length: {mfg_length}mm",
		f"Tape Cut Length: {tape_cut_length}mm ({tape_cut_length / 304.8:.2f}ft)",
		f"Difference: {requested_length - mfg_length}mm",
		"",
		"--- SEGMENT CUT LIST ---",
	]

	if fixture.segments:
		for segment in fixture.segments:
			lines.append(f"Segment {segment.segment_index}:")
			lines.append(f"  Profile: {segment.profile_cut_len_mm or 0}mm")
			lines.append(f"  Lens: {segment.lens_cut_len_mm or 0}mm")
			if segment.notes:
				lines.append(f"  Notes: {segment.notes}")
	else:
		lines.append("  No segment data available")

	lines.extend([
		"",
		"--- TAPE CUT & RUN BREAKDOWN ---",
		f"Total Tape Length: {tape_cut_length}mm",
		f"Number of Runs: {runs_count}",
	])

	if fixture.runs:
		for run in fixture.runs:
			lines.append(f"  Run {run.run_index}: {run.run_len_mm or 0}mm - {run.run_watts or 0}W")
	else:
		lines.append("  No run data available")

	lines.extend([
		"",
		f"--- LEADER CABLES ---",
		f"Leader Item: {fixture.leader_item or 'N/A'}",
		f"Leader Qty: {runs_count} (one per run)",
	])

	# Driver information
	lines.extend([
		"",
		"--- DRIVER SELECTION ---",
	])
	if fixture.drivers:
		for driver in fixture.drivers:
			lines.append(f"Driver: {driver.driver_item or 'N/A'}")
			lines.append(f"  Qty: {driver.driver_qty or 0}")
			lines.append(f"  Outputs Used: {driver.outputs_used or 'N/A'}")
			if driver.mapping_notes:
				lines.append(f"  Mapping: {driver.mapping_notes}")
	else:
		lines.append("No drivers configured")

	# Endcap information
	lines.extend([
		"",
		"--- ENDCAPS ---",
		f"Start Style: {fixture.endcap_style_start or 'N/A'}",
		f"End Style: {fixture.endcap_style_end or 'N/A'}",
		f"Color: {fixture.endcap_color or 'N/A'}",
		f"Start Item: {fixture.endcap_item_start or 'N/A'}",
		f"End Item: {fixture.endcap_item_end or 'N/A'}",
		"Qty: 4 (2 for fixture + 2 extra pair included)",
	])

	# QC Section (Epic 7)
	lines.extend([
		"",
		"=" * 60,
		"QC / TESTING SECTION",
		"=" * 60,
		"",
		"[ ] Functional Test: PASS / FAIL",
		"    Date: _______________",
		"    Technician: _______________",
		"",
		"Serial Number: _______________",
		"",
		"Notes: _______________________________________________",
	])

	return "\n".join(lines)


def _calculate_profile_quantity(fixture) -> int:
	"""Calculate profile quantity based on segments."""
	# Number of profile sticks = number of segments
	return len(fixture.segments) if fixture.segments else 1


def _calculate_lens_quantity(fixture) -> int:
	"""Calculate lens quantity (mirrors profile for stick lenses)."""
	return len(fixture.segments) if fixture.segments else 1


def _calculate_mounting_quantity(fixture) -> int:
	"""Calculate mounting accessory quantity based on qty rule from mapping."""
	# Try to get the mounting accessory rule
	mount_rule = frappe.db.get_value(
		"ilL-Rel-Mounting-Accessory-Map",
		{
			"fixture_template": fixture.fixture_template,
			"mounting_method": fixture.mounting_method,
			"is_active": 1,
		},
		["qty_rule_type", "qty_rule_value", "min_qty", "rounding"],
		as_dict=True,
	)

	if not mount_rule:
		return 1  # Default to 1 if no rule found

	qty = 0
	rule_type = mount_rule.get("qty_rule_type", "PER_FIXTURE")
	rule_value = float(mount_rule.get("qty_rule_value", 1) or 1)
	min_qty = int(mount_rule.get("min_qty", 0) or 0)
	rounding = mount_rule.get("rounding", "CEIL")

	if rule_type == "PER_FIXTURE":
		qty = rule_value
	elif rule_type == "PER_SEGMENT":
		qty = rule_value * len(fixture.segments)
	elif rule_type == "PER_RUN":
		qty = rule_value * fixture.runs_count
	elif rule_type == "PER_X_MM":
		# rule_value is the mm per unit
		if rule_value > 0:
			qty = (fixture.manufacturable_overall_length_mm or 0) / rule_value

	# Apply rounding
	if rounding == "CEIL":
		qty = math.ceil(qty)
	elif rounding == "FLOOR":
		qty = math.floor(qty)
	else:
		qty = round(qty)

	# Apply minimum
	return max(qty, min_qty)


def _get_tape_item(fixture) -> Optional[str]:
	"""Get the tape item from the tape offering."""
	if not fixture.tape_offering:
		return None

	tape_offering = frappe.db.get_value(
		"ilL-Rel-Tape Offering", fixture.tape_offering, "tape_spec"
	)
	if not tape_offering:
		return None

	return frappe.db.get_value("ilL-Spec-LED Tape", tape_offering, "item")
