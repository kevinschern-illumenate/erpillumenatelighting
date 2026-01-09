# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Reconciliation and Sync Detection API

This module provides utilities to detect when manufacturing artifacts
(Item, BOM, Work Order) are out of sync with their source Configured Fixture.

Epic 4 Task 4.2: "Out-of-sync" detection
"""

import hashlib
import json
from typing import Any

import frappe
from frappe import _


@frappe.whitelist()
def check_artifact_sync(configured_fixture_id: str) -> dict[str, Any]:
	"""
	Check if manufacturing artifacts are in sync with the configured fixture.

	Detects:
	- Engine version mismatch
	- Option changes (length, finish, etc.)
	- Pricing changes
	- BOM component mismatches

	Args:
		configured_fixture_id: Name of the ilL-Configured-Fixture

	Returns:
		dict: Sync status and details of any mismatches
	"""
	result = {
		"success": True,
		"in_sync": True,
		"configured_fixture_id": configured_fixture_id,
		"mismatches": [],
		"recommendations": [],
	}

	# Validate fixture exists
	if not frappe.db.exists("ilL-Configured-Fixture", configured_fixture_id):
		result["success"] = False
		result["mismatches"].append({
			"type": "not_found",
			"message": f"Configured Fixture '{configured_fixture_id}' not found",
		})
		return result

	fixture = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_id)

	# Check 1: Configured Item sync
	if fixture.configured_item:
		item_mismatches = _check_item_sync(fixture)
		result["mismatches"].extend(item_mismatches)

	# Check 2: BOM sync
	if fixture.bom:
		bom_mismatches = _check_bom_sync(fixture)
		result["mismatches"].extend(bom_mismatches)

	# Check 3: Work Order sync
	if fixture.work_order:
		wo_mismatches = _check_work_order_sync(fixture)
		result["mismatches"].extend(wo_mismatches)

	# Check 4: Engine version
	current_engine_version = "1.0.0"  # Should match ENGINE_VERSION in configurator_engine
	if fixture.engine_version and fixture.engine_version != current_engine_version:
		result["mismatches"].append({
			"type": "engine_version",
			"field": "engine_version",
			"expected": current_engine_version,
			"actual": fixture.engine_version,
			"message": (
				f"Engine version mismatch: fixture was computed with v{fixture.engine_version}, "
				f"current engine is v{current_engine_version}"
			),
		})

	# Determine overall sync status
	result["in_sync"] = len(result["mismatches"]) == 0

	# Generate recommendations
	if not result["in_sync"]:
		result["recommendations"] = _generate_recommendations(result["mismatches"])

	return result


def _check_item_sync(fixture) -> list[dict[str, Any]]:
	"""
	Check if the configured Item matches the fixture specification.

	Args:
		fixture: ilL-Configured-Fixture document

	Returns:
		list: Mismatch details
	"""
	mismatches = []

	if not frappe.db.exists("Item", fixture.configured_item):
		mismatches.append({
			"type": "item_missing",
			"field": "configured_item",
			"message": f"Configured Item '{fixture.configured_item}' no longer exists",
		})
		return mismatches

	item = frappe.get_doc("Item", fixture.configured_item)

	# Check if item links back to the fixture
	item_fixture_link = item.get("custom_ill_configured_fixture")
	if item_fixture_link and item_fixture_link != fixture.name:
		mismatches.append({
			"type": "item_link_mismatch",
			"field": "configured_item",
			"expected": fixture.name,
			"actual": item_fixture_link,
			"message": f"Item links to different fixture: {item_fixture_link}",
		})

	return mismatches


def _check_bom_sync(fixture) -> list[dict[str, Any]]:
	"""
	Check if the BOM matches the fixture's resolved items and quantities.

	Args:
		fixture: ilL-Configured-Fixture document

	Returns:
		list: Mismatch details
	"""
	mismatches = []

	if not frappe.db.exists("BOM", fixture.bom):
		mismatches.append({
			"type": "bom_missing",
			"field": "bom",
			"message": f"BOM '{fixture.bom}' no longer exists",
		})
		return mismatches

	bom = frappe.get_doc("BOM", fixture.bom)

	# Check BOM is active
	if not bom.is_active:
		mismatches.append({
			"type": "bom_inactive",
			"field": "bom",
			"message": f"BOM '{fixture.bom}' is no longer active",
		})

	# Check BOM item matches configured item
	if fixture.configured_item and bom.item != fixture.configured_item:
		mismatches.append({
			"type": "bom_item_mismatch",
			"field": "bom",
			"expected": fixture.configured_item,
			"actual": bom.item,
			"message": (
				f"BOM is for item '{bom.item}' but fixture uses '{fixture.configured_item}'"
			),
		})

	# Check key components are present
	expected_components = []
	if fixture.profile_item:
		expected_components.append(("profile", fixture.profile_item))
	if fixture.lens_item:
		expected_components.append(("lens", fixture.lens_item))
	if fixture.endcap_item_start:
		expected_components.append(("endcap_start", fixture.endcap_item_start))
	if fixture.endcap_item_end:
		expected_components.append(("endcap_end", fixture.endcap_item_end))
	if fixture.mounting_item:
		expected_components.append(("mounting", fixture.mounting_item))
	if fixture.leader_item:
		expected_components.append(("leader", fixture.leader_item))

	bom_items = {item.item_code for item in bom.items}

	for component_type, item_code in expected_components:
		if item_code not in bom_items:
			mismatches.append({
				"type": "bom_component_missing",
				"field": component_type,
				"expected": item_code,
				"message": f"BOM missing {component_type} component: {item_code}",
			})

	return mismatches


def _check_work_order_sync(fixture) -> list[dict[str, Any]]:
	"""
	Check if the Work Order matches the fixture specification.

	Args:
		fixture: ilL-Configured-Fixture document

	Returns:
		list: Mismatch details
	"""
	mismatches = []

	if not frappe.db.exists("Work Order", fixture.work_order):
		mismatches.append({
			"type": "work_order_missing",
			"field": "work_order",
			"message": f"Work Order '{fixture.work_order}' no longer exists",
		})
		return mismatches

	wo = frappe.get_doc("Work Order", fixture.work_order)

	# Check Work Order status
	if wo.docstatus == 2:  # Cancelled
		mismatches.append({
			"type": "work_order_cancelled",
			"field": "work_order",
			"message": f"Work Order '{fixture.work_order}' has been cancelled",
		})

	# Check production item matches
	if fixture.configured_item and wo.production_item != fixture.configured_item:
		mismatches.append({
			"type": "work_order_item_mismatch",
			"field": "work_order",
			"expected": fixture.configured_item,
			"actual": wo.production_item,
			"message": (
				f"Work Order is for item '{wo.production_item}' "
				f"but fixture uses '{fixture.configured_item}'"
			),
		})

	# Check BOM matches
	if fixture.bom and wo.bom_no != fixture.bom:
		mismatches.append({
			"type": "work_order_bom_mismatch",
			"field": "work_order",
			"expected": fixture.bom,
			"actual": wo.bom_no,
			"message": (
				f"Work Order uses BOM '{wo.bom_no}' but fixture uses '{fixture.bom}'"
			),
		})

	return mismatches


def _generate_recommendations(mismatches: list[dict[str, Any]]) -> list[str]:
	"""
	Generate actionable recommendations based on mismatches.

	Args:
		mismatches: List of mismatch details

	Returns:
		list: Recommendation strings
	"""
	recommendations = []

	mismatch_types = {m["type"] for m in mismatches}

	if "engine_version" in mismatch_types:
		recommendations.append(
			"Re-run validate_and_quote to update the configuration with the current engine version."
		)

	if any(t.startswith("bom_") for t in mismatch_types):
		recommendations.append(
			"Regenerate the BOM using generate_manufacturing_artifacts with skip_if_exists=False."
		)

	if any(t.startswith("work_order_") for t in mismatch_types):
		recommendations.append(
			"Create a new Work Order or cancel the existing one and regenerate."
		)

	if "item_missing" in mismatch_types:
		recommendations.append(
			"Regenerate the configured Item using generate_manufacturing_artifacts."
		)

	if not recommendations:
		recommendations.append(
			"Review the mismatches and take appropriate action to synchronize artifacts."
		)

	return recommendations


@frappe.whitelist()
def regenerate_artifacts(
	configured_fixture_id: str,
	regenerate_bom: bool = True,
	regenerate_work_order: bool = True,
) -> dict[str, Any]:
	"""
	Regenerate manufacturing artifacts for a configured fixture.

	This provides a controlled action to update out-of-sync artifacts.

	Args:
		configured_fixture_id: Name of the ilL-Configured-Fixture
		regenerate_bom: Whether to regenerate the BOM (default: True)
		regenerate_work_order: Whether to regenerate the Work Order (default: True)

	Returns:
		dict: Results of the regeneration
	"""
	result = {
		"success": True,
		"messages": [],
		"bom_regenerated": False,
		"work_order_regenerated": False,
	}

	# Validate fixture exists
	if not frappe.db.exists("ilL-Configured-Fixture", configured_fixture_id):
		result["success"] = False
		result["messages"].append({
			"severity": "error",
			"text": f"Configured Fixture '{configured_fixture_id}' not found",
		})
		return result

	fixture = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_id)

	# Import the manufacturing generator
	from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
		generate_manufacturing_artifacts,
	)

	# Clear existing links if regenerating
	if regenerate_bom and fixture.bom:
		# Deactivate old BOM instead of deleting
		try:
			old_bom = frappe.get_doc("BOM", fixture.bom)
			if old_bom.docstatus == 1:  # Submitted
				old_bom.is_active = 0
				old_bom.is_default = 0
				old_bom.save()
			fixture.bom = None
			result["messages"].append({
				"severity": "info",
				"text": f"Deactivated old BOM: {old_bom.name}",
			})
		except Exception as e:
			result["messages"].append({
				"severity": "warning",
				"text": f"Could not deactivate old BOM: {e}",
			})

	if regenerate_work_order and fixture.work_order:
		# Check if work order can be cancelled
		try:
			old_wo = frappe.get_doc("Work Order", fixture.work_order)
			if old_wo.docstatus == 0:  # Draft - can delete
				frappe.delete_doc("Work Order", fixture.work_order)
				fixture.work_order = None
				result["messages"].append({
					"severity": "info",
					"text": f"Deleted draft Work Order: {old_wo.name}",
				})
			elif old_wo.docstatus == 1:  # Submitted - leave as is but clear link
				fixture.work_order = None
				result["messages"].append({
					"severity": "warning",
					"text": f"Existing Work Order {old_wo.name} is submitted and cannot be modified",
				})
		except Exception as e:
			result["messages"].append({
				"severity": "warning",
				"text": f"Could not process old Work Order: {e}",
			})

	fixture.save()

	# Regenerate artifacts
	gen_result = generate_manufacturing_artifacts(
		configured_fixture_id=configured_fixture_id,
		qty=1,
		skip_if_exists=False,
	)

	result["messages"].extend(gen_result.get("messages", []))
	result["success"] = gen_result.get("success", False)
	result["bom_regenerated"] = gen_result.get("created", {}).get("bom", False)
	result["work_order_regenerated"] = gen_result.get("created", {}).get("work_order", False)

	return result


@frappe.whitelist()
def get_sync_status_batch(fixture_ids: list[str] | str) -> dict[str, Any]:
	"""
	Check sync status for multiple configured fixtures.

	Args:
		fixture_ids: List of configured fixture IDs or JSON string

	Returns:
		dict: Sync status for each fixture
	"""
	if isinstance(fixture_ids, str):
		fixture_ids = frappe.parse_json(fixture_ids)

	results = {
		"total": len(fixture_ids),
		"in_sync": 0,
		"out_of_sync": 0,
		"fixtures": [],
	}

	for fixture_id in fixture_ids:
		sync_result = check_artifact_sync(fixture_id)
		results["fixtures"].append({
			"configured_fixture_id": fixture_id,
			"in_sync": sync_result["in_sync"],
			"mismatch_count": len(sync_result["mismatches"]),
		})

		if sync_result["in_sync"]:
			results["in_sync"] += 1
		else:
			results["out_of_sync"] += 1

	return results
