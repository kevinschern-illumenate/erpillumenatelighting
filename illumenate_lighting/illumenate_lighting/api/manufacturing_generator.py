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

	# Generate friendly item name with length in inches and multi-segment info
	template_name = frappe.db.get_value(
		"ilL-Fixture-Template", fixture.fixture_template, "template_name"
	) or fixture.fixture_template

	length_mm = fixture.manufacturable_overall_length_mm or fixture.requested_overall_length_mm or 0
	length_inches = length_mm / 25.4
	
	# Format length in inches (use decimal if not whole, otherwise integer)
	if length_inches == int(length_inches):
		length_str = f'{int(length_inches)}"'
	else:
		length_str = f'{length_inches:.1f}"'
	
	# Build item name with multi-segment and jumper info
	is_multi_segment = getattr(fixture, 'is_multi_segment', 0) or 0
	user_segment_count = getattr(fixture, 'user_segment_count', 1) or 1
	
	name_parts = [
		template_name,
		fixture.finish or 'STD',
		fixture.lens_appearance or 'STD',
		length_str,
	]
	
	# Add multi-segment indicator if applicable
	if is_multi_segment:
		# Count jumper connections from user_segments
		jumper_count = 0
		if hasattr(fixture, 'user_segments') and fixture.user_segments:
			jumper_count = sum(
				1 for seg in fixture.user_segments 
				if getattr(seg, 'end_type', '') == 'Jumper'
			)
		
		if jumper_count > 0:
			name_parts.append(f"{user_segment_count}seg+{jumper_count}J")
		else:
			name_parts.append(f"{user_segment_count}seg")
	
	item_name = " - ".join(name_parts)

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
	
	# Determine if this is a multi-segment fixture
	is_multi_segment = fixture.is_multi_segment if hasattr(fixture, 'is_multi_segment') else 0
	user_segment_count = fixture.user_segment_count if hasattr(fixture, 'user_segment_count') else 1

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

	# --- Role 3: Endcaps (properly counted for multi-segment fixtures) ---
	# For multi-segment fixtures, calculate endcaps based on segment configuration
	endcap_counts = _calculate_endcap_quantities(fixture)
	
	# Add feed-through endcaps (start endcap)
	if endcap_counts.get("feed_through_qty", 0) > 0 and fixture.endcap_item_start:
		bom_items.append({
			"item_code": fixture.endcap_item_start,
			"qty": endcap_counts["feed_through_qty"],
			"uom": "Nos",
			"stock_uom": "Nos",
		})
	
	# Add solid endcaps (end endcap)
	if endcap_counts.get("solid_qty", 0) > 0 and fixture.endcap_item_end:
		# Check if already added same item as feed-through
		existing_endcap_idx = None
		for idx, item in enumerate(bom_items):
			if item["item_code"] == fixture.endcap_item_end:
				existing_endcap_idx = idx
				break
		
		if existing_endcap_idx is not None and fixture.endcap_item_end == fixture.endcap_item_start:
			# Same item for both - add to existing quantity
			bom_items[existing_endcap_idx]["qty"] += endcap_counts["solid_qty"]
		else:
			# Different item - add new line
			bom_items.append({
				"item_code": fixture.endcap_item_end,
				"qty": endcap_counts["solid_qty"],
				"uom": "Nos",
				"stock_uom": "Nos",
			})

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

	# --- Role 5: LED Tape (calculate from ALL segments for multi-segment) ---
	tape_item = _get_tape_item(fixture)
	if tape_item:
		# For multi-segment fixtures, sum tape from all segments
		total_tape_mm = _calculate_total_tape_length(fixture)
		tape_length_ft = total_tape_mm / 304.8
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

	# --- Role 7: Jumper Cables (for multi-segment fixtures) ---
	if is_multi_segment and fixture.segments:
		jumper_items = _calculate_jumper_cable_items(fixture)
		for jumper_item in jumper_items:
			if jumper_item.get("item_code") and jumper_item.get("qty", 0) > 0:
				bom_items.append({
					"item_code": jumper_item["item_code"],
					"qty": jumper_item["qty"],
					"uom": "Nos",
					"stock_uom": "Nos",
				})

	# --- Role 8: Drivers ---
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
	length_inches = length_mm / 25.4
	requested_inches = requested_mm / 25.4
	
	# Check for multi-segment
	is_multi_segment = getattr(fixture, 'is_multi_segment', 0) or 0
	user_segment_count = getattr(fixture, 'user_segment_count', 1) or 1
	
	lines = [
		f"Configured Fixture: {fixture.name}",
		f"Template: {fixture.fixture_template or 'N/A'}",
		f"Length: {length_inches:.1f}\" / {length_mm}mm (requested: {requested_inches:.1f}\" / {requested_mm}mm)",
		f"Finish: {fixture.finish or 'N/A'}",
		f"Lens: {fixture.lens_appearance or 'N/A'}",
		f"Mounting: {fixture.mounting_method or 'N/A'}",
		f"Endcaps: {fixture.endcap_style_start or 'N/A'} / {fixture.endcap_style_end or 'N/A'} ({fixture.endcap_color or 'N/A'})",
		f"Environment: {fixture.environment_rating or 'N/A'}",
		f"Runs: {fixture.runs_count or 0}",
		f"Total Watts: {fixture.total_watts or 0}W",
		f"Assembly Mode: {fixture.assembly_mode or 'N/A'}",
	]
	
	# Add multi-segment info if applicable
	if is_multi_segment:
		lines.append(f"Multi-Segment: Yes ({user_segment_count} segments)")
		
		# Count jumpers from user_segments
		jumper_count = 0
		if hasattr(fixture, 'user_segments') and fixture.user_segments:
			jumper_count = sum(
				1 for seg in fixture.user_segments 
				if getattr(seg, 'end_type', '') == 'Jumper'
			)
		if jumper_count > 0:
			lines.append(f"Jumper Connections: {jumper_count}")
		
		# Add build description if available
		build_desc = getattr(fixture, 'build_description', None)
		if build_desc:
			lines.append(f"\nBuild Description:\n{build_desc}")
	
	return "\n".join(lines)


def _generate_bom_remarks(fixture) -> str:
	"""Generate BOM remarks with run plan details (Task 3.2 Option A)."""
	tape_cut_length = fixture.tape_cut_length_mm or 0
	runs_count = fixture.runs_count or 0
	is_multi_segment = getattr(fixture, 'is_multi_segment', 0) or 0
	user_segment_count = getattr(fixture, 'user_segment_count', 1) or 1

	# Convert to inches for readability
	tape_cut_inches = tape_cut_length / 25.4

	lines = [
		"=== RUN PLAN / CUT INSTRUCTIONS ===",
		f"Total Tape Length: {tape_cut_inches:.1f}\" / {tape_cut_length}mm ({tape_cut_length / 304.8:.2f}ft)",
		f"Number of Runs: {runs_count}",
	]
	
	# Add multi-segment summary
	if is_multi_segment:
		lines.append(f"Multi-Segment Fixture: {user_segment_count} segments")
		
		# Count jumper connections
		jumper_count = 0
		if hasattr(fixture, 'user_segments') and fixture.user_segments:
			jumper_count = sum(
				1 for seg in fixture.user_segments 
				if getattr(seg, 'end_type', '') == 'Jumper'
			)
		if jumper_count > 0:
			lines.append(f"Jumper Connections: {jumper_count}")
	
	lines.extend(["", "Run Breakdown:"])

	if fixture.runs:
		for run in fixture.runs:
			run_len = run.run_len_mm or 0
			run_len_inches = run_len / 25.4
			run_watts = run.run_watts or 0
			segment_idx = getattr(run, 'segment_index', None)
			segment_info = f" (Segment {segment_idx})" if segment_idx else ""
			lines.append(
				f"  Run {run.run_index}: {run_len_inches:.1f}\" / {run_len}mm ({run_len / 304.8:.2f}ft) - {run_watts}W{segment_info}"
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
			tape_len = getattr(segment, 'tape_cut_len_mm', 0) or 0
			profile_inches = profile_len / 25.4
			lens_inches = lens_len / 25.4
			tape_inches = tape_len / 25.4
			
			lines.append(
				f"  Segment {segment.segment_index}: Profile {profile_inches:.1f}\", Lens {lens_inches:.1f}\", Tape {tape_inches:.1f}\""
			)
			
			# Show endcap info
			start_type = getattr(segment, 'start_endcap_type', '') or ''
			end_type = getattr(segment, 'end_endcap_type', '') or ''
			if start_type or end_type:
				lines.append(f"    Endcaps: Start={start_type or 'None'}, End={end_type or 'Jumper'}")
			
			# Show jumper info
			end_jumper_len = getattr(segment, 'end_jumper_len_mm', 0) or 0
			if end_jumper_len > 0:
				jumper_inches = end_jumper_len / 25.4
				lines.append(f"    End Jumper: {jumper_inches:.1f}\" / {end_jumper_len}mm")
			
			if segment.notes:
				lines.append(f"    Note: {segment.notes}")
	else:
		lines.append("  No segment data available")
	
	# Add endcap summary
	lines.extend([
		"",
		"=== ENDCAP SUMMARY ===",
	])
	
	endcap_counts = _calculate_endcap_quantities(fixture)
	lines.append(f"  Feed-Through Endcaps: {endcap_counts.get('feed_through_qty', 0)} (includes spares)")
	lines.append(f"  Solid Endcaps: {endcap_counts.get('solid_qty', 0)} (includes spares)")

	return "\n".join(lines)


def _generate_traveler_notes(fixture) -> str:
	"""Generate comprehensive traveler notes for the Work Order (Task 5.2)."""
	requested_length = fixture.requested_overall_length_mm or 0
	mfg_length = fixture.manufacturable_overall_length_mm or 0
	tape_cut_length = fixture.tape_cut_length_mm or 0
	runs_count = fixture.runs_count or 0
	
	# Convert to inches
	requested_inches = requested_length / 25.4
	mfg_inches = mfg_length / 25.4
	tape_inches = tape_cut_length / 25.4
	
	# Check for multi-segment
	is_multi_segment = getattr(fixture, 'is_multi_segment', 0) or 0
	user_segment_count = getattr(fixture, 'user_segment_count', 1) or 1

	lines = [
		"=" * 60,
		"MANUFACTURING TRAVELER",
		"=" * 60,
		"",
		"--- FIXTURE IDENTITY ---",
		f"Config ID: {fixture.name}",
		f"Template: {fixture.fixture_template or 'N/A'}",
		f"Engine Version: {fixture.engine_version or ENGINE_VERSION}",
	]
	
	# Add multi-segment indicator
	if is_multi_segment:
		lines.append(f"Multi-Segment Fixture: {user_segment_count} segments")
		
		# Count jumpers
		jumper_count = 0
		if hasattr(fixture, 'user_segments') and fixture.user_segments:
			jumper_count = sum(
				1 for seg in fixture.user_segments 
				if getattr(seg, 'end_type', '') == 'Jumper'
			)
		if jumper_count > 0:
			lines.append(f"Jumper Connections: {jumper_count}")
	
	lines.extend([
		"",
		"--- LENGTH SPECIFICATIONS ---",
		f"Requested Length: {requested_inches:.1f}\" / {requested_length}mm",
		f"Manufacturable Length: {mfg_inches:.1f}\" / {mfg_length}mm",
		f"Tape Cut Length: {tape_inches:.1f}\" / {tape_cut_length}mm ({tape_cut_length / 304.8:.2f}ft)",
		f"Difference: {(requested_length - mfg_length) / 25.4:.2f}\" / {requested_length - mfg_length}mm",
		"",
		"--- SEGMENT CUT LIST ---",
	])

	if fixture.segments:
		for segment in fixture.segments:
			profile_mm = segment.profile_cut_len_mm or 0
			lens_mm = segment.lens_cut_len_mm or 0
			tape_mm = getattr(segment, 'tape_cut_len_mm', 0) or 0
			lines.append(f"Segment {segment.segment_index}:")
			lines.append(f"  Profile: {profile_mm / 25.4:.1f}\" / {profile_mm}mm")
			lines.append(f"  Lens: {lens_mm / 25.4:.1f}\" / {lens_mm}mm")
			if tape_mm > 0:
				lines.append(f"  Tape: {tape_mm / 25.4:.1f}\" / {tape_mm}mm")
			
			# Show endcap info for this segment
			start_type = getattr(segment, 'start_endcap_type', '') or ''
			end_type = getattr(segment, 'end_endcap_type', '') or ''
			if start_type:
				lines.append(f"  Start Endcap: {start_type}")
			if end_type:
				lines.append(f"  End Endcap: {end_type}")
			elif is_multi_segment and segment.segment_index < user_segment_count:
				# This segment connects to next via jumper
				end_jumper_len = getattr(segment, 'end_jumper_len_mm', 0) or 0
				if end_jumper_len > 0:
					lines.append(f"  End: Jumper Cable ({end_jumper_len / 25.4:.1f}\" / {end_jumper_len}mm)")
			
			if segment.notes:
				lines.append(f"  Notes: {segment.notes}")
	else:
		lines.append("  No segment data available")

	lines.extend([
		"",
		"--- TAPE CUT & RUN BREAKDOWN ---",
		f"Total Tape Length: {tape_inches:.1f}\" / {tape_cut_length}mm ({tape_cut_length / 304.8:.2f}ft)",
		f"Number of Runs: {runs_count}",
	])

	if fixture.runs:
		for run in fixture.runs:
			run_mm = run.run_len_mm or 0
			run_inches = run_mm / 25.4
			segment_idx = getattr(run, 'segment_index', None)
			segment_info = f" (Segment {segment_idx})" if segment_idx else ""
			lines.append(f"  Run {run.run_index}: {run_inches:.1f}\" / {run_mm}mm - {run.run_watts or 0}W{segment_info}")
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
	endcap_counts = _calculate_endcap_quantities(fixture)
	lines.extend([
		"",
		"--- ENDCAPS ---",
		f"Start Style: {fixture.endcap_style_start or 'N/A'}",
		f"End Style: {fixture.endcap_style_end or 'N/A'}",
		f"Color: {fixture.endcap_color or 'N/A'}",
		f"Start/Feed-Through Item: {fixture.endcap_item_start or 'N/A'}",
		f"End/Solid Item: {fixture.endcap_item_end or 'N/A'}",
		f"Feed-Through Qty: {endcap_counts.get('feed_through_qty', 0)} (includes spares)",
		f"Solid Qty: {endcap_counts.get('solid_qty', 0)} (includes spares)",
	])
	
	# Jumper cable information (for multi-segment)
	if is_multi_segment:
		jumper_items = _calculate_jumper_cable_items(fixture)
		if jumper_items:
			lines.extend([
				"",
				"--- JUMPER CABLES ---",
			])
			for jumper in jumper_items:
				lines.append(f"  Item: {jumper.get('item_code', 'N/A')}, Qty: {jumper.get('qty', 0)}")

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


def _calculate_endcap_quantities(fixture) -> dict:
	"""
	Calculate accurate endcap quantities based on actual fixture configuration.
	
	The fixture has endcap_style_start and endcap_style_end fields that indicate
	whether each position needs a FEED_THROUGH or SOLID endcap.
	
	For single-segment fixtures:
	- Start endcap: Based on endcap_style_start (FEED_THROUGH if END feed, else SOLID)
	- End endcap: Based on endcap_style_end (usually SOLID)
	- Extra pair rule: +1 of each type used as spares
	
	For multi-segment fixtures:
	- First segment start: Based on segment's start_endcap_type
	- Segment ends with Jumper: No endcap (jumper cable connects to next)
	- Last segment end: Based on segment's end_endcap_type
	- Extra pair rule: +1 of each type used as spares
	
	Returns:
		dict: {"feed_through_qty": int, "solid_qty": int}
	"""
	is_multi_segment = fixture.is_multi_segment if hasattr(fixture, 'is_multi_segment') else 0
	
	feed_through_count = 0
	solid_count = 0
	
	if not is_multi_segment:
		# Single-segment fixture: check configured endcap styles
		start_style = getattr(fixture, 'endcap_style_start', '') or ''
		end_style = getattr(fixture, 'endcap_style_end', '') or ''
		
		# Count start endcap type
		if start_style.upper() == "FEED_THROUGH":
			feed_through_count += 1
		else:
			# Default to solid if not specified or SOLID
			solid_count += 1
		
		# Count end endcap type
		if end_style.upper() == "FEED_THROUGH":
			feed_through_count += 1
		else:
			# Default to solid if not specified or SOLID
			solid_count += 1
	else:
		# Multi-segment fixture: count from segments
		if fixture.segments:
			for idx, segment in enumerate(fixture.segments):
				# Start endcap: only for first segment
				if idx == 0:
					start_type = getattr(segment, 'start_endcap_type', '') or ''
					if start_type == "Feed-Through":
						feed_through_count += 1
					else:
						# Default to solid if not specified or unknown
						solid_count += 1
				
				# End endcap: only if this segment ends with an endcap (not jumper)
				end_type = getattr(segment, 'end_endcap_type', '') or ''
				if end_type == "Solid":
					solid_count += 1
				elif end_type == "Feed-Through":
					feed_through_count += 1
				# If end_type is empty, it's a jumper connection (no endcap)
		else:
			# No segments defined - use fixture-level styles or defaults
			start_style = getattr(fixture, 'endcap_style_start', '') or ''
			end_style = getattr(fixture, 'endcap_style_end', '') or ''
			
			if start_style.upper() == "FEED_THROUGH":
				feed_through_count += 1
			else:
				solid_count += 1
			
			if end_style.upper() == "FEED_THROUGH":
				feed_through_count += 1
			else:
				solid_count += 1
	
	# Apply extra pair rule: add +1 spare for each type used
	# This gives an extra pair (1 of each type) as spares
	if feed_through_count > 0:
		feed_through_count += 1  # +1 spare
	if solid_count > 0:
		solid_count += 1  # +1 spare
	
	return {
		"feed_through_qty": feed_through_count,
		"solid_qty": solid_count,
	}


def _calculate_total_tape_length(fixture) -> float:
	"""
	Calculate total tape length from all segments for multi-segment fixtures.
	
	Returns:
		float: Total tape length in mm
	"""
	is_multi_segment = fixture.is_multi_segment if hasattr(fixture, 'is_multi_segment') else 0
	
	if not is_multi_segment or not fixture.segments:
		# Single-segment: use tape_cut_length_mm
		return fixture.tape_cut_length_mm or 0
	
	# Multi-segment: sum tape from all segments
	total_tape_mm = 0
	for segment in fixture.segments:
		tape_len = getattr(segment, 'tape_cut_len_mm', 0) or 0
		total_tape_mm += tape_len
	
	# If segments don't have tape lengths, fall back to fixture total
	if total_tape_mm == 0:
		total_tape_mm = fixture.tape_cut_length_mm or 0
	
	return total_tape_mm


def _calculate_jumper_cable_items(fixture) -> list:
	"""
	Calculate jumper cable items needed for multi-segment fixtures.
	
	Jumper cables connect segments in a multi-segment fixture.
	Each segment that ends with "Jumper" type needs a jumper cable.
	
	Returns:
		list: List of {"item_code": str, "qty": int} for jumper cables
	"""
	jumper_items = []
	
	if not fixture.segments:
		return jumper_items
	
	# Group jumper cables by item and length
	jumper_by_item = {}
	
	for segment in fixture.segments:
		# Check if this segment ends with a jumper (connects to next segment)
		end_jumper_item = getattr(segment, 'end_jumper_item', None)
		end_jumper_len = getattr(segment, 'end_jumper_len_mm', 0) or 0
		
		if end_jumper_item and end_jumper_len > 0:
			if end_jumper_item not in jumper_by_item:
				jumper_by_item[end_jumper_item] = 0
			jumper_by_item[end_jumper_item] += 1
	
	# If no jumper items found on segments, try to determine from user_segments
	if not jumper_by_item and hasattr(fixture, 'user_segments') and fixture.user_segments:
		# Count segments that end with Jumper
		jumper_count = sum(
			1 for seg in fixture.user_segments 
			if getattr(seg, 'end_type', '') == 'Jumper'
		)
		
		if jumper_count > 0:
			# Try to get default jumper cable item from leader cable mappings
			# Jumpers typically use same family as leaders but different length
			default_jumper_item = _get_default_jumper_item(fixture)
			if default_jumper_item:
				jumper_by_item[default_jumper_item] = jumper_count
	
	# Convert to list format
	for item_code, qty in jumper_by_item.items():
		jumper_items.append({
			"item_code": item_code,
			"qty": qty,
		})
	
	return jumper_items


def _get_default_jumper_item(fixture) -> Optional[str]:
	"""
	Get default jumper cable item for a fixture.
	
	Looks up the leader cable mapping and returns a jumper cable item
	(jumpers are similar to leaders but for inter-segment connections).
	
	Returns:
		str or None: Item code for jumper cable
	"""
	# First try to use the leader_item as jumper (they're often the same)
	if fixture.leader_item:
		return fixture.leader_item
	
	# Otherwise look up from mapping
	if not fixture.fixture_template:
		return None
	
	# Get leader cable mapping which may have jumper info
	leader_map = frappe.db.get_value(
		"ilL-Rel-Leader-Cable-Map",
		{
			"fixture_template": fixture.fixture_template,
			"is_active": 1,
		},
		["leader_cable_item", "jumper_cable_item"],
		as_dict=True,
	)
	
	if leader_map:
		# Prefer dedicated jumper item, fall back to leader
		return leader_map.get("jumper_cable_item") or leader_map.get("leader_cable_item")
	
	return None

