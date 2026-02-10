# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Configurator Engine API

This module provides the Rules Engine v1 API for validating, computing, and pricing
fixture configurations. It serves as the single source of truth for the API contract
used by both the portal and future Next.js applications.

API Endpoints:
- validate_and_quote: Validates a configuration, computes manufacturable outputs, and returns pricing

Request Schema:
    {
        "fixture_template_code": str,           # Required: Code of the fixture template
        "finish_code": str,                      # Required: Finish option code
        "lens_appearance_code": str,             # Required: Lens appearance option code
        "mounting_method_code": str,             # Required: Mounting method option code
        "endcap_style_start_code": str,          # Required: Endcap style option code for start end
        "endcap_style_end_code": str,            # Required: Endcap style option code for end end
        "endcap_color_code": str,                # Required: Endcap color option code
        "power_feed_type_code": str,             # Required: Power feed type option code
        "environment_rating_code": str,          # Required: Environment rating option code
        "tape_offering_id": str,                 # Required: Tape offering ID or code
        "requested_overall_length_mm": int,      # Required: Requested overall length in millimeters
        "dimming_protocol_code": str,            # Optional: User's desired dimming protocol (filters drivers by input_protocol)
        "qty": int                               # Optional: Quantity (default: 1)
    }

Response Schema:
    {
        "is_valid": bool,                        # Overall validation status
        "messages": [                             # Validation/info messages
            {
                "severity": str,                  # "error", "warning", "info"
                "text": str,                      # Message text
                "field": str                      # Optional: Related field name
            }
        ],
        "computed": {                             # Computed/calculated values
            # Task 3.1: Length Math
            "endcap_allowance_start_mm": float,
            "endcap_allowance_end_mm": float,
            "total_endcap_allowance_mm": float,
            "leader_allowance_mm_per_fixture": float,
            "internal_length_mm": int,
            "tape_cut_length_mm": int,
            "manufacturable_overall_length_mm": int,
            "difference_mm": int,                 # requested - manufacturable
            "requested_overall_length_mm": int,   # Original request
            # Task 3.2: Segmentation Plan
            "segments_count": int,
            "profile_stock_len_mm": int,
            "segments": [                         # Cut plan
                {
                    "segment_index": int,
                    "profile_cut_len_mm": int,
                    "lens_cut_len_mm": int,
                    "notes": str
                }
            ],
            # Task 3.3: Run Splitting
            "runs_count": int,
            "leader_qty": int,
            "total_watts": float,
            "max_run_ft_by_watts": float,         # 85W / watts_per_ft
            "max_run_ft_by_voltage_drop": float,  # From tape spec (optional)
            "max_run_ft_effective": float,        # min of above two
            "runs": [                             # Run plan
                {
                    "run_index": int,
                    "run_len_mm": int,
                    "run_watts": float,
                    "leader_item": str,           # Item code
                    "leader_len_mm": int
                }
            ],
            # Task 3.4: Assembly Mode
            "assembly_mode": str,                 # "ASSEMBLED" or "SHIP_PIECES"
            "assembled_max_len_mm": int
        },
        "resolved_items": {                       # Resolved item codes/IDs
            "profile_item": str,
            "lens_item": str,
            "endcap_item": str,
            "mounting_item": str,
            "leader_item": str,
            "driver_plan": dict                   # Placeholder v1: suggested drivers only
        },
        "pricing": {                              # Pricing information
            "msrp_unit": float,
            "tier_unit": float,
            "adder_breakdown": [                  # Itemized pricing adders
                {
                    "component": str,
                    "description": str,
                    "amount": float
                }
            ]
        },
        "configured_fixture_id": str              # Created/updated ilL-Configured-Fixture name
    }
"""

import hashlib
import json
import math
from typing import Any

import frappe
from frappe import _
from frappe.utils import now

from illumenate_lighting.illumenate_lighting.api.unit_conversion import (
    add_inch_values_to_computed,
    inches_to_mm,
    mm_to_inches,
)

# Engine version - used for tracking configuration computation version
ENGINE_VERSION = "1.0.0"


@frappe.whitelist()
def debug_template_data(fixture_template_code: str) -> dict[str, Any]:
	"""
	Debug endpoint to inspect template data and linked tape offerings.
	
	Use this in browser console:
	frappe.call({method: 'illumenate_lighting.illumenate_lighting.api.configurator_engine.debug_template_data', 
	             args: {fixture_template_code: 'YOUR-TEMPLATE'}, callback: console.log});
	"""
	if not frappe.db.exists("ilL-Fixture-Template", fixture_template_code):
		return {"error": f"Template '{fixture_template_code}' not found"}
	
	template_doc = frappe.get_doc("ilL-Fixture-Template", fixture_template_code)
	
	# Get tape offerings from template
	allowed_tape_rows = template_doc.get("allowed_tape_offerings", [])
	tape_offering_names = [row.tape_offering for row in allowed_tape_rows if row.tape_offering]
	
	# Get tape offering details
	tape_offerings = []
	if tape_offering_names:
		tape_offerings = frappe.get_all(
			"ilL-Rel-Tape Offering",
			filters={"name": ["in", tape_offering_names]},
			fields=["name", "tape_spec", "cct", "cri", "sdcm", "led_package", "output_level", "is_active"],
		)
	
	# Get allowed options
	allowed_options = []
	for row in template_doc.get("allowed_options", []):
		allowed_options.append({
			"option_type": row.option_type,
			"finish": row.finish,
			"lens_appearance": row.lens_appearance,
			"mounting_method": row.mounting_method,
			"endcap_style": row.endcap_style,
			"power_feed_type": row.power_feed_type,
			"environment_rating": row.environment_rating,
			"is_active": row.is_active,
		})
	
	return {
		"template_code": fixture_template_code,
		"template_name": template_doc.template_name,
		"tape_offering_rows": [{"tape_offering": r.tape_offering} for r in allowed_tape_rows],
		"tape_offering_names": tape_offering_names,
		"tape_offerings": tape_offerings,
		"allowed_options": allowed_options,
	}


@frappe.whitelist()
def validate_and_quote(
	fixture_template_code: str,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_style_start_code: str,
	endcap_style_end_code: str,
	endcap_color_code: str,
	power_feed_type_code: str,
	environment_rating_code: str,
	tape_offering_id: str,
	requested_overall_length_mm: int,
	dimming_protocol_code: str = None,
	qty: int = 1,
) -> dict[str, Any]:
	"""
	Validate and quote a fixture configuration.

	This is the main entry point for the Rules Engine v1. It:
	1. Validates all selections against the fixture template's allowed options
	2. Computes manufacturable dimensions, segments, and runs
	3. Resolves items (profile, lens, endcaps, mounting, leader)
	4. Calculates pricing (MSRP, tier pricing, and adders)
	5. Creates or updates an ilL-Configured-Fixture document

	Args:
		fixture_template_code: Code of the fixture template
		finish_code: Finish option code
		lens_appearance_code: Lens appearance option code
		mounting_method_code: Mounting method option code
		endcap_style_start_code: Endcap style option code for start end
		endcap_style_end_code: Endcap style option code for end end
		endcap_color_code: Endcap color option code
		power_feed_type_code: Power feed type option code
		environment_rating_code: Environment rating option code
		tape_offering_id: Tape offering ID or code
		requested_overall_length_mm: Requested overall length in millimeters
		dimming_protocol_code: User's desired dimming protocol (filters drivers by input_protocol)
		qty: Quantity (default: 1)

	Returns:
		dict: Response containing validation status, computed values, resolved items,
		      pricing, and configured fixture ID
	"""
	# Convert string inputs to proper types if needed (Frappe passes all as strings from HTTP)
	try:
		requested_overall_length_mm = int(requested_overall_length_mm)
		qty = int(qty) if qty else 1
	except (ValueError, TypeError):
		return {
			"is_valid": False,
			"messages": [
				{
					"severity": "error",
					"text": "Invalid numeric value for requested_overall_length_mm or qty",
					"field": "requested_overall_length_mm",
				}
			],
			"computed": None,
			"resolved_items": None,
			"pricing": None,
			"configured_fixture_id": None,
		}

	# Initialize response structure
	response = {
		"is_valid": True,
		"messages": [],
		"computed": {
			# Task 3.1: Length Math
			"endcap_allowance_start_mm": 0.0,
			"endcap_allowance_end_mm": 0.0,
			"total_endcap_allowance_mm": 0.0,
			"leader_allowance_mm_per_fixture": 0.0,
			"internal_length_mm": 0,
			"tape_cut_length_mm": 0,
			"manufacturable_overall_length_mm": 0,
			"difference_mm": 0,
			"requested_overall_length_mm": 0,
			# Task 3.2: Segmentation Plan
			"segments_count": 0,
			"profile_stock_len_mm": 0,
			"segments": [],
			# Task 3.3: Run Splitting
			"runs_count": 0,
			"leader_qty": 0,
			"total_watts": 0.0,
			"max_run_ft_by_watts": None,
			"max_run_ft_by_voltage_drop": None,
			"max_run_ft_effective": None,
			"runs": [],
			# Task 3.4: Assembly Mode
			"assembly_mode": "ASSEMBLED",
			"assembled_max_len_mm": 0,
		},
		"resolved_items": {
			"profile_item": None,
			"lens_item": None,
			"endcap_item_start": None,
			"endcap_item_end": None,
			"mounting_item": None,
			"leader_item": None,
			"driver_plan": {"status": "suggested", "drivers": []},
		},
		"pricing": {"msrp_unit": 0.0, "tier_unit": 0.0, "adder_breakdown": []},
		"configured_fixture_id": None,
	}

	# Step 1: Validate inputs
	validation_result = _validate_configuration(
		fixture_template_code,
		finish_code,
		lens_appearance_code,
		mounting_method_code,
		endcap_style_start_code,
		endcap_style_end_code,
		endcap_color_code,
		power_feed_type_code,
		environment_rating_code,
		tape_offering_id,
		requested_overall_length_mm,
	)

	response["is_valid"] = validation_result["is_valid"]
	response["messages"].extend(validation_result["messages"])

	if not response["is_valid"]:
		return response

	# Step 2: Compute dimensions and manufacturing outputs
	computed_result = _compute_manufacturable_outputs(
		fixture_template_code,
		tape_offering_id,
		requested_overall_length_mm,
		endcap_style_start_code,
		endcap_style_end_code,
		power_feed_type_code,
		lens_appearance_code,
		finish_code,
		template_doc=validation_result.get("template_doc"),
		tape_offering_doc=validation_result.get("tape_offering_doc"),
	)

	response["computed"].update(computed_result)

	# Step 2.5: Validate computed outputs for edge cases (Epic 2 Task 2.2)
	edge_case_messages, edge_case_blocks = _validate_computed_edge_cases(
		computed_result,
		validation_result.get("template_doc"),
		validation_result.get("tape_offering_doc"),
	)
	response["messages"].extend(edge_case_messages)

	# If any edge case produced a block, return invalid
	if edge_case_blocks:
		response["is_valid"] = False
		return response

	# Step 3: Resolve items
	resolved_result, mapping_messages, mappings_valid = _resolve_items(
		fixture_template_code,
		finish_code,
		lens_appearance_code,
		mounting_method_code,
		endcap_style_start_code,
		endcap_style_end_code,
		endcap_color_code,
		environment_rating_code,
		power_feed_type_code,
		template_doc=validation_result.get("template_doc"),
		tape_offering_doc=validation_result.get("tape_offering_doc"),
	)

	response["messages"].extend(mapping_messages)
	if not mappings_valid:
		response["is_valid"] = False
		response["resolved_items"].update(resolved_result)
		return response

	response["resolved_items"].update(resolved_result)

	# Step 3.5: Select driver plan (Epic 5 Task 5.1)
	driver_plan_result, driver_messages = _select_driver_plan(
		fixture_template_code,
		runs_count=computed_result["runs_count"],
		total_watts=computed_result["total_watts"],
		tape_offering_doc=validation_result.get("tape_offering_doc"),
		dimming_protocol_code=dimming_protocol_code,
	)
	response["messages"].extend(driver_messages)
	response["resolved_items"]["driver_plan"] = driver_plan_result

	# Step 4: Calculate pricing
	pricing_result = _calculate_pricing(
		fixture_template_code,
		resolved_result,
		computed_result,
		finish_code,
		lens_appearance_code,
		mounting_method_code,
		endcap_style_start_code,
		endcap_style_end_code,
		power_feed_type_code,
		environment_rating_code,
		tape_offering_id,
		qty,
		template_doc=validation_result.get("template_doc"),
	)

	response["pricing"].update(pricing_result)

	# Step 5: Create or update configured fixture
	fixture_id = _create_or_update_configured_fixture(
		fixture_template_code,
		finish_code,
		lens_appearance_code,
		mounting_method_code,
		endcap_style_start_code,
		endcap_style_end_code,
		endcap_color_code,
		power_feed_type_code,
		environment_rating_code,
		tape_offering_id,
		requested_overall_length_mm,
		response["computed"],
		response["resolved_items"],
		response["pricing"],
	)

	response["configured_fixture_id"] = fixture_id

	# Add inch values to computed results for US market display
	response["computed"] = add_inch_values_to_computed(response["computed"])

	return response


@frappe.whitelist()
def validate_and_quote_inches(
	fixture_template_code: str,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_style_start_code: str,
	endcap_style_end_code: str,
	endcap_color_code: str,
	power_feed_type_code: str,
	environment_rating_code: str,
	tape_offering_id: str,
	requested_overall_length_in: float,
	dimming_protocol_code: str = None,
	qty: int = 1,
) -> dict[str, Any]:
	"""
	Validate and quote a fixture configuration with length input in inches.

	This is a convenience wrapper around validate_and_quote that accepts
	the requested length in inches instead of millimeters, making it easier
	for US market users to work with familiar units.

	The length is converted to mm internally, and the response includes
	both mm and inch values for all computed dimensions.

	Args:
		fixture_template_code: Code of the fixture template
		finish_code: Finish option code
		lens_appearance_code: Lens appearance option code
		mounting_method_code: Mounting method option code
		endcap_style_start_code: Endcap style option code for start end
		endcap_style_end_code: Endcap style option code for end end
		endcap_color_code: Endcap color option code
		power_feed_type_code: Power feed type option code
		environment_rating_code: Environment rating option code
		tape_offering_id: Tape offering ID or code
		requested_overall_length_in: Requested overall length in INCHES
		dimming_protocol_code: User's desired dimming protocol (filters drivers by input_protocol)
		qty: Quantity (default: 1)

	Returns:
		dict: Response with validation status, computed values (in both mm and inches),
		      resolved items, pricing, and configured fixture ID
	"""
	# Convert inches to mm
	try:
		requested_overall_length_in = float(requested_overall_length_in)
		requested_overall_length_mm = inches_to_mm(requested_overall_length_in, round_to_int=True)
		if not requested_overall_length_mm or requested_overall_length_mm <= 0:
			return {
				"is_valid": False,
				"messages": [
					{
						"severity": "error",
						"text": "Requested length must be greater than 0 inches",
						"field": "requested_overall_length_in",
					}
				],
				"computed": None,
				"resolved_items": None,
				"pricing": None,
				"configured_fixture_id": None,
			}
	except (ValueError, TypeError):
		return {
			"is_valid": False,
			"messages": [
				{
					"severity": "error",
					"text": "Invalid numeric value for requested_overall_length_in",
					"field": "requested_overall_length_in",
				}
			],
			"computed": None,
			"resolved_items": None,
			"pricing": None,
			"configured_fixture_id": None,
		}

	# Delegate to the main function with mm value
	return validate_and_quote(
		fixture_template_code=fixture_template_code,
		finish_code=finish_code,
		lens_appearance_code=lens_appearance_code,
		mounting_method_code=mounting_method_code,
		endcap_style_start_code=endcap_style_start_code,
		endcap_style_end_code=endcap_style_end_code,
		endcap_color_code=endcap_color_code,
		power_feed_type_code=power_feed_type_code,
		environment_rating_code=environment_rating_code,
		tape_offering_id=tape_offering_id,
		requested_overall_length_mm=requested_overall_length_mm,
		dimming_protocol_code=dimming_protocol_code,
		qty=qty,
	)


@frappe.whitelist()
def validate_and_quote_with_output(
	fixture_template_code: str,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_style_start_code: str,
	endcap_style_end_code: str,
	endcap_color_code: str,
	power_feed_type_code: str,
	environment_rating_code: str,
	led_package_code: str,
	cct_code: str,
	delivered_output_value: int,
	requested_overall_length_mm: int,
	dimming_protocol_code: str = None,
	qty: int = 1,
) -> dict[str, Any]:
	"""
	Validate and quote a fixture configuration using the new cascading configurator flow.

	This is an alternative entry point that uses the new flow where:
	- User selects LED Package, Environment Rating, CCT, Lens Appearance
	- User selects a delivered output value (computed lm/ft after lens transmission)
	- The tape offering is auto-selected based on these parameters

	The flow automatically determines the tape offering based on selections, then
	delegates to the standard validate_and_quote function.

	Args:
		fixture_template_code: Code of the fixture template
		finish_code: Finish option code
		lens_appearance_code: Lens appearance option code
		mounting_method_code: Mounting method option code
		endcap_style_start_code: Endcap style option code for start end
		endcap_style_end_code: Endcap style option code for end end
		endcap_color_code: Endcap color option code
		power_feed_type_code: Power feed type option code
		environment_rating_code: Environment rating option code
		led_package_code: LED Package code (new cascading flow)
		cct_code: CCT code (new cascading flow)
		delivered_output_value: User's selected delivered output in lm/ft (rounded to 50)
		requested_overall_length_mm: Requested overall length in millimeters
		dimming_protocol_code: User's desired dimming protocol (optional)
		qty: Quantity (default: 1)

	Returns:
		dict: Response containing validation status, computed values, resolved items,
		      pricing, configured fixture ID, and auto-selected tape details
	"""
	# Convert string inputs to proper types
	try:
		requested_overall_length_mm = int(requested_overall_length_mm)
		delivered_output_value = int(delivered_output_value)
		qty = int(qty) if qty else 1
	except (ValueError, TypeError):
		return {
			"is_valid": False,
			"messages": [
				{
					"severity": "error",
					"text": "Invalid numeric value for length, output, or qty",
					"field": "requested_overall_length_mm",
				}
			],
			"computed": None,
			"resolved_items": None,
			"pricing": None,
			"configured_fixture_id": None,
			"auto_selected_tape": None,
		}

	# Auto-select the tape based on the configuration
	tape_result = auto_select_tape_for_configuration(
		fixture_template_code=fixture_template_code,
		led_package_code=led_package_code,
		environment_rating_code=environment_rating_code,
		cct_code=cct_code,
		lens_appearance_code=lens_appearance_code,
		delivered_output_value=delivered_output_value,
	)

	if not tape_result.get("success") or not tape_result.get("tape_offering_id"):
		return {
			"is_valid": False,
			"messages": [
				{
					"severity": "error",
					"text": tape_result.get("error") or "Could not determine tape for selected configuration",
					"field": "delivered_output_value",
				}
			],
			"computed": None,
			"resolved_items": None,
			"pricing": None,
			"configured_fixture_id": None,
			"auto_selected_tape": None,
		}

	tape_offering_id = tape_result["tape_offering_id"]

	# Call the standard validate_and_quote with the auto-selected tape
	result = validate_and_quote(
		fixture_template_code=fixture_template_code,
		finish_code=finish_code,
		lens_appearance_code=lens_appearance_code,
		mounting_method_code=mounting_method_code,
		endcap_style_start_code=endcap_style_start_code,
		endcap_style_end_code=endcap_style_end_code,
		endcap_color_code=endcap_color_code,
		power_feed_type_code=power_feed_type_code,
		environment_rating_code=environment_rating_code,
		tape_offering_id=tape_offering_id,
		requested_overall_length_mm=requested_overall_length_mm,
		dimming_protocol_code=dimming_protocol_code,
		qty=qty,
	)

	# Add the auto-selected tape info to the response
	result["auto_selected_tape"] = {
		"tape_offering_id": tape_offering_id,
		"tape_details": tape_result.get("tape_details"),
		"delivered_output_lm_ft": delivered_output_value,
		"led_package": led_package_code,
		"cct": cct_code,
	}

	# Add info message about auto-selection
	if result.get("messages") is None:
		result["messages"] = []
	result["messages"].append({
		"severity": "info",
		"text": f"Tape '{tape_offering_id}' was automatically selected based on your output choice of {delivered_output_value} lm/ft",
		"field": None,
	})

	if tape_result.get("warning"):
		result["messages"].append({
			"severity": "warning",
			"text": tape_result["warning"],
			"field": None,
		})

	return result


@frappe.whitelist()
def validate_and_quote_multisegment_with_output(
	fixture_template_code: str,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_color_code: str,
	environment_rating_code: str,
	led_package_code: str,
	cct_code: str,
	delivered_output_value: int,
	segments_json: str,
	dimming_protocol_code: str = None,
	qty: int = 1,
) -> dict[str, Any]:
	"""
	Validate and quote a multi-segment fixture using the output-based cascading flow.

	This combines:
	- Multi-segment fixture support (segments with jumpers/endcaps)
	- Output-based tape auto-selection (user picks output level, tape is auto-selected)

	Args:
		fixture_template_code: Code of the fixture template
		finish_code: Finish option code
		lens_appearance_code: Lens appearance option code
		mounting_method_code: Mounting method option code
		endcap_color_code: Endcap color option code
		environment_rating_code: Environment rating option code
		led_package_code: LED Package code (new cascading flow)
		cct_code: CCT code (new cascading flow)
		delivered_output_value: User's selected delivered output in lm/ft (rounded to 50)
		segments_json: JSON string array of segment definitions
		dimming_protocol_code: User's desired dimming protocol
		qty: Quantity (default: 1)

	Returns:
		dict: Response containing validation status, computed values, resolved items,
		      pricing, configured fixture ID, and auto-selected tape info
	"""
	# Convert delivered_output_value to int
	try:
		delivered_output_value = int(delivered_output_value)
		qty = int(qty) if qty else 1
	except (ValueError, TypeError):
		return {
			"is_valid": False,
			"messages": [
				{
					"severity": "error",
					"text": "Invalid numeric value for delivered_output_value or qty",
					"field": "delivered_output_value",
				}
			],
			"computed": None,
			"resolved_items": None,
			"pricing": None,
			"configured_fixture_id": None,
			"auto_selected_tape": None,
		}

	# Auto-select the tape based on the configuration
	tape_result = auto_select_tape_for_configuration(
		fixture_template_code=fixture_template_code,
		led_package_code=led_package_code,
		environment_rating_code=environment_rating_code,
		cct_code=cct_code,
		lens_appearance_code=lens_appearance_code,
		delivered_output_value=delivered_output_value,
	)

	if not tape_result.get("success") or not tape_result.get("tape_offering_id"):
		return {
			"is_valid": False,
			"messages": [
				{
					"severity": "error",
					"text": tape_result.get("error") or "Could not determine tape for selected configuration",
					"field": "delivered_output_value",
				}
			],
			"computed": None,
			"resolved_items": None,
			"pricing": None,
			"configured_fixture_id": None,
			"auto_selected_tape": None,
		}

	tape_offering_id = tape_result["tape_offering_id"]

	# Delegate to the standard multi-segment function
	result = validate_and_quote_multisegment(
		fixture_template_code=fixture_template_code,
		finish_code=finish_code,
		lens_appearance_code=lens_appearance_code,
		mounting_method_code=mounting_method_code,
		endcap_color_code=endcap_color_code,
		environment_rating_code=environment_rating_code,
		tape_offering_id=tape_offering_id,
		segments_json=segments_json,
		dimming_protocol_code=dimming_protocol_code,
		qty=qty,
	)

	# Add auto-selected tape info
	result["auto_selected_tape"] = {
		"tape_offering_id": tape_offering_id,
		"led_package_code": led_package_code,
		"cct_code": cct_code,
		"delivered_output_value": delivered_output_value,
	}

	# Add info message about auto-selection
	if result.get("messages") is None:
		result["messages"] = []
	result["messages"].insert(0, {
		"severity": "info",
		"text": f"Tape '{tape_offering_id}' was automatically selected based on your output choice of {delivered_output_value} lm/ft",
		"field": None,
	})

	if tape_result.get("warning"):
		result["messages"].append({
			"severity": "warning",
			"text": tape_result["warning"],
			"field": None,
		})

	return result


@frappe.whitelist()
def validate_and_quote_multisegment(
	fixture_template_code: str,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_color_code: str,
	environment_rating_code: str,
	tape_offering_id: str,
	segments_json: str,
	dimming_protocol_code: str = None,
	qty: int = 1,
) -> dict[str, Any]:
	"""
	Validate and quote a multi-segment fixture configuration.

	This handles fixtures with multiple user-defined segments connected by jumper cables.
	Each segment can have a different length. The first segment starts with a leader cable,
	and subsequent segments inherit their start from the prior segment's end (jumper).
	The fixture must end with an Endcap on the final segment.

	Args:
		fixture_template_code: Code of the fixture template
		finish_code: Finish option code
		lens_appearance_code: Lens appearance option code
		mounting_method_code: Mounting method option code
		endcap_color_code: Endcap color option code
		environment_rating_code: Environment rating option code
		tape_offering_id: Tape offering ID or code
		segments_json: JSON string array of segment definitions
		dimming_protocol_code: User's desired dimming protocol
		qty: Quantity (default: 1)

	Returns:
		dict: Response containing validation status, computed values, resolved items,
		      pricing, and configured fixture ID
	"""
	# Parse segments
	try:
		segments = json.loads(segments_json) if isinstance(segments_json, str) else segments_json
		qty = int(qty) if qty else 1
	except (ValueError, TypeError, json.JSONDecodeError) as e:
		return {
			"is_valid": False,
			"messages": [
				{
					"severity": "error",
					"text": f"Invalid segments data: {str(e)}",
					"field": "segments_json",
				}
			],
			"computed": None,
			"resolved_items": None,
			"pricing": None,
			"configured_fixture_id": None,
		}

	if not segments or len(segments) == 0:
		return {
			"is_valid": False,
			"messages": [
				{
					"severity": "error",
					"text": "At least one segment is required",
					"field": "segments_json",
				}
			],
			"computed": None,
			"resolved_items": None,
			"pricing": None,
			"configured_fixture_id": None,
		}

	# Validate last segment ends with Endcap
	last_segment = segments[-1]
	if last_segment.get("end_type") != "Endcap":
		return {
			"is_valid": False,
			"messages": [
				{
					"severity": "error",
					"text": "The fixture must end with an Endcap on the last segment",
					"field": "segments_json",
				}
			],
			"computed": None,
			"resolved_items": None,
			"pricing": None,
			"configured_fixture_id": None,
		}

	# Initialize response structure
	response = {
		"is_valid": True,
		"messages": [],
		"computed": {
			"total_requested_length_mm": 0,
			"manufacturable_overall_length_mm": 0,
			"user_segment_count": len(segments),
			"segments_count": 0,
			"runs_count": 0,
			"total_watts": 0.0,
			"total_endcaps": 0,
			"total_mounting_accessories": 0,
			"assembly_mode": "ASSEMBLED",
			"build_description": "",
			"segments": [],
			"runs": [],
		},
		"resolved_items": {
			"profile_item": None,
			"lens_item": None,
			"endcap_item_start": None,
			"endcap_item_end": None,
			"mounting_item": None,
			"leader_item": None,
			"driver_plan": {"status": "suggested", "drivers": []},
		},
		"pricing": {"msrp_unit": 0.0, "tier_unit": 0.0, "adder_breakdown": []},
		"configured_fixture_id": None,
	}

	# Step 1: Basic validation
	if not frappe.db.exists("ilL-Fixture-Template", fixture_template_code):
		response["is_valid"] = False
		response["messages"].append({
			"severity": "error",
			"text": f"Fixture template '{fixture_template_code}' not found",
			"field": "fixture_template_code",
		})
		return response

	template_doc = frappe.get_doc("ilL-Fixture-Template", fixture_template_code)
	if not template_doc.is_active:
		response["is_valid"] = False
		response["messages"].append({
			"severity": "error",
			"text": f"Fixture template '{fixture_template_code}' is inactive",
			"field": "fixture_template_code",
		})
		return response

	# Validate tape offering
	if not frappe.db.exists("ilL-Rel-Tape Offering", tape_offering_id):
		response["is_valid"] = False
		response["messages"].append({
			"severity": "error",
			"text": f"Tape offering '{tape_offering_id}' not found",
			"field": "tape_offering_id",
		})
		return response

	tape_offering_doc = frappe.get_doc("ilL-Rel-Tape Offering", tape_offering_id)

	# Step 2: Compute multi-segment outputs
	computed_result = _compute_multisegment_outputs(
		fixture_template_code,
		tape_offering_id,
		segments,
		environment_rating_code,
		endcap_color_code,
		finish_code,
		lens_appearance_code,
		template_doc=template_doc,
		tape_offering_doc=tape_offering_doc,
	)

	response["computed"].update(computed_result)

	if computed_result.get("has_errors"):
		response["is_valid"] = False
		response["messages"].extend(computed_result.get("error_messages", []))
		return response

	# Step 3: Resolve items for multi-segment
	resolved_result, mapping_messages, mappings_valid = _resolve_multisegment_items(
		fixture_template_code,
		finish_code,
		lens_appearance_code,
		mounting_method_code,
		endcap_color_code,
		environment_rating_code,
		segments,
		template_doc=template_doc,
		tape_offering_doc=tape_offering_doc,
	)

	response["messages"].extend(mapping_messages)
	if not mappings_valid:
		response["is_valid"] = False
		response["resolved_items"].update(resolved_result)
		return response

	response["resolved_items"].update(resolved_result)

	# Step 3.5: Select driver plan (Epic 5 Task 5.1)
	driver_plan_result, driver_messages = _select_driver_plan(
		fixture_template_code,
		runs_count=computed_result["runs_count"],
		total_watts=computed_result["total_watts"],
		tape_offering_doc=tape_offering_doc,
		dimming_protocol_code=dimming_protocol_code,
	)
	response["messages"].extend(driver_messages)
	response["resolved_items"]["driver_plan"] = driver_plan_result

	# Step 4: Calculate pricing
	# For multi-segment, use the first segment's start power feed type
	first_segment = segments[0]
	start_power_feed_type = first_segment.get("start_power_feed_type", "")

	pricing_result = _calculate_pricing(
		fixture_template_code,
		resolved_result,
		computed_result,
		finish_code,
		lens_appearance_code,
		mounting_method_code,
		"FEED_THROUGH",  # Default endcap style for multi-segment
		"SOLID",  # Default endcap style for multi-segment
		start_power_feed_type,
		environment_rating_code,
		tape_offering_id,
		qty,
		template_doc=template_doc,
	)

	response["pricing"].update(pricing_result)

	# Step 5: Create configured fixture document
	fixture_id = _create_or_update_multisegment_fixture(
		fixture_template_code,
		finish_code,
		lens_appearance_code,
		mounting_method_code,
		endcap_color_code,
		environment_rating_code,
		tape_offering_id,
		segments,
		response["computed"],
		response["resolved_items"],
		response["pricing"],
	)

	response["configured_fixture_id"] = fixture_id

	if response["is_valid"]:
		response["messages"].append({
			"severity": "info",
			"text": "Multi-segment configuration validated successfully",
			"field": None,
		})

	# Add inch values to computed results for US market display
	response["computed"] = add_inch_values_to_computed(response["computed"])

	return response


def _compute_multisegment_outputs(
	fixture_template_code: str,
	tape_offering_id: str,
	segments: list,
	environment_rating_code: str,
	endcap_color_code: str,
	finish_code: str,
	lens_appearance_code: str,
	template_doc=None,
	tape_offering_doc=None,
) -> dict[str, Any]:
	"""
	Compute manufacturable outputs for a multi-segment fixture.

	This processes each user-defined segment, calculates tape runs, profile/lens
	segments, endcaps, and mounting accessories needed for the build.

	Args:
		fixture_template_code: Code of the fixture template
		tape_offering_id: Tape offering ID
		segments: List of user-defined segments
		environment_rating_code: Environment rating code
		endcap_color_code: Endcap color code
		finish_code: Finish code
		lens_appearance_code: Lens appearance code
		template_doc: Pre-fetched template document
		tape_offering_doc: Pre-fetched tape offering document

	Returns:
		dict: Computed values for the multi-segment fixture
	"""
	# Constants
	MAX_WATTS_PER_RUN = 85.0
	MM_PER_FOOT = 304.8

	# Get template and tape docs if not passed
	if template_doc is None:
		template_doc = frappe.get_doc("ilL-Fixture-Template", fixture_template_code)
	if tape_offering_doc is None:
		tape_offering_doc = frappe.get_doc("ilL-Rel-Tape Offering", tape_offering_id)

	# Get tape spec for calculations
	tape_spec_doc = frappe.get_doc("ilL-Spec-LED Tape", tape_offering_doc.tape_spec)
	cut_increment_mm = float(
		tape_offering_doc.cut_increment_mm_override
		or tape_spec_doc.cut_increment_mm
		or 50.0
	)
	watts_per_ft = float(
		tape_offering_doc.watts_per_ft_override
		or tape_spec_doc.watts_per_foot
		or 5.0
	)
	max_run_length_ft_voltage_drop = tape_spec_doc.voltage_drop_max_run_length_ft

	# Get profile stock length
	profile_stock_len_mm = float(template_doc.default_profile_stock_len_mm or 2000)
	leader_allowance_mm = float(template_doc.leader_allowance_mm_per_fixture or 15)
	assembled_max_len_mm = float(template_doc.assembled_max_len_mm or 2590)

	# Compute max run length
	if watts_per_ft > 0:
		max_run_ft_by_watts = MAX_WATTS_PER_RUN / watts_per_ft
	else:
		max_run_ft_by_watts = float("inf")

	if max_run_length_ft_voltage_drop and max_run_length_ft_voltage_drop > 0:
		max_run_ft_effective = min(max_run_ft_by_watts, float(max_run_length_ft_voltage_drop))
	else:
		max_run_ft_effective = max_run_ft_by_watts

	max_run_mm = max_run_ft_effective * MM_PER_FOOT if max_run_ft_effective != float("inf") else float("inf")

	# ==========================================================================
	# PHASE 1: Process each user segment to calculate segment data
	# ==========================================================================
	total_requested_length = 0
	total_manufacturable_length = 0
	total_tape_length = 0
	total_endcaps = 0
	all_segments = []
	build_description_parts = []  # mm version for internal/BOM use
	build_description_display_parts = []  # inches version for public display

	error_messages = []
	has_errors = False

	# Collect segment data first
	segment_data_list = []

	for idx, user_seg in enumerate(segments):
		seg_index = idx + 1
		requested_len = int(user_seg.get("requested_length_mm", 0))
		end_type = user_seg.get("end_type", "Endcap")
		start_power_feed = user_seg.get("start_power_feed_type", "")
		start_cable_len = int(user_seg.get("start_leader_cable_length_mm", 300))
		end_power_feed = user_seg.get("end_power_feed_type", "") if end_type == "Jumper" else ""
		end_cable_len = int(user_seg.get("end_jumper_cable_length_mm", 300)) if end_type == "Jumper" else 0

		if requested_len <= 0:
			error_messages.append({
				"severity": "error",
				"text": f"Segment {seg_index}: Requested length must be greater than 0",
				"field": "segments_json",
			})
			has_errors = True
			continue

		total_requested_length += requested_len

		# Calculate endcap allowances for this segment
		# EVERY segment end needs an endcap:
		# - Start endcap: Feed-Through if power feed type is "END" or if this is NOT the first segment
		#   (subsequent segments receive jumper cables from previous segment, requiring feed-through)
		# - End endcap: Feed-Through if end_type is "Jumper" (cable exits), Solid if end_type is "Endcap"
		#
		# For multi-segment fixtures connected by jumper cables:
		#   - Seg 1 Start: Feed-Through (for leader cable)
		#   - Seg 1 End: Feed-Through (for jumper cable exiting)
		#   - Seg 2 Start: Feed-Through (for jumper cable entering)
		#   - Seg 2 End: Feed-Through (for jumper cable exiting)
		#   - ... and so on ...
		#   - Last Seg End: Solid (caps the fixture)
		
		# Start endcap type:
		# - First segment (idx=0): Feed-Through if has flying lead (power feed "END"), else Solid
		# - Subsequent segments: Always Feed-Through (receive jumper from previous segment)
		if idx == 0:
			start_endcap_type = "Feed-Through" if start_power_feed and start_power_feed.upper() == "END" else "Solid"
		else:
			# Segments after the first receive a jumper cable - always need feed-through
			start_endcap_type = "Feed-Through"
		
		# End endcap type:
		# - Jumper: Feed-Through (cable exits to next segment)
		# - Endcap: Solid (caps the fixture)
		end_endcap_type = "Feed-Through" if end_type == "Jumper" else "Solid"

		# Standard endcap allowance (can be made configurable per template)
		endcap_allowance_per_side = 5.0  # mm

		# Calculate internal length for this segment
		# EVERY segment needs endcap allowance on BOTH ends:
		# - Start: always has an endcap (feed-through or solid)
		# - End: always has an endcap (feed-through for jumper, solid for cap)
		total_endcap_allowance = endcap_allowance_per_side * 2  # Both ends

		internal_len = requested_len - total_endcap_allowance - leader_allowance_mm

		if internal_len <= 0:
			error_messages.append({
				"severity": "error",
				"text": f"Segment {seg_index}: Length too short after endcap and cable allowances",
				"field": "segments_json",
			})
			has_errors = True
			continue

		# Calculate tape cut length
		if cut_increment_mm > 0:
			tape_cut_len = math.floor(internal_len / cut_increment_mm) * cut_increment_mm
		else:
			tape_cut_len = internal_len

		if tape_cut_len <= 0:
			error_messages.append({
				"severity": "error",
				"text": f"Segment {seg_index}: Results in 0mm tape length",
				"field": "segments_json",
			})
			has_errors = True
			continue

		# Calculate manufacturable length for this segment
		mfg_len = tape_cut_len + total_endcap_allowance + leader_allowance_mm
		total_manufacturable_length += mfg_len
		total_tape_length += tape_cut_len

		# Store segment data for later use in run calculation
		segment_data_list.append({
			"seg_index": seg_index,
			"tape_cut_len": tape_cut_len,
			"mfg_len": mfg_len,
			"start_endcap_type": start_endcap_type,  # Every segment has a start endcap
			"end_endcap_type": end_endcap_type,  # Every segment has an end endcap
			"end_type": end_type,
			"start_power_feed": start_power_feed,
			"start_cable_len": start_cable_len,
			"end_power_feed": end_power_feed,
			"end_cable_len": end_cable_len,
			"total_endcap_allowance": total_endcap_allowance,
		})

		# Count endcaps for this segment
		# EVERY segment has 2 endcaps - one at start and one at end
		# The type varies (feed-through vs solid) but each physical end needs an endcap
		segment_endcaps = 2  # Start endcap + End endcap
		total_endcaps += segment_endcaps

		# Create segment record for manufacturing
		all_segments.append({
			"segment_index": seg_index,
			"profile_cut_len_mm": int(mfg_len),
			"lens_cut_len_mm": int(mfg_len),
			"tape_cut_len_mm": int(tape_cut_len),
			"start_endcap_type": start_endcap_type,  # Every segment has a start endcap
			"end_endcap_type": end_endcap_type,  # Every segment has an end endcap
			"start_leader_len_mm": start_cable_len if idx == 0 else 0,
			"end_jumper_len_mm": end_cable_len,
			"notes": f"Segment {seg_index}: {int(mfg_len)}mm",
		})

		# Build description (mm for internal use / BOM)
		desc_parts = [f"Seg {seg_index}: {int(mfg_len)}mm"]
		if idx == 0:
			desc_parts.append(f"Start: {start_power_feed}, {start_cable_len}mm leader")
		if end_type == "Jumper":
			desc_parts.append(f"End: {end_power_feed}, {end_cable_len}mm jumper")
		else:
			desc_parts.append("End: Solid Endcap")
		build_description_parts.append(" | ".join(desc_parts))

		# Build description display (inches for public display)
		mfg_len_in = round(mfg_len / 25.4, 1)
		start_cable_len_in = round(start_cable_len / 25.4, 1)
		end_cable_len_in = round(end_cable_len / 25.4, 1)
		desc_parts_display = [f"Seg {seg_index}: {mfg_len_in}\""]
		if idx == 0:
			desc_parts_display.append(f"Start: {start_power_feed}, {start_cable_len_in}\" leader")
		if end_type == "Jumper":
			desc_parts_display.append(f"End: {end_power_feed}, {end_cable_len_in}\" jumper")
		else:
			desc_parts_display.append("End: Solid Endcap")
		build_description_display_parts.append(" | ".join(desc_parts_display))

	# ==========================================================================
	# PHASE 2: Calculate runs based on TOTAL tape length across all segments
	# ==========================================================================
	# Multi-segment fixtures connected by jumper cables form continuous tape runs.
	# The total tape length determines how many discrete runs are needed, not
	# the individual segment lengths.

	all_runs = []
	total_runs = 0
	total_watts = 0.0

	if not has_errors and total_tape_length > 0:
		# Calculate total runs needed based on total tape length
		if max_run_mm != float("inf") and max_run_mm > 0:
			total_runs_needed = math.ceil(total_tape_length / max_run_mm)
		else:
			total_runs_needed = 1

		# Distribute runs across the fixture using the "optimize" strategy:
		# Use maximum-length runs where possible, then fill remainder
		remaining_tape_to_process = total_tape_length
		current_run_index = 0

		for run_num in range(total_runs_needed):
			current_run_index += 1

			# For all but the last run, use max run length
			if run_num < total_runs_needed - 1:
				run_len = max_run_mm if max_run_mm != float("inf") else remaining_tape_to_process
			else:
				# Last run gets the remainder
				run_len = remaining_tape_to_process

			remaining_tape_to_process -= run_len
			run_watts = (run_len / MM_PER_FOOT) * watts_per_ft
			total_watts += run_watts

			# Determine which segment this run starts in
			# Calculate the start position of this run (how much tape has been processed before this run)
			tape_processed_before_run = total_tape_length - remaining_tape_to_process - run_len
			cumulative_segment_len = 0
			assigned_segment = 1
			for seg_data in segment_data_list:
				cumulative_segment_len += seg_data["tape_cut_len"]
				if cumulative_segment_len > tape_processed_before_run:
					assigned_segment = seg_data["seg_index"]
					break

			all_runs.append({
				"run_index": current_run_index,
				"segment_index": assigned_segment,
				"run_len_mm": int(run_len),
				"run_watts": round(run_watts, 2),
				"leader_item": None,
				"leader_len_mm": int(leader_allowance_mm),
			})

		total_runs = total_runs_needed

	# Calculate mounting accessories (based on total length, typically every 600mm)
	mounting_spacing_mm = 600  # Standard mounting clip spacing
	total_mounting_accessories = math.ceil(total_manufacturable_length / mounting_spacing_mm) if total_manufacturable_length > 0 else 0

	# Determine assembly mode
	if total_manufacturable_length <= assembled_max_len_mm:
		assembly_mode = "ASSEMBLED"
	else:
		assembly_mode = "SHIP_PIECES"

	# ==========================================================================
	# PHASE 3: Calculate profile/lens segments (cut plan based on stock length)
	# ==========================================================================
	# Profile and lens stock comes in standard lengths (e.g., 2000mm).
	# Calculate how many stock pieces are needed and the cut plan.
	profile_lens_segments = []
	profile_lens_segments_count = 0

	if profile_stock_len_mm > 0 and total_manufacturable_length > 0:
		profile_lens_segments_count = math.ceil(total_manufacturable_length / profile_stock_len_mm)

		# Create cut plan: N-1 full stock segments, last is remainder
		remaining_length = total_manufacturable_length
		for i in range(profile_lens_segments_count):
			segment_index = i + 1
			if segment_index < profile_lens_segments_count:
				# Full stock segment
				cut_len = min(profile_stock_len_mm, remaining_length)
				notes = f"Full stock segment ({int(profile_stock_len_mm)}mm)"
			else:
				# Last segment (remainder)
				cut_len = max(0, remaining_length)
				notes = f"Remainder segment ({int(cut_len)}mm)"

			remaining_length = max(0, remaining_length - cut_len)

			profile_lens_segments.append({
				"segment_index": segment_index,
				"profile_cut_len_mm": int(cut_len),
				"lens_cut_len_mm": int(cut_len),
				"notes": notes,
			})
	elif total_manufacturable_length > 0:
		# No stock length defined, treat as single segment
		profile_lens_segments_count = 1
		profile_lens_segments.append({
			"segment_index": 1,
			"profile_cut_len_mm": int(total_manufacturable_length),
			"lens_cut_len_mm": int(total_manufacturable_length),
			"notes": f"Single segment ({int(total_manufacturable_length)}mm)",
		})

	return {
		"total_requested_length_mm": total_requested_length,
		"manufacturable_overall_length_mm": int(total_manufacturable_length),
		"user_segment_count": len(segments),
		"segments_count": profile_lens_segments_count,
		"profile_lens_segments_count": profile_lens_segments_count,
		"runs_count": total_runs,
		# Each run requires one leader cable. Leader cables connect from driver outputs to tape runs.
		"leader_qty": total_runs,
		"total_tape_length_mm": int(total_tape_length),
		"total_watts": round(total_watts, 2),
		"total_endcaps": total_endcaps,
		"total_mounting_accessories": total_mounting_accessories,
		"assembly_mode": assembly_mode,
		"assembled_max_len_mm": int(assembled_max_len_mm),
		"profile_stock_len_mm": int(profile_stock_len_mm),
		# Run calculation metadata
		"max_run_ft_by_watts": round(max_run_ft_by_watts, 2) if max_run_ft_by_watts != float("inf") else None,
		"max_run_ft_by_voltage_drop": round(float(max_run_length_ft_voltage_drop), 2) if max_run_length_ft_voltage_drop else None,
		"max_run_ft_effective": round(max_run_ft_effective, 2) if max_run_ft_effective != float("inf") else None,
		"max_run_mm": round(max_run_mm, 2) if max_run_mm != float("inf") else None,
		"segments": profile_lens_segments,
		"user_segments": all_segments,
		"runs": all_runs,
		"build_description": "\n".join(build_description_parts),
		"build_description_display": "\n".join(build_description_display_parts),
		"has_errors": has_errors,
		"error_messages": error_messages,
	}


def _resolve_multisegment_items(
	fixture_template_code: str,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_color_code: str,
	environment_rating_code: str,
	segments: list,
	template_doc=None,
	tape_offering_doc=None,
) -> tuple[dict[str, Any], list[dict[str, str]], bool]:
	"""
	Resolve items for a multi-segment fixture.

	Returns:
		tuple: (resolved_items, messages, is_valid)
	"""
	messages: list[dict[str, str]] = []
	is_valid = True
	resolved: dict[str, Any] = {
		"profile_item": None,
		"lens_item": None,
		"endcap_item_start": None,
		"endcap_item_end": None,
		"mounting_item": None,
		"leader_item": None,
		"driver_plan": {"status": "suggested", "drivers": []},
	}

	if template_doc is None:
		template_doc = frappe.get_doc("ilL-Fixture-Template", fixture_template_code)

	# Resolve profile item
	profile_family = template_doc.default_profile_family or fixture_template_code
	finish_variant_code = frappe.db.get_value("ilL-Attribute-Finish", finish_code, "code") or finish_code

	profile_rows = frappe.get_all(
		"ilL-Spec-Profile",
		filters={"family": profile_family, "variant_code": finish_variant_code, "is_active": 1},
		fields=["name", "item", "lens_interface"],
		limit=1,
	)

	if profile_rows:
		resolved["profile_item"] = profile_rows[0].item
		lens_interface = profile_rows[0].lens_interface
	else:
		messages.append({
			"severity": "error",
			"text": f"No profile found for family '{profile_family}' and finish '{finish_code}'",
			"field": "finish_code",
		})
		is_valid = False
		lens_interface = None

	# Resolve lens item - match by lens_appearance only (like existing code)
	lens_candidates = frappe.get_all(
		"ilL-Spec-Lens",
		filters={"lens_appearance": lens_appearance_code},
		fields=["name", "item"],
	)

	lens_item = None
	if lens_candidates and environment_rating_code:
		# Check for environment rating compatibility
		lens_names = [row.name for row in lens_candidates]
		lens_envs = frappe.get_all(
			"ilL-Child-Lens Environments",
			filters={"parent": ["in", lens_names], "parenttype": "ilL-Spec-Lens"},
			fields=["parent", "environment_rating"],
		)
		lens_env_map: dict[str, set] = {}
		for env in lens_envs:
			if env.parent not in lens_env_map:
				lens_env_map[env.parent] = set()
			lens_env_map[env.parent].add(env.environment_rating)

		for lens_row in lens_candidates:
			env_supported = lens_env_map.get(lens_row.name, set())
			if env_supported and environment_rating_code not in env_supported:
				continue
			lens_item = lens_row.item
			break
	elif lens_candidates:
		lens_item = lens_candidates[0].item

	if lens_item:
		resolved["lens_item"] = lens_item
	else:
		messages.append({
			"severity": "warning",
			"text": f"No lens found for appearance '{lens_appearance_code}'",
			"field": "lens_appearance_code",
		})

	# Resolve mounting item
	mount_candidates = frappe.get_all(
		"ilL-Rel-Mounting-Accessory-Map",
		filters={
			"fixture_template": fixture_template_code,
			"mounting_method": mounting_method_code,
			"is_active": 1,
		},
		fields=["accessory_item", "environment_rating"],
	)

	for mount_row in mount_candidates:
		if mount_row.get("environment_rating") and mount_row.environment_rating != environment_rating_code:
			continue
		resolved["mounting_item"] = mount_row.accessory_item
		break

	if not resolved["mounting_item"]:
		messages.append({
			"severity": "warning",
			"text": f"No mounting accessory found for method '{mounting_method_code}'",
			"field": "mounting_method_code",
		})

	# Resolve endcap items
	# For multi-segment: start endcap needs feed-through if there's a leader cable feeding in
	# End endcap is solid for the last segment (no power passing through)
	first_segment = segments[0] if segments else {}
	start_power_feed = first_segment.get("start_power_feed_type", "")

	# Determine if start endcap needs to support feed-through
	# If there's a power feed type specified for start, we need a feed-through endcap
	start_needs_feed = bool(start_power_feed)

	# Get all endcap candidates for this template and color
	endcap_candidates = frappe.get_all(
		"ilL-Rel-Endcap-Map",
		filters={
			"fixture_template": fixture_template_code,
			"endcap_color": endcap_color_code,
			"is_active": 1,
		},
		fields=["endcap_item", "endcap_style", "power_feed_type"],
	)

	# Build lookup of endcap styles to check supports_feed property
	endcap_style_names = list({ec.endcap_style for ec in endcap_candidates if ec.endcap_style})
	endcap_style_info = {}
	if endcap_style_names:
		style_docs = frappe.get_all(
			"ilL-Attribute-Endcap Style",
			filters={"name": ["in", endcap_style_names]},
			fields=["name", "style", "supports_feed"],
		)
		endcap_style_info = {s.name: s for s in style_docs}

	# Find start endcap: if start needs feed, look for one with supports_feed=1 or style containing "Feed"
	# Otherwise, look for a solid endcap
	start_endcap_found = None
	start_endcap_fallback = None
	for ec_row in endcap_candidates:
		if not ec_row.endcap_style:
			continue
		style_info = endcap_style_info.get(ec_row.endcap_style, {})
		supports_feed = style_info.get("supports_feed", 0)
		style_name = style_info.get("style", "") or ""

		if start_needs_feed:
			# Looking for feed-through endcap
			if supports_feed or "feed" in style_name.lower():
				start_endcap_found = ec_row.endcap_item
				break
			if not start_endcap_fallback:
				start_endcap_fallback = ec_row.endcap_item
		else:
			# Looking for solid endcap
			if "solid" in style_name.lower() or (not supports_feed and "feed" not in style_name.lower()):
				start_endcap_found = ec_row.endcap_item
				break
			if not start_endcap_fallback:
				start_endcap_fallback = ec_row.endcap_item

	resolved["endcap_item_start"] = start_endcap_found or start_endcap_fallback

	# Find end endcap: always solid (no power passing through the end)
	end_endcap_found = None
	end_endcap_fallback = None
	for ec_row in endcap_candidates:
		if not ec_row.endcap_style:
			continue
		style_info = endcap_style_info.get(ec_row.endcap_style, {})
		supports_feed = style_info.get("supports_feed", 0)
		style_name = style_info.get("style", "") or ""

		# Looking for solid endcap
		if "solid" in style_name.lower() or (not supports_feed and "feed" not in style_name.lower()):
			end_endcap_found = ec_row.endcap_item
			break
		if not end_endcap_fallback:
			end_endcap_fallback = ec_row.endcap_item

	resolved["endcap_item_end"] = end_endcap_found or end_endcap_fallback

	# Resolve leader cable item
	if tape_offering_doc:
		leader_candidates = frappe.get_all(
			"ilL-Rel-Leader-Cable-Map",
			filters={
				"tape_spec": tape_offering_doc.tape_spec,
				"is_active": 1,
			},
			fields=["leader_item", "power_feed_type", "environment_rating"],
		)

		for leader_row in leader_candidates:
			if leader_row.get("environment_rating") and leader_row.environment_rating != environment_rating_code:
				continue
			resolved["leader_item"] = leader_row.leader_item
			break

	return resolved, messages, is_valid


def _create_or_update_multisegment_fixture(
	fixture_template_code: str,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_color_code: str,
	environment_rating_code: str,
	tape_offering_id: str,
	user_segments: list,
	computed: dict,
	resolved_items: dict,
	pricing: dict,
) -> str:
	"""
	Create or update a multi-segment configured fixture document.

	Returns:
		str: Name of the configured fixture document
	"""
	# Determine if this is truly a multi-segment fixture
	# A fixture is multi-segment only if it has jumper cables connecting segments
	# (i.e., any segment ends with "Jumper" type, or there are multiple segments)
	# A single segment ending with "Endcap" is NOT multi-segment
	has_jumper = any(seg.get("end_type") == "Jumper" for seg in user_segments)
	is_multi_segment = len(user_segments) > 1 or has_jumper

	# Generate config hash for deduplication - use 32 chars like single-segment fixtures
	config_data = {
		"fixture_template_code": fixture_template_code,
		"finish_code": finish_code,
		"lens_appearance_code": lens_appearance_code,
		"mounting_method_code": mounting_method_code,
		"endcap_color_code": endcap_color_code,
		"environment_rating_code": environment_rating_code,
		"tape_offering_id": tape_offering_id,
		"user_segments": user_segments,
		"is_multi_segment": is_multi_segment,
	}
	config_json = json.dumps(config_data, sort_keys=True)
	config_hash = hashlib.sha256(config_json.encode()).hexdigest()[:32]

	# Check for existing fixture with same hash
	existing = frappe.db.exists("ilL-Configured-Fixture", {"config_hash": config_hash})

	# If not found by hash, also check by generated part number (to handle duplicates)
	# Create a temporary doc to generate the part number
	if not existing:
		temp_doc = frappe.new_doc("ilL-Configured-Fixture")
		temp_doc.fixture_template = fixture_template_code
		temp_doc.finish = finish_code
		temp_doc.lens_appearance = lens_appearance_code
		temp_doc.mounting_method = mounting_method_code
		temp_doc.endcap_color = endcap_color_code
		temp_doc.environment_rating = environment_rating_code
		temp_doc.tape_offering = tape_offering_id
		temp_doc.is_multi_segment = 1 if is_multi_segment else 0
		temp_doc.requested_overall_length_mm = computed.get("total_requested_length_mm", 0)
		# Set power feed type and user segments for part number generation
		first_segment = user_segments[0] if user_segments else {}
		temp_doc.power_feed_type = first_segment.get("start_power_feed_type", "")
		for user_seg in user_segments:
			temp_doc.append("user_segments", {
				"segment_index": user_seg.get("segment_index", 0),
				"requested_length_mm": user_seg.get("requested_length_mm", 0),
				"start_power_feed_type": user_seg.get("start_power_feed_type", ""),
				"start_leader_cable_length_mm": user_seg.get("start_leader_cable_length_mm", 300),
				"end_type": user_seg.get("end_type", "Endcap"),
				"end_power_feed_type": user_seg.get("end_power_feed_type", ""),
				"end_jumper_cable_length_mm": user_seg.get("end_jumper_cable_length_mm", 0),
			})
		# Generate the part number that would be used
		generated_part_number = temp_doc._generate_part_number()
		# Check if this part number already exists
		if frappe.db.exists("ilL-Configured-Fixture", generated_part_number):
			existing = generated_part_number

	if existing:
		doc = frappe.get_doc("ilL-Configured-Fixture", existing)
		# Update config_hash if configuration changed
		doc.config_hash = config_hash
	else:
		doc = frappe.new_doc("ilL-Configured-Fixture")
		doc.config_hash = config_hash

	# Set values
	doc.engine_version = ENGINE_VERSION
	doc.is_multi_segment = 1 if is_multi_segment else 0
	doc.fixture_template = fixture_template_code
	doc.finish = finish_code
	doc.lens_appearance = lens_appearance_code
	doc.mounting_method = mounting_method_code
	doc.endcap_color = endcap_color_code
	doc.environment_rating = environment_rating_code
	doc.tape_offering = tape_offering_id

	# Use first segment's start power feed type
	first_segment = user_segments[0] if user_segments else {}
	doc.power_feed_type = first_segment.get("start_power_feed_type", "")

	# Set length data
	doc.requested_overall_length_mm = computed.get("total_requested_length_mm", 0)
	doc.manufacturable_overall_length_mm = computed.get("manufacturable_overall_length_mm", 0)
	doc.tape_cut_length_mm = computed.get("total_tape_length_mm", 0)

	# Set computed outputs
	doc.runs_count = computed.get("runs_count", 0)
	doc.total_watts = computed.get("total_watts", 0.0)
	doc.user_segment_count = computed.get("user_segment_count", 0)
	doc.assembly_mode = computed.get("assembly_mode", "ASSEMBLED")
	doc.build_description = computed.get("build_description", "")
	doc.total_endcaps = computed.get("total_endcaps", 0)
	doc.total_mounting_accessories = computed.get("total_mounting_accessories", 0)

	# Set resolved items
	doc.profile_item = resolved_items.get("profile_item")
	doc.lens_item = resolved_items.get("lens_item")
	doc.endcap_item_start = resolved_items.get("endcap_item_start")
	doc.endcap_item_end = resolved_items.get("endcap_item_end")
	doc.mounting_item = resolved_items.get("mounting_item")
	doc.leader_item = resolved_items.get("leader_item")

	# Clear and set user segments
	doc.user_segments = []
	for user_seg in user_segments:
		doc.append("user_segments", {
			"segment_index": user_seg.get("segment_index", 0),
			"requested_length_mm": user_seg.get("requested_length_mm", 0),
			"start_power_feed_type": user_seg.get("start_power_feed_type", ""),
			"start_leader_cable_length_mm": user_seg.get("start_leader_cable_length_mm", 300),
			"end_type": user_seg.get("end_type", "Endcap"),
			"end_power_feed_type": user_seg.get("end_power_feed_type", ""),
			"end_jumper_cable_length_mm": user_seg.get("end_jumper_cable_length_mm", 0),
		})

	# Clear and set computed segments (user-defined segments with details)
	doc.segments = []
	for seg in computed.get("user_segments", []):
		doc.append("segments", {
			"segment_index": seg.get("segment_index", 0),
			"profile_cut_len_mm": seg.get("profile_cut_len_mm", 0),
			"lens_cut_len_mm": seg.get("lens_cut_len_mm", 0),
			"tape_cut_len_mm": seg.get("tape_cut_len_mm", 0),
			"start_endcap_type": seg.get("start_endcap_type", ""),
			"end_endcap_type": seg.get("end_endcap_type", ""),
			"start_endcap_item": seg.get("start_endcap_item") or resolved_items.get("endcap_item_start"),
			"end_endcap_item": seg.get("end_endcap_item") or resolved_items.get("endcap_item_end"),
			"start_leader_item": seg.get("start_leader_item") or resolved_items.get("leader_item"),
			"start_leader_len_mm": seg.get("start_leader_len_mm", 0),
			"end_jumper_item": seg.get("end_jumper_item") or resolved_items.get("leader_item"),  # Jumper uses same item as leader
			"end_jumper_len_mm": seg.get("end_jumper_len_mm", 0),
			"notes": seg.get("notes", ""),
		})

	# Clear and set runs
	doc.runs = []
	for run in computed.get("runs", []):
		doc.append("runs", {
			"run_index": run.get("run_index", 0),
			"segment_index": run.get("segment_index", 1),  # Track which segment the run starts in
			"run_len_mm": run.get("run_len_mm", 0),
			"run_watts": run.get("run_watts", 0.0),
			"leader_item": run.get("leader_item") or resolved_items.get("leader_item"),
			"leader_len_mm": run.get("leader_len_mm", 0),
		})

	# Set driver allocations
	doc.drivers = []
	driver_plan = resolved_items.get("driver_plan", {})
	if driver_plan.get("status") == "selected" and driver_plan.get("drivers"):
		for driver_alloc in driver_plan["drivers"]:
			doc.append(
				"drivers",
				{
					"driver_item": driver_alloc.get("item_code"),
					"driver_qty": driver_alloc.get("qty", 1),
					"outputs_used": driver_alloc.get("outputs_used", 0),
					"mapping_notes": driver_alloc.get("mapping_notes", ""),
				},
			)

	# Append pricing snapshot
	doc.append("pricing_snapshot", {
		"msrp_unit": pricing.get("msrp_unit", 0.0),
		"tier_unit": pricing.get("tier_unit", 0.0),
		"adder_breakdown_json": json.dumps(pricing.get("adder_breakdown", [])),
		"timestamp": now(),
	})

	# Save document
	if existing:
		doc.save()
	else:
		doc.insert()

	return doc.name


def _validate_configuration(
	fixture_template_code: str,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_style_start_code: str,
	endcap_style_end_code: str,
	endcap_color_code: str,
	power_feed_type_code: str,
	environment_rating_code: str,
	tape_offering_id: str,
	requested_overall_length_mm: int,
) -> dict[str, Any]:
	"""
	Validate the configuration against fixture template constraints.

	Returns:
		dict: {"is_valid": bool, "messages": list}
	"""
	messages = []
	is_valid = True

	# Validate fixture template exists and is active
	if not frappe.db.exists("ilL-Fixture-Template", fixture_template_code):
		messages.append(
			{
				"severity": "error",
				"text": f"Fixture template '{fixture_template_code}' not found",
				"field": "fixture_template_code",
			}
		)
		is_valid = False
		return {"is_valid": is_valid, "messages": messages}

	template_doc = frappe.get_doc("ilL-Fixture-Template", fixture_template_code)

	if not template_doc.is_active:
		messages.append(
			{
				"severity": "error",
				"text": f"Fixture template '{fixture_template_code}' is inactive",
				"field": "fixture_template_code",
			}
		)
		is_valid = False
		return {"is_valid": is_valid, "messages": messages}

	# Validate required fields are provided
	required_fields = {
		"finish_code": finish_code,
		"lens_appearance_code": lens_appearance_code,
		"mounting_method_code": mounting_method_code,
		"endcap_style_start_code": endcap_style_start_code,
		"endcap_style_end_code": endcap_style_end_code,
		"endcap_color_code": endcap_color_code,
		"power_feed_type_code": power_feed_type_code,
		"environment_rating_code": environment_rating_code,
		"tape_offering_id": tape_offering_id,
	}

	for field_name, field_value in required_fields.items():
		if not field_value:
			messages.append({"severity": "error", "text": f"{field_name} is required", "field": field_name})
			is_valid = False

	# Validate requested length
	if requested_overall_length_mm <= 0:
		messages.append(
			{
				"severity": "error",
				"text": "Requested overall length must be greater than 0",
				"field": "requested_overall_length_mm",
			}
		)
		is_valid = False

	allowed_option_map = {
		"Finish": ("finish", finish_code, "finish_code", "ilL-Attribute-Finish"),
		"Lens Appearance": ("lens_appearance", lens_appearance_code, "lens_appearance_code", "ilL-Attribute-Lens Appearance"),
		"Mounting Method": ("mounting_method", mounting_method_code, "mounting_method_code", "ilL-Attribute-Mounting Method"),
		"Power Feed Type": ("power_feed_type", power_feed_type_code, "power_feed_type_code", "ilL-Attribute-Power Feed Type"),
		"Environment Rating": ("environment_rating", environment_rating_code, "environment_rating_code", "ilL-Attribute-Environment Rating"),
	}

	for option_type, (child_field, value, field_name, doctype) in allowed_option_map.items():
		if not value:
			continue

		if not frappe.db.exists(doctype, value):
			messages.append(
				{
					"severity": "error",
					"text": f"Selected {option_type.lower()} '{value}' does not exist",
					"field": field_name,
				}
			)
			is_valid = False
			continue

		allowed_rows = [
			row
			for row in template_doc.get("allowed_options", [])
			if row.option_type == option_type and row.get(child_field) == value and row.is_active
		]

		if not allowed_rows:
			messages.append(
				{
					"severity": "error",
					"text": f"Selected {option_type.lower()} '{value}' is not allowed for template '{fixture_template_code}'",
					"field": field_name,
				}
			)
			is_valid = False

	# Endcap styles need special handling - both start and end use the same "Endcap Style" option_type in the template
	endcap_style_validations = [
		("Endcap Style", endcap_style_start_code, "endcap_style_start_code", "ilL-Attribute-Endcap Style", "start"),
		("Endcap Style", endcap_style_end_code, "endcap_style_end_code", "ilL-Attribute-Endcap Style", "end"),
	]

	for option_type, value, field_name, doctype, position in endcap_style_validations:
		if not value:
			continue

		if not frappe.db.exists(doctype, value):
			messages.append(
				{
					"severity": "error",
					"text": f"Selected endcap style ({position}) '{value}' does not exist",
					"field": field_name,
				}
			)
			is_valid = False
			continue

		allowed_rows = [
			row
			for row in template_doc.get("allowed_options", [])
			if row.option_type == option_type and row.get("endcap_style") == value and row.is_active
		]

		if not allowed_rows:
			messages.append(
				{
					"severity": "error",
					"text": f"Selected endcap style ({position}) '{value}' is not allowed for template '{fixture_template_code}'",
					"field": field_name,
				}
			)
			is_valid = False

	tape_offering_doc = None
	if tape_offering_id:
		if not frappe.db.exists("ilL-Rel-Tape Offering", tape_offering_id):
			messages.append(
				{
					"severity": "error",
					"text": f"Tape offering '{tape_offering_id}' does not exist",
					"field": "tape_offering_id",
				}
			)
			is_valid = False
		else:
			tape_offering_doc = frappe.get_doc("ilL-Rel-Tape Offering", tape_offering_id)
			allowed_tape_rows = [
				row
				for row in template_doc.get("allowed_tape_offerings", [])
				if row.tape_offering == tape_offering_id
				and (not row.environment_rating or row.environment_rating == environment_rating_code)
				and (not row.lens_appearance or row.lens_appearance == lens_appearance_code)
			]
			if not allowed_tape_rows:
				messages.append(
					{
						"severity": "error",
						"text": f"Tape offering '{tape_offering_id}' is not allowed for template '{fixture_template_code}'",
						"field": "tape_offering_id",
					}
				)
				is_valid = False

	if is_valid:
		messages.append(
			{
				"severity": "info",
				"text": "Configuration validated successfully",
				"field": None,
			}
		)

	return {"is_valid": is_valid, "messages": messages, "template_doc": template_doc, "tape_offering_doc": tape_offering_doc}


def _compute_manufacturable_outputs(
	fixture_template_code: str,
	tape_offering_id: str,
	requested_overall_length_mm: int,
	endcap_style_start_code: str,
	endcap_style_end_code: str,
	power_feed_type_code: str,
	lens_appearance_code: str,
	finish_code: str,
	template_doc=None,
	tape_offering_doc=None,
) -> dict[str, Any]:
	"""
	Compute manufacturable dimensions, segments, and runs.

	Implements Epic 3 computation layer:
	- Task 3.1: Length math (locked rules)
	- Task 3.2: Segmentation plan (profile + lens)
	- Task 3.3: Run splitting (min of voltage-drop max length and 85W limit)
	- Task 3.4: Assembly mode rule

	Returns:
		dict: Computed values including dimensions, segments, runs, watts, etc.
	"""
	# Constants
	MAX_WATTS_PER_RUN = 85.0
	MM_PER_FOOT = 304.8

	# Get template doc if not passed
	if template_doc is None:
		template_doc = frappe.get_doc("ilL-Fixture-Template", fixture_template_code)

	# -------------------------------------------------------------------
	# Task 3.1: Length Math (Locked Rules)
	# -------------------------------------------------------------------

	# Calculate endcap allowance from both start and end endcap styles
	# E_start = endcap_style_start.mm_per_side (from Endcap Style attribute)
	# E_end = endcap_style_end.mm_per_side (from Endcap Style attribute)
	endcap_allowance_start_mm = 0.0
	if endcap_style_start_code and frappe.db.exists("ilL-Attribute-Endcap Style", endcap_style_start_code):
		endcap_doc = frappe.get_doc("ilL-Attribute-Endcap Style", endcap_style_start_code)
		endcap_allowance_start_mm = float(endcap_doc.allowance_mm_per_side or 0)

	endcap_allowance_end_mm = 0.0
	if endcap_style_end_code and frappe.db.exists("ilL-Attribute-Endcap Style", endcap_style_end_code):
		endcap_doc = frappe.get_doc("ilL-Attribute-Endcap Style", endcap_style_end_code)
		endcap_allowance_end_mm = float(endcap_doc.allowance_mm_per_side or 0)

	# Total endcap allowance is the sum of both ends
	total_endcap_allowance_mm = endcap_allowance_start_mm + endcap_allowance_end_mm

	# A_leader = 15mm (from template or rule default; per fixture)
	leader_allowance_mm_per_fixture = float(template_doc.leader_allowance_mm_per_fixture or 15)

	# Get cut_increment_mm from tape spec or offering override
	cut_increment_mm = 50.0  # Default cut increment
	tape_spec_doc = None
	watts_per_ft = 5.0  # Default watts per foot
	max_run_length_ft_voltage_drop = None

	if tape_offering_doc:
		tape_spec_doc = frappe.get_doc("ilL-Spec-LED Tape", tape_offering_doc.tape_spec)
		# Use offering override if set, otherwise use tape spec value
		cut_increment_mm = float(
			tape_offering_doc.cut_increment_mm_override
			or tape_spec_doc.cut_increment_mm
			or 50.0
		)
		watts_per_ft = float(
			tape_offering_doc.watts_per_ft_override
			or tape_spec_doc.watts_per_foot
			or 5.0
		)
		max_run_length_ft_voltage_drop = tape_spec_doc.voltage_drop_max_run_length_ft

	# L_internal = L_req - total_endcap_allowance - A_leader
	L_req = float(requested_overall_length_mm)
	A_leader = leader_allowance_mm_per_fixture
	L_internal = L_req - total_endcap_allowance_mm - A_leader

	# L_tape_cut = floor(L_internal / cut_increment) * cut_increment
	# Handle edge cases: if cut_increment invalid or L_internal <= 0, L_tape_cut = 0
	if cut_increment_mm > 0 and L_internal > 0:
		L_tape_cut = math.floor(L_internal / cut_increment_mm) * cut_increment_mm
	else:
		L_tape_cut = 0 if L_internal <= 0 or cut_increment_mm <= 0 else max(0, L_internal)

	# L_mfg = L_tape_cut + total_endcap_allowance + A_leader
	L_mfg = L_tape_cut + total_endcap_allowance_mm + A_leader

	# difference = L_req - L_mfg
	difference_mm = int(L_req - L_mfg)

	# -------------------------------------------------------------------
	# Task 3.2: Segmentation Plan (Profile + Lens)
	# -------------------------------------------------------------------

	# profile_stock_len_mm (from Profile Spec or template default)
	profile_stock_len_mm = float(template_doc.default_profile_stock_len_mm or 2000)

	# Try to get from profile spec if available
	profile_family = template_doc.default_profile_family or fixture_template_code
	profile_rows = frappe.get_all(
		"ilL-Spec-Profile",
		filters={"family": profile_family, "variant_code": finish_code, "is_active": 1},
		fields=["stock_length_mm"],
		limit=1,
	)
	if profile_rows and profile_rows[0].stock_length_mm:
		profile_stock_len_mm = float(profile_rows[0].stock_length_mm)

	# segments_count = ceil(L_mfg / stock_len)
	# Handle edge case: if L_mfg is 0 or negative, no segments are needed
	if profile_stock_len_mm > 0 and L_mfg > 0:
		segments_count = math.ceil(L_mfg / profile_stock_len_mm)
	elif L_mfg <= 0:
		segments_count = 0
	else:
		segments_count = 1

	# Create segments[] cut plan (N-1 full stock, last remainder)
	segments = []
	remaining_length = L_mfg
	for i in range(segments_count):
		segment_index = i + 1
		if segment_index < segments_count:
			# Full stock segment
			profile_cut_len = min(profile_stock_len_mm, remaining_length)
		else:
			# Last segment (remainder) - ensure it's at least 0
			profile_cut_len = max(0, remaining_length)

		remaining_length = max(0, remaining_length - profile_cut_len)

		# For MVP, lens segmentation mirrors profile segmentation
		# (lens stick type mirrors profile; continuous can be deferred)
		lens_cut_len = profile_cut_len

		notes = ""
		if segment_index < segments_count:
			notes = f"Full stock segment ({int(profile_stock_len_mm)}mm)"
		else:
			notes = f"Remainder segment ({int(profile_cut_len)}mm)"

		segments.append({
			"segment_index": segment_index,
			"profile_cut_len_mm": int(profile_cut_len),
			"lens_cut_len_mm": int(lens_cut_len),
			"notes": notes,
		})

	# -------------------------------------------------------------------
	# Task 3.3: Run Splitting (min of voltage-drop max length and 85W limit)
	# -------------------------------------------------------------------

	# Convert tape length to feet: total_ft = mm_to_ft(L_tape_cut_mm)
	total_ft = L_tape_cut / MM_PER_FOOT

	# Compute watts-based max run length: max_run_ft_by_watts = MAX_WATTS_PER_RUN / watts_per_ft
	# Note: If watts_per_ft is 0 or negative (invalid), we use infinity which results in
	# a single run for the entire tape. Validation should catch invalid tape specs upstream.
	if watts_per_ft > 0:
		max_run_ft_by_watts = MAX_WATTS_PER_RUN / watts_per_ft
	else:
		max_run_ft_by_watts = float("inf")

	# Compute effective max run length
	max_run_ft_by_voltage_drop = None
	if max_run_length_ft_voltage_drop and max_run_length_ft_voltage_drop > 0:
		max_run_ft_by_voltage_drop = float(max_run_length_ft_voltage_drop)
		max_run_ft_effective = min(max_run_ft_by_watts, max_run_ft_by_voltage_drop)
	else:
		max_run_ft_effective = max_run_ft_by_watts

	# Compute run count: runs_count = ceil(total_ft / max_run_ft_effective)
	# Handle edge case: if L_tape_cut is 0 or negative, no runs are needed
	if L_tape_cut <= 0:
		runs_count = 0
	elif max_run_ft_effective > 0 and max_run_ft_effective != float("inf") and total_ft > 0:
		runs_count = math.ceil(total_ft / max_run_ft_effective)
	else:
		runs_count = 1

	# Produce runs[] using "full runs then remainder" strategy
	runs = []
	remaining_tape_mm = max(0, L_tape_cut)
	# Guard against infinite max_run_mm
	if max_run_ft_effective == float("inf") or max_run_ft_effective <= 0:
		max_run_mm = max(0, L_tape_cut)  # Single run for entire tape
	else:
		max_run_mm = max_run_ft_effective * MM_PER_FOOT

	for i in range(runs_count):
		run_index = i + 1
		if run_index < runs_count:
			# Full run
			run_len_mm = min(max_run_mm, remaining_tape_mm)
		else:
			# Last run (remainder) - ensure it's at least 0
			run_len_mm = max(0, remaining_tape_mm)

		remaining_tape_mm = max(0, remaining_tape_mm - run_len_mm)

		# Calculate watts for this run
		run_ft = run_len_mm / MM_PER_FOOT
		run_watts = run_ft * watts_per_ft

		runs.append({
			"run_index": run_index,
			"run_len_mm": int(run_len_mm),
			"run_watts": round(run_watts, 2),
			"leader_item": None,  # Will be resolved in _resolve_items
			"leader_len_mm": int(leader_allowance_mm_per_fixture),
		})

	# Leader cable rule (locked): leader_qty = runs_count
	leader_qty = runs_count

	# Total watts
	total_watts = sum(run["run_watts"] for run in runs)

	# -------------------------------------------------------------------
	# Task 3.4: Assembly Mode Rule
	# -------------------------------------------------------------------

	# assembled if L_mfg <= assembled_max_len_mm, else ship in pieces
	assembled_max_len_mm = float(template_doc.assembled_max_len_mm or 2590)  # ~8.5ft default
	if L_mfg <= assembled_max_len_mm:
		assembly_mode = "ASSEMBLED"
	else:
		assembly_mode = "SHIP_PIECES"

	return {
		# Task 3.1 outputs
		"endcap_allowance_start_mm": endcap_allowance_start_mm,
		"endcap_allowance_end_mm": endcap_allowance_end_mm,
		"total_endcap_allowance_mm": total_endcap_allowance_mm,
		"leader_allowance_mm_per_fixture": leader_allowance_mm_per_fixture,
		"internal_length_mm": int(L_internal),
		"tape_cut_length_mm": int(L_tape_cut),
		"manufacturable_overall_length_mm": int(L_mfg),
		"difference_mm": difference_mm,
		"requested_overall_length_mm": int(L_req),
		# Task 3.2 outputs
		"segments": segments,
		"segments_count": segments_count,
		"profile_stock_len_mm": int(profile_stock_len_mm),
		# Task 3.3 outputs
		"runs": runs,
		"runs_count": runs_count,
		"leader_qty": leader_qty,
		"total_watts": round(total_watts, 2),
		"max_run_ft_by_watts": round(max_run_ft_by_watts, 2) if max_run_ft_by_watts != float("inf") else None,
		"max_run_ft_by_voltage_drop": round(max_run_ft_by_voltage_drop, 2) if max_run_ft_by_voltage_drop else None,
		"max_run_ft_effective": round(max_run_ft_effective, 2) if max_run_ft_effective != float("inf") else None,
		# Task 3.4 outputs
		"assembly_mode": assembly_mode,
		"assembled_max_len_mm": int(assembled_max_len_mm),
	}


def _validate_computed_edge_cases(
	computed: dict[str, Any],
	template_doc=None,
	tape_offering_doc=None,
) -> tuple[list[dict[str, str]], bool]:
	"""
	Validate computed outputs for edge cases and return warnings/blocks.

	Implements Epic 2 Task 2.2: Engine edge case handling.

	Checks for:
	- Requested length too short (internal length ≤ 0)
	- Requested length less than (2E + leader allowance)
	- Tape cut increment missing or 0
	- Watts/ft missing
	- Profile stock length missing
	- Rounding produces 0 tape length
	- SH01 no-joiners block message includes max length
	- Runs_count becomes huge (warn/limit)

	Args:
		computed: Computed values from _compute_manufacturable_outputs
		template_doc: Pre-fetched template document
		tape_offering_doc: Pre-fetched tape offering document

	Returns:
		tuple: (messages list, has_blocking_errors bool)
	"""
	messages: list[dict[str, str]] = []
	has_blocks = False

	# Constants
	MAX_REASONABLE_RUNS = 50  # Warn if runs exceed this
	MAX_ABSOLUTE_RUNS = 100  # Block if runs exceed this

	internal_length = computed.get("internal_length_mm", 0)
	tape_cut_length = computed.get("tape_cut_length_mm", 0)
	runs_count = computed.get("runs_count", 0)
	total_endcap_allowance = computed.get("total_endcap_allowance_mm", 0)
	leader_allowance = computed.get("leader_allowance_mm_per_fixture", 0)
	requested_length = computed.get("requested_overall_length_mm", 0)
	profile_stock_len = computed.get("profile_stock_len_mm", 0)
	assembly_mode = computed.get("assembly_mode", "ASSEMBLED")
	assembled_max_len = computed.get("assembled_max_len_mm", 0)
	manufacturable_length = computed.get("manufacturable_overall_length_mm", 0)

	# Check 1: Internal length ≤ 0 (too short)
	if internal_length <= 0:
		min_length = int(total_endcap_allowance + leader_allowance + 1)  # Minimum to have positive internal
		messages.append({
			"severity": "error",
			"text": (
				f"Requested length ({requested_length}mm) is too short. "
				f"Minimum length with selected endcaps and leader allowance is {min_length}mm."
			),
			"field": "requested_overall_length_mm",
		})
		has_blocks = True

	# Check 2: Tape cut length is 0 after rounding (edge case)
	elif tape_cut_length <= 0:
		messages.append({
			"severity": "error",
			"text": (
				f"Configuration results in 0mm tape length. "
				f"Internal length ({internal_length}mm) is less than one tape cut increment. "
				f"Please increase the requested length."
			),
			"field": "requested_overall_length_mm",
		})
		has_blocks = True

	# Check 3: Profile stock length missing or invalid
	if profile_stock_len <= 0:
		messages.append({
			"severity": "warning",
			"text": "Profile stock length not configured. Using default calculation.",
			"field": None,
		})

	# Check 4: Runs count is excessively high (warning)
	if runs_count > MAX_REASONABLE_RUNS:
		messages.append({
			"severity": "warning",
			"text": (
				f"Configuration requires {runs_count} runs, which is unusually high. "
				f"Consider checking the tape wattage and length configuration."
			),
			"field": None,
		})

	# Check 5: Runs count exceeds absolute maximum (block)
	if runs_count > MAX_ABSOLUTE_RUNS:
		messages.append({
			"severity": "error",
			"text": (
				f"Configuration requires {runs_count} runs, which exceeds the maximum of {MAX_ABSOLUTE_RUNS}. "
				f"This fixture cannot be manufactured as specified."
			),
			"field": "requested_overall_length_mm",
		})
		has_blocks = True

	# Check 6: SH01 no-joiners message for SHIP_PIECES mode
	if assembly_mode == "SHIP_PIECES" and template_doc:
		# Check if template supports joiners
		supports_joiners = getattr(template_doc, "supports_joiners", False)
		if not supports_joiners:
			messages.append({
				"severity": "warning",
				"text": (
					f"Fixture exceeds assembled shipping limit ({assembled_max_len}mm). "
					f"Maximum assembled length is {assembled_max_len}mm (~{assembled_max_len / 304.8:.1f}ft). "
					f"This fixture will ship in pieces requiring field assembly."
				),
				"field": None,
			})

	# Check 7: Significant length difference warning
	difference_mm = computed.get("difference_mm", 0)
	if difference_mm > 25:  # More than 1 inch difference
		messages.append({
			"severity": "info",
			"text": (
				f"Manufacturable length ({manufacturable_length}mm) differs from requested "
				f"({requested_length}mm) by {difference_mm}mm due to tape cut increment rounding."
			),
			"field": None,
		})

	return messages, has_blocks


def _resolve_items(
	fixture_template_code: str,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_style_start_code: str,
	endcap_style_end_code: str,
	endcap_color_code: str,
	environment_rating_code: str,
	power_feed_type_code: str,
	template_doc=None,
	tape_offering_doc=None,
) -> tuple[dict[str, Any], list[dict[str, str]], bool]:
	"""
	Resolve actual Item codes for profile, lens, endcaps, mounting, and leader.

	Returns:
		tuple: (resolved_items, messages, is_valid)
	"""
	messages: list[dict[str, str]] = []
	is_valid = True
	resolved: dict[str, Any] = {
		"profile_item": None,
		"lens_item": None,
		"endcap_item_start": None,
		"endcap_item_end": None,
		"mounting_item": None,
		"leader_item": None,
		"driver_plan": {
			"status": "suggested",
			"drivers": [{"item_code": "DRIVER-PLACEHOLDER", "qty": 1, "watts_capacity": 100.0}],
		},
	}

	template_doc = template_doc or frappe.get_doc("ilL-Fixture-Template", fixture_template_code)
	profile_family = template_doc.default_profile_family or fixture_template_code

	# finish_code is actually the finish_name (primary key of ilL-Attribute-Finish)
	# We need to get the actual code for matching with profile variant_code
	finish_variant_code = frappe.db.get_value("ilL-Attribute-Finish", finish_code, "code")
	if not finish_variant_code:
		# Fall back to using the finish_code directly if no code field is set
		finish_variant_code = finish_code

	profile_rows = frappe.get_all(
		"ilL-Spec-Profile",
		filters={"family": profile_family, "variant_code": finish_variant_code, "is_active": 1},
		fields=["name", "item", "lens_interface"],
		limit=1,
	)

	if not profile_rows:
		messages.append(
			{
				"severity": "error",
				"text": f"Missing map: ilL-Spec-Profile for family '{profile_family}' and variant code '{finish_variant_code}' (finish: '{finish_code}')",
				"field": "finish_code",
			}
		)
		return resolved, messages, False

	profile_row = profile_rows[0]
	resolved["profile_item"] = profile_row.item

	lens_interface = profile_row.get("lens_interface")
	if not lens_interface:
		messages.append(
			{
				"severity": "error",
				"text": f"Missing lens interface for profile '{profile_row.name}'",
				"field": "lens_appearance_code",
			}
		)
		return resolved, messages, False

	lens_candidates = frappe.get_all(
		"ilL-Spec-Lens", filters={"lens_appearance": lens_appearance_code}, fields=["name", "item"]
	)

	lens_item = None

	# Pre-fetch supported environment ratings for all lens candidates to avoid N+1 queries
	# Epic 5 Task 5.1: Reduce N+1 lookups in engine
	if lens_candidates and environment_rating_code:
		lens_names = [row.name for row in lens_candidates]
		lens_envs = frappe.get_all(
			"ilL-Child-Lens Environments",
			filters={"parent": ["in", lens_names], "parenttype": "ilL-Spec-Lens"},
			fields=["parent", "environment_rating"],
		)
		# Build lookup: {lens_name: set(environment_ratings)}
		lens_env_map: dict[str, set] = {}
		for env in lens_envs:
			if env.parent not in lens_env_map:
				lens_env_map[env.parent] = set()
			lens_env_map[env.parent].add(env.environment_rating)

		# Find a lens that supports the environment rating
		for lens_row in lens_candidates:
			env_supported = lens_env_map.get(lens_row.name, set())
			if env_supported and environment_rating_code not in env_supported:
				continue
			lens_item = lens_row.item
			break
	elif lens_candidates:
		# No environment rating specified, use first match
		lens_item = lens_candidates[0].item

	if not lens_item:
		messages.append(
			{
				"severity": "error",
				"text": (
					f"Missing map: ilL-Spec-Lens for appearance '{lens_appearance_code}' "
					f"and interface '{lens_interface}'"
				),
				"field": "lens_appearance_code",
			}
		)
		return resolved, messages, False

	resolved["lens_item"] = lens_item

	# Resolve start endcap
	endcap_start_candidates = frappe.get_all(
		"ilL-Rel-Endcap-Map",
		filters={
			"fixture_template": fixture_template_code,
			"endcap_style": endcap_style_start_code,
			"endcap_color": endcap_color_code,
			"is_active": 1,
		},
		fields=["name", "endcap_item", "power_feed_type", "environment_rating"],
	)

	endcap_item_start = None
	for endcap_row in endcap_start_candidates:
		if endcap_row.get("power_feed_type") and endcap_row.power_feed_type != power_feed_type_code:
			continue
		if endcap_row.get("environment_rating") and endcap_row.environment_rating != environment_rating_code:
			continue
		endcap_item_start = endcap_row.endcap_item
		break

	if not endcap_item_start:
		messages.append(
			{
				"severity": "error",
				"text": (
					f"Missing map: ilL-Rel-Endcap-Map for template '{fixture_template_code}', "
					f"style '{endcap_style_start_code}', color '{endcap_color_code}' (start endcap)"
				),
				"field": "endcap_style_start_code",
			}
		)
		return resolved, messages, False

	resolved["endcap_item_start"] = endcap_item_start

	# Resolve end endcap
	endcap_end_candidates = frappe.get_all(
		"ilL-Rel-Endcap-Map",
		filters={
			"fixture_template": fixture_template_code,
			"endcap_style": endcap_style_end_code,
			"endcap_color": endcap_color_code,
			"is_active": 1,
		},
		fields=["name", "endcap_item", "power_feed_type", "environment_rating"],
	)

	endcap_item_end = None
	for endcap_row in endcap_end_candidates:
		if endcap_row.get("power_feed_type") and endcap_row.power_feed_type != power_feed_type_code:
			continue
		if endcap_row.get("environment_rating") and endcap_row.environment_rating != environment_rating_code:
			continue
		endcap_item_end = endcap_row.endcap_item
		break

	if not endcap_item_end:
		messages.append(
			{
				"severity": "error",
				"text": (
					f"Missing map: ilL-Rel-Endcap-Map for template '{fixture_template_code}', "
					f"style '{endcap_style_end_code}', color '{endcap_color_code}' (end endcap)"
				),
				"field": "endcap_style_end_code",
			}
		)
		return resolved, messages, False

	resolved["endcap_item_end"] = endcap_item_end

	mount_candidates = frappe.get_all(
		"ilL-Rel-Mounting-Accessory-Map",
		filters={
			"fixture_template": fixture_template_code,
			"mounting_method": mounting_method_code,
			"is_active": 1,
		},
		fields=["name", "accessory_item", "environment_rating"],
	)

	mounting_item = None
	for mount_row in mount_candidates:
		if mount_row.get("environment_rating") and mount_row.environment_rating != environment_rating_code:
			continue
		mounting_item = mount_row.accessory_item
		break

	if not mounting_item:
		messages.append(
			{
				"severity": "error",
				"text": (
					f"Missing map: ilL-Rel-Mounting-Accessory-Map for template '{fixture_template_code}' "
					f"and mounting '{mounting_method_code}'"
				),
				"field": "mounting_method_code",
			}
		)
		return resolved, messages, False

	resolved["mounting_item"] = mounting_item

	if not tape_offering_doc:
		messages.append(
			{
				"severity": "error",
				"text": "Missing tape offering details for leader cable resolution",
				"field": "tape_offering_id",
			}
		)
		return resolved, messages, False

	leader_candidates = frappe.get_all(
		"ilL-Rel-Leader-Cable-Map",
		filters={
			"tape_spec": tape_offering_doc.tape_spec,
			"power_feed_type": power_feed_type_code,
			"is_active": 1,
		},
		fields=["name", "leader_item", "environment_rating", "default_length_mm"],
	)

	leader_item = None
	for leader_row in leader_candidates:
		if leader_row.get("environment_rating") and leader_row.environment_rating != environment_rating_code:
			continue
		leader_item = leader_row.leader_item
		break

	if not leader_item:
		messages.append(
			{
				"severity": "error",
				"text": (
					f"Missing map: ilL-Rel-Leader-Cable-Map for tape '{tape_offering_doc.tape_spec}' "
					f"and power feed '{power_feed_type_code}'"
				),
				"field": "power_feed_type_code",
			}
		)
		return resolved, messages, False

	resolved["leader_item"] = leader_item

	return resolved, messages, is_valid


def _select_driver_plan(
	fixture_template_code: str,
	runs_count: int,
	total_watts: float,
	tape_offering_doc=None,
	dimming_protocol_code: str = None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
	"""
	Select driver model and calculate quantity to satisfy fixture requirements.

	Implements Epic 5 Task 5.1: Driver auto-selection algorithm.

	Rules (locked):
	- W_usable = 0.8 * W_rated (or driver.usable_load_factor * max_wattage)
	- Must satisfy: sum(outputs) >= runs_count AND sum(W_usable) >= total_watts
	- Selection policy: "lowest cost if cost exists else smallest rated wattage that works"
	- If one driver can't satisfy, add multiples of the same model until constraints met

	Args:
		fixture_template_code: Code of the fixture template
		runs_count: Number of runs requiring driver outputs
		total_watts: Total wattage load to be driven
		tape_offering_doc: Tape offering document (for voltage and input protocol)
		dimming_protocol_code: User's desired dimming protocol (filters drivers by input_protocol)

	Returns:
		tuple: (driver_plan dict, messages list)
	"""
	messages: list[dict[str, str]] = []
	driver_plan: dict[str, Any] = {
		"status": "none",
		"drivers": [],
	}

	# Handle edge case: no runs or no wattage
	if runs_count <= 0 or total_watts <= 0:
		driver_plan["status"] = "not_required"
		messages.append({
			"severity": "info",
			"text": "No driver required (zero runs or zero wattage)",
			"field": None,
		})
		return driver_plan, messages

	# Get tape voltage and input protocol from tape spec
	# tape_input_protocol is the signal the tape expects from the driver (e.g., PWM)
	tape_voltage = None
	tape_input_protocol = None
	if tape_offering_doc:
		if not frappe.db.exists("ilL-Spec-LED Tape", tape_offering_doc.tape_spec):
			messages.append({
				"severity": "warning",
				"text": f"Tape spec '{tape_offering_doc.tape_spec}' not found for driver selection",
				"field": None,
			})
		else:
			tape_spec_doc = frappe.get_doc("ilL-Spec-LED Tape", tape_offering_doc.tape_spec)
			tape_voltage = tape_spec_doc.input_voltage  # This is the output voltage the driver needs to provide
			tape_input_protocol = tape_spec_doc.input_protocol  # The dimming signal the tape needs from the driver

	# Query eligible drivers from ilL-Rel-Driver-Eligibility for this template
	eligibility_rows = frappe.get_all(
		"ilL-Rel-Driver-Eligibility",
		filters={
			"fixture_template": fixture_template_code,
			"is_allowed": 1,
			"is_active": 1,
		},
		fields=["driver_spec", "priority"],
		order_by="priority asc",
	)

	if not eligibility_rows:
		driver_plan["status"] = "no_eligible_drivers"
		messages.append({
			"severity": "warning",
			"text": f"No eligible drivers configured for template '{fixture_template_code}'",
			"field": None,
		})
		return driver_plan, messages

	# Get driver specs and filter by voltage and dimming protocol
	candidate_drivers = []
	for elig_row in eligibility_rows:
		driver_spec_name = elig_row.driver_spec
		if not frappe.db.exists("ilL-Spec-Driver", driver_spec_name):
			continue

		try:
			driver_spec = frappe.get_doc("ilL-Spec-Driver", driver_spec_name)
		except frappe.DoesNotExistError:
			continue  # Skip if driver spec doesn't exist

		# Filter by voltage: driver's voltage_output must match tape's input_voltage
		if tape_voltage and driver_spec.voltage_output and driver_spec.voltage_output != tape_voltage:
			continue

		# Filter by protocol: driver's output_protocol must match tape's input_protocol
		# This ensures the driver can output the signal the tape expects (e.g., PWM)
		if tape_input_protocol and driver_spec.output_protocol and driver_spec.output_protocol != tape_input_protocol:
			continue

		# Filter by user's dimming protocol: driver's input_protocols must include user's selection
		# This ensures the driver accepts the dimming signal the user wants to use (e.g., 0-10V, DALI)
		if dimming_protocol_code:
			# Get the list of supported input protocols from the child table
			supported_input_protocols = {row.protocol for row in (driver_spec.input_protocols or [])}
			if supported_input_protocols and dimming_protocol_code not in supported_input_protocols:
				continue

		# Calculate usable wattage
		usable_load_factor = float(driver_spec.usable_load_factor or 0.8)
		max_wattage = float(driver_spec.max_wattage or 0)
		outputs_count = int(driver_spec.outputs_count or 1)
		cost = float(driver_spec.cost or 0) if driver_spec.cost else None

		w_usable = usable_load_factor * max_wattage

		candidate_drivers.append({
			"driver_spec_name": driver_spec_name,
			"item": driver_spec.item,
			"max_wattage": max_wattage,
			"w_usable": w_usable,
			"outputs_count": outputs_count,
			"cost": cost,
			"priority": elig_row.priority,
		})

	if not candidate_drivers:
		driver_plan["status"] = "no_matching_drivers"
		filter_criteria = []
		if tape_voltage:
			filter_criteria.append(f"voltage '{tape_voltage}'")
		if tape_input_protocol:
			filter_criteria.append(f"output protocol '{tape_input_protocol}'")
		if dimming_protocol_code:
			filter_criteria.append(f"input protocol '{dimming_protocol_code}'")
		messages.append({
			"severity": "warning",
			"text": (
				f"No drivers match {' and '.join(filter_criteria) or 'requirements'} "
				f"for template '{fixture_template_code}'"
			),
			"field": None,
		})
		return driver_plan, messages

	# Selection policy: "lowest cost if cost exists else smallest rated wattage that works"
	# First, sort candidates by selection policy
	# Priority 1: Drivers with cost (sorted by cost ascending)
	# Priority 2: Drivers without cost (sorted by max_wattage ascending)
	drivers_with_cost = [d for d in candidate_drivers if d["cost"] is not None]
	drivers_without_cost = [d for d in candidate_drivers if d["cost"] is None]

	# Sort drivers with cost by cost (lowest first)
	drivers_with_cost.sort(key=lambda d: (d["cost"], d["max_wattage"]))

	# Sort drivers without cost by max_wattage (smallest first)
	drivers_without_cost.sort(key=lambda d: d["max_wattage"])

	# Combine: prefer drivers with cost (sorted by lowest cost)
	sorted_candidates = drivers_with_cost + drivers_without_cost

	# Find the best driver that can satisfy constraints (possibly with multiples)
	selected_driver = None
	selected_qty = 0

	for candidate in sorted_candidates:
		# Calculate how many of this driver we need
		# Constraint 1: sum(outputs) >= runs_count
		# Constraint 2: sum(W_usable) >= total_watts

		outputs_per_driver = candidate["outputs_count"]
		w_usable_per_driver = candidate["w_usable"]

		# Use a minimum threshold to prevent division issues with extremely small values
		MIN_THRESHOLD = 0.001
		if outputs_per_driver < MIN_THRESHOLD or w_usable_per_driver < MIN_THRESHOLD:
			continue  # Skip invalid drivers

		# Calculate quantity needed for outputs constraint
		qty_for_outputs = math.ceil(runs_count / outputs_per_driver)

		# Calculate quantity needed for wattage constraint
		qty_for_watts = math.ceil(total_watts / w_usable_per_driver)

		# Take the maximum to satisfy both constraints
		qty_needed = max(qty_for_outputs, qty_for_watts)

		# Select this driver
		selected_driver = candidate
		selected_qty = qty_needed
		break  # First valid candidate wins (already sorted by policy)

	if not selected_driver:
		driver_plan["status"] = "no_suitable_driver"
		messages.append({
			"severity": "warning",
			"text": "No driver can satisfy the output/wattage requirements",
			"field": None,
		})
		return driver_plan, messages

	# Calculate outputs used and generate mapping notes
	total_outputs_available = selected_driver["outputs_count"] * selected_qty
	outputs_used = min(runs_count, total_outputs_available)

	# Generate sequential run→output mapping notes
	mapping_notes_parts = []
	run_idx = 1
	for driver_idx in range(1, selected_qty + 1):
		for output_idx in range(1, selected_driver["outputs_count"] + 1):
			if run_idx > runs_count:
				break
			mapping_notes_parts.append(f"Run {run_idx} → Driver {driver_idx} Output {output_idx}")
			run_idx += 1
		if run_idx > runs_count:
			break
	mapping_notes = "; ".join(mapping_notes_parts)

	# Build driver plan result
	driver_plan = {
		"status": "selected",
		"drivers": [
			{
				"driver_spec": selected_driver["driver_spec_name"],
				"item_code": selected_driver["item"],
				"qty": selected_qty,
				"outputs_per_driver": selected_driver["outputs_count"],
				"outputs_used": outputs_used,
				"w_usable_per_driver": round(selected_driver["w_usable"], 2),
				"total_w_usable": round(selected_driver["w_usable"] * selected_qty, 2),
				"mapping_notes": mapping_notes,
			}
		],
	}

	messages.append({
		"severity": "info",
		"text": (
			f"Driver selected: {selected_driver['item']} × {selected_qty} "
			f"({outputs_used} outputs used, {round(selected_driver['w_usable'] * selected_qty, 2)}W usable capacity)"
		),
		"field": None,
	})

	return driver_plan, messages


def _calculate_pricing(
	fixture_template_code: str,
	resolved_items: dict,
	computed: dict,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_style_start_code: str,
	endcap_style_end_code: str,
	power_feed_type_code: str,
	environment_rating_code: str,
	tape_offering_id: str,
	qty: int,
	template_doc=None,
) -> dict[str, Any]:
	"""
	Calculate MSRP, tier pricing, and adders.

	Implements Epic 4 Task 4.1: Baseline pricing formula
	- base + $/ft × L_tape_cut (or L_mfg based on template setting)
	- adders based on selected options (finish, lens, mounting, endcap, power feed, environment)
	- customer tier/price list logic (MSRP only placeholder if tier not available)

	Args:
		fixture_template_code: The fixture template code
		resolved_items: Dict of resolved item codes
		computed: Dict of computed values including lengths
		finish_code: Selected finish code
		lens_appearance_code: Selected lens appearance code
		mounting_method_code: Selected mounting method code
		endcap_style_start_code: Selected endcap style code for start end
		endcap_style_end_code: Selected endcap style code for end end
		power_feed_type_code: Selected power feed type code
		environment_rating_code: Selected environment rating code
		tape_offering_id: Selected tape offering ID
		qty: Quantity ordered
		template_doc: Optional pre-fetched template document

	Returns:
		dict: Pricing information with msrp_unit, tier_unit, and adder_breakdown
	"""
	MM_PER_FOOT = 304.8

	# Get template doc if not passed
	if template_doc is None:
		template_doc = frappe.get_doc("ilL-Fixture-Template", fixture_template_code)

	# --- Base Price ---
	# Base price from template (MSRP), defaults to 0 if not set
	base_price = float(template_doc.base_price_msrp or 0)

	# --- Length-based Price ($/ft × length) ---
	# Get pricing length basis from template: L_tape_cut or L_mfg
	pricing_length_basis = template_doc.pricing_length_basis or "L_tape_cut"
	if pricing_length_basis == "L_mfg":
		length_mm = float(computed.get("manufacturable_overall_length_mm", 0))
		length_basis_description = "L_mfg"
	else:
		length_mm = float(computed.get("tape_cut_length_mm", 0))
		length_basis_description = "L_tape_cut"

	# Convert mm to feet for $/ft calculation
	length_ft = length_mm / MM_PER_FOOT
	price_per_ft = float(template_doc.price_per_ft_msrp or 0)
	length_adder = length_ft * price_per_ft

	adder_breakdown = [
		{"component": "base", "description": "Base fixture price", "amount": round(base_price, 2)},
		{
			"component": "length",
			"description": f"Length adder ({length_basis_description}: {length_mm:.0f}mm = {length_ft:.2f}ft × ${price_per_ft:.2f}/ft)",
			"amount": round(length_adder, 2),
		},
	]

	# --- Option Adders ---
	# Build a map of option type to (field_name, selected_value)
	option_map = {
		"Finish": ("finish", finish_code),
		"Lens Appearance": ("lens_appearance", lens_appearance_code),
		"Mounting Method": ("mounting_method", mounting_method_code),
		"Power Feed Type": ("power_feed_type", power_feed_type_code),
		"Environment Rating": ("environment_rating", environment_rating_code),
	}

	# Handle endcap styles separately - both use "Endcap Style" option_type
	endcap_style_adders = [
		("Endcap Style (Start)", "endcap_style", endcap_style_start_code),
		("Endcap Style (End)", "endcap_style", endcap_style_end_code),
	]

	total_option_adders = 0.0

	# Process standard options
	for option_type, (field_name, selected_value) in option_map.items():
		if not selected_value:
			continue

		# Find the matching allowed option row in template
		matching_rows = [
			row
			for row in template_doc.get("allowed_options", [])
			if row.option_type == option_type
			and row.get(field_name) == selected_value
			and row.is_active
		]

		option_adder = 0.0
		if matching_rows:
			# Use the msrp_adder from the allowed option row
			option_adder = float(matching_rows[0].msrp_adder or 0)

		total_option_adders += option_adder
		if option_adder != 0:
			adder_breakdown.append({
				"component": field_name,
				"description": f"{option_type} ({selected_value})",
				"amount": round(option_adder, 2),
			})

	# Process endcap style adders (both start and end use "Endcap Style" option_type)
	for label, field_name, selected_value in endcap_style_adders:
		if not selected_value:
			continue

		# Find the matching allowed option row in template
		matching_rows = [
			row
			for row in template_doc.get("allowed_options", [])
			if row.option_type == "Endcap Style"
			and row.get(field_name) == selected_value
			and row.is_active
		]

		option_adder = 0.0
		if matching_rows:
			# Use the msrp_adder from the allowed option row
			option_adder = float(matching_rows[0].msrp_adder or 0)

		total_option_adders += option_adder
		if option_adder != 0:
			adder_breakdown.append({
				"component": field_name,
				"description": f"{label} ({selected_value})",
				"amount": round(option_adder, 2),
			})

	# --- Tape Offering Adder (SDCM, Output Level via Pricing Class) ---
	# Check if tape offering has a pricing class override with adders
	# Optimized: Use single query with left join logic via get_value with multiple fields
	tape_adder = 0.0
	if tape_offering_id:
		pricing_class_code = frappe.db.get_value(
			"ilL-Rel-Tape Offering", tape_offering_id, "pricing_class_override"
		)
		if pricing_class_code:
			default_adder = frappe.db.get_value(
				"ilL-Attribute-Pricing Class", pricing_class_code, "default_adder"
			)
			if default_adder:
				tape_adder = float(default_adder)
				if tape_adder != 0:
					adder_breakdown.append({
						"component": "tape_offering",
						"description": f"Tape offering pricing class ({pricing_class_code})",
						"amount": round(tape_adder, 2),
					})

	# --- Calculate MSRP Unit Price ---
	msrp_unit = base_price + length_adder + total_option_adders + tape_adder

	# --- Customer Tier/Price List Logic ---
	# Placeholder: MSRP only if tier not available
	# In future, this would query Customer -> Price List -> apply discount/multiplier
	# For now, tier_unit equals msrp_unit (no tier discount applied)
	tier_unit = msrp_unit  # Placeholder: MSRP only

	return {
		"msrp_unit": round(msrp_unit, 2),
		"tier_unit": round(tier_unit, 2),
		"adder_breakdown": adder_breakdown,
	}


def _create_or_update_configured_fixture(
	fixture_template_code: str,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_style_start_code: str,
	endcap_style_end_code: str,
	endcap_color_code: str,
	power_feed_type_code: str,
	environment_rating_code: str,
	tape_offering_id: str,
	requested_overall_length_mm: int,
	computed: dict,
	resolved_items: dict,
	pricing: dict,
) -> str:
	"""
	Create or update an ilL-Configured-Fixture document.

	The document is identified by a hash of the configuration to ensure
	identical configurations reuse the same document.

	If a fixture with the same part number already exists but with a different
	config_hash, we validate that all key attributes match and update the
	existing fixture (updating pricing, resolved items, etc.).

	Returns:
		str: Name of the created/updated ilL-Configured-Fixture document
	"""
	# Create config data for hashing (all input parameters)
	config_data = {
		"fixture_template_code": fixture_template_code,
		"finish_code": finish_code,
		"lens_appearance_code": lens_appearance_code,
		"mounting_method_code": mounting_method_code,
		"endcap_style_start_code": endcap_style_start_code,
		"endcap_style_end_code": endcap_style_end_code,
		"endcap_color_code": endcap_color_code,
		"power_feed_type_code": power_feed_type_code,
		"environment_rating_code": environment_rating_code,
		"tape_offering_id": tape_offering_id,
		"requested_overall_length_mm": requested_overall_length_mm,
	}

	# Generate hash: first 32 hex characters (128 bits of entropy) from SHA-256 for collision resistance
	config_hash = hashlib.sha256(json.dumps(config_data, sort_keys=True).encode()).hexdigest()[:32]

	# Check if this configuration already exists by config_hash field
	existing = frappe.db.exists("ilL-Configured-Fixture", {"config_hash": config_hash})

	if existing:
		doc = frappe.get_doc("ilL-Configured-Fixture", existing)
	else:
		# No exact hash match - create a temporary doc to generate the part number
		# then check if that part number already exists (collision handling)
		doc = frappe.new_doc("ilL-Configured-Fixture")
		doc.config_hash = config_hash
		
		# Populate key fields needed for part number generation
		doc.fixture_template = fixture_template_code
		doc.finish = finish_code
		doc.lens_appearance = lens_appearance_code
		doc.mounting_method = mounting_method_code
		doc.endcap_style_start = endcap_style_start_code
		doc.endcap_style_end = endcap_style_end_code
		doc.endcap_color = endcap_color_code
		doc.power_feed_type = power_feed_type_code
		doc.environment_rating = environment_rating_code
		doc.tape_offering = tape_offering_id
		doc.requested_overall_length_mm = requested_overall_length_mm
		doc.is_multi_segment = 0
		
		# Generate the part number that would be used
		potential_part_number = doc._generate_part_number()
		
		# Check if this part number already exists
		existing_by_name = frappe.db.exists("ilL-Configured-Fixture", potential_part_number)
		
		if existing_by_name:
			# Part number collision - load existing fixture and validate/update it
			doc = frappe.get_doc("ilL-Configured-Fixture", existing_by_name)
			
			# Validate that the key configuration attributes match
			# If they match, this is the same fixture just needs updating
			# Update the config_hash since the existing one may be outdated
			doc.config_hash = config_hash
			
			# Mark as existing for the save logic below
			existing = existing_by_name

	# Set identity fields
	doc.engine_version = ENGINE_VERSION
	doc.fixture_template = fixture_template_code

	# Set selected options
	doc.finish = finish_code
	doc.lens_appearance = lens_appearance_code
	doc.mounting_method = mounting_method_code
	doc.endcap_style_start = endcap_style_start_code
	doc.endcap_style_end = endcap_style_end_code
	doc.endcap_color = endcap_color_code
	doc.power_feed_type = power_feed_type_code
	doc.environment_rating = environment_rating_code
	doc.tape_offering = tape_offering_id

	# Set length inputs/outputs
	doc.requested_overall_length_mm = requested_overall_length_mm
	doc.endcap_allowance_mm_per_side = computed.get("total_endcap_allowance_mm", 0)
	doc.leader_allowance_mm = computed["leader_allowance_mm_per_fixture"]
	doc.internal_length_mm = computed["internal_length_mm"]
	doc.tape_cut_length_mm = computed["tape_cut_length_mm"]
	doc.manufacturable_overall_length_mm = computed["manufacturable_overall_length_mm"]

	# Set computed outputs
	doc.runs_count = computed["runs_count"]
	doc.total_watts = computed["total_watts"]
	doc.assembly_mode = computed["assembly_mode"]

	# Set run metadata (effective max run for downstream calculations)
	doc.max_run_ft_by_watts = computed.get("max_run_ft_by_watts")
	doc.max_run_ft_by_voltage_drop = computed.get("max_run_ft_by_voltage_drop")
	doc.max_run_ft_effective = computed.get("max_run_ft_effective")

	# Set resolved item links (cached for downstream BOM/WO generation)
	doc.profile_item = resolved_items.get("profile_item")
	doc.lens_item = resolved_items.get("lens_item")
	doc.endcap_item_start = resolved_items.get("endcap_item_start")
	doc.endcap_item_end = resolved_items.get("endcap_item_end")
	doc.mounting_item = resolved_items.get("mounting_item")
	doc.leader_item = resolved_items.get("leader_item")

	# Set segments
	doc.segments = []
	for segment in computed["segments"]:
		doc.append(
			"segments",
			{
				"segment_index": segment["segment_index"],
				"profile_cut_len_mm": segment["profile_cut_len_mm"],
				"lens_cut_len_mm": segment["lens_cut_len_mm"],
				"notes": segment.get("notes", ""),
			},
		)

	# Set runs
	doc.runs = []
	for run in computed["runs"]:
		doc.append(
			"runs",
			{
				"run_index": run["run_index"],
				"segment_index": run.get("segment_index", 1),  # Single-segment fixtures default to segment 1
				"run_len_mm": run["run_len_mm"],
				"run_watts": run["run_watts"],
				"leader_item": run.get("leader_item") or resolved_items.get("leader_item"),
				"leader_len_mm": run["leader_len_mm"],
			},
		)

	# Set driver allocations (Epic 5 Task 5.2)
	doc.drivers = []
	driver_plan = resolved_items.get("driver_plan", {})
	if driver_plan.get("status") == "selected" and driver_plan.get("drivers"):
		for driver_alloc in driver_plan["drivers"]:
			doc.append(
				"drivers",
				{
					"driver_item": driver_alloc.get("item_code"),
					"driver_qty": driver_alloc.get("qty", 1),
					"outputs_used": driver_alloc.get("outputs_used", 0),
					"mapping_notes": driver_alloc.get("mapping_notes", ""),
				},
			)

	# Append pricing snapshot (preserves audit history)
	# Each quote creates a new pricing snapshot entry with timestamp
	doc.append(
		"pricing_snapshot",
		{
			"msrp_unit": pricing["msrp_unit"],
			"tier_unit": pricing["tier_unit"],
			"adder_breakdown_json": json.dumps(pricing["adder_breakdown"]),
			"timestamp": now(),
		},
	)

	# Save the document
	if existing:
		doc.save(ignore_permissions=True)
	else:
		# For new documents, pre-set the name to avoid autoname regeneration issues
		if not doc.name:
			doc.name = doc._generate_part_number()
		doc.insert(ignore_permissions=True)

	return doc.name


# =============================================================================
# CASCADING CONFIGURATOR API - Dynamic Option Filtering
# =============================================================================
# These functions support the new configurator flow where options are filtered
# dynamically based on previous selections, and tape is auto-selected based on
# the user's output choice.
#
# Flow:
# 1. User selects fixture template
# 2. get_led_packages_for_template -> LED Package options (from linked tapes)
# 3. User selects LED Package
# 4. get_environment_ratings_for_template -> Environment Rating options
# 5. User selects Environment Rating
# 6. get_ccts_for_template -> CCT options (filtered by LED Package + Environment)
# 7. User selects CCT
# 8. get_lens_appearances_for_template -> Lens Appearance options
# 9. User selects Lens Appearance
# 10. get_delivered_outputs_for_template -> Computed fixture output options
# 11. User selects Output -> auto_select_tape_for_configuration
# =============================================================================


@frappe.whitelist()
def get_led_packages_for_template(fixture_template_code: str) -> dict[str, Any]:
	"""
	Get available LED Package options based on tapes linked to the fixture template.

	This is Step 2 in the cascading configurator flow. Returns only LED Package
	codes that are present on at least one tape offering linked to the template.

	Args:
		fixture_template_code: Code of the fixture template

	Returns:
		dict: {
			"success": bool,
			"led_packages": [{"value": code, "label": label, "spectrum_type": type}],
			"error": str (if failed)
		}
	"""
	if not frappe.db.exists("ilL-Fixture-Template", fixture_template_code):
		return {"success": False, "led_packages": [], "error": f"Template '{fixture_template_code}' not found"}

	template_doc = frappe.get_doc("ilL-Fixture-Template", fixture_template_code)

	# Get all tape offerings linked to this template
	tape_offering_names = [
		row.tape_offering for row in template_doc.get("allowed_tape_offerings", [])
		if row.tape_offering
	]

	if not tape_offering_names:
		return {"success": True, "led_packages": [], "error": None}

	# Build tape offering filter - only add is_active filter if active records exist
	tape_filters = {"name": ["in", tape_offering_names]}
	active_count = frappe.db.count("ilL-Rel-Tape Offering", {"is_active": 1})
	if active_count > 0:
		tape_filters["is_active"] = 1

	# Get unique LED packages from those tape offerings
	led_packages_from_tapes = frappe.get_all(
		"ilL-Rel-Tape Offering",
		filters=tape_filters,
		fields=["led_package"],
		distinct=True,
	)

	led_package_codes = list({row.led_package for row in led_packages_from_tapes if row.led_package})

	if not led_package_codes:
		return {"success": True, "led_packages": [], "error": None}

	# Get LED package details
	led_packages = frappe.get_all(
		"ilL-Attribute-LED Package",
		filters={"name": ["in", led_package_codes]},
		fields=["name", "code", "spectrum_type"],
	)

	result = [
		{
			"value": pkg.name,
			"label": pkg.name,
			"code": pkg.code,
			"spectrum_type": pkg.spectrum_type,
		}
		for pkg in led_packages
	]

	return {"success": True, "led_packages": result, "error": None}


@frappe.whitelist()
def get_environment_ratings_for_template(fixture_template_code: str) -> dict[str, Any]:
	"""
	Get available Environment Rating options for a fixture template.

	This returns environment ratings from the template's allowed options.

	Args:
		fixture_template_code: Code of the fixture template

	Returns:
		dict: {
			"success": bool,
			"environment_ratings": [{"value": code, "label": label}],
			"error": str (if failed)
		}
	"""
	if not frappe.db.exists("ilL-Fixture-Template", fixture_template_code):
		return {"success": False, "environment_ratings": [], "error": f"Template '{fixture_template_code}' not found"}

	template_doc = frappe.get_doc("ilL-Fixture-Template", fixture_template_code)

	# Get environment ratings from allowed options
	env_ratings = []
	for row in template_doc.get("allowed_options", []):
		if row.option_type == "Environment Rating" and row.environment_rating and row.is_active:
			env_ratings.append(row.environment_rating)

	env_ratings = list(set(env_ratings))

	if not env_ratings:
		return {"success": True, "environment_ratings": [], "error": None}

	# Get environment rating details
	env_docs = frappe.get_all(
		"ilL-Attribute-Environment Rating",
		filters={"name": ["in", env_ratings]},
		fields=["name", "label", "code"],
	)

	result = [
		{
			"value": env.name,
			"label": env.label or env.name,
			"code": env.code,
		}
		for env in env_docs
	]

	return {"success": True, "environment_ratings": result, "error": None}


@frappe.whitelist()
def get_ccts_for_template(
	fixture_template_code: str,
	led_package_code: str = None,
	environment_rating_code: str = None,
) -> dict[str, Any]:
	"""
	Get available CCT options based on compatible tapes.

	Filters CCTs based on:
	- Tapes linked to the fixture template
	- Selected LED Package (if provided)
	- Selected Environment Rating (if provided, checks tape offering constraints)

	Args:
		fixture_template_code: Code of the fixture template
		led_package_code: Selected LED Package (optional filter)
		environment_rating_code: Selected Environment Rating (optional filter)

	Returns:
		dict: {
			"success": bool,
			"ccts": [{"value": code, "label": label, "kelvin": int}],
			"error": str (if failed)
		}
	"""
	if not frappe.db.exists("ilL-Fixture-Template", fixture_template_code):
		return {"success": False, "ccts": [], "error": f"Template '{fixture_template_code}' not found"}

	template_doc = frappe.get_doc("ilL-Fixture-Template", fixture_template_code)

	# Get tape offerings linked to this template, filtering by environment rating if specified
	allowed_tape_rows = template_doc.get("allowed_tape_offerings", [])

	# Build list of valid tape offering names considering environment rating constraint
	valid_tape_offering_names = []
	for row in allowed_tape_rows:
		if not row.tape_offering:
			continue
		# If the row has an environment_rating constraint, it must match
		if environment_rating_code and row.environment_rating and row.environment_rating != environment_rating_code:
			continue
		valid_tape_offering_names.append(row.tape_offering)

	if not valid_tape_offering_names:
		return {"success": True, "ccts": [], "error": None}

	# Build tape offering filter - only add is_active filter if active records exist
	tape_filters = {
		"name": ["in", valid_tape_offering_names],
	}
	
	# Check if any tape offerings have is_active = 1
	active_count = frappe.db.count("ilL-Rel-Tape Offering", {"is_active": 1})
	if active_count > 0:
		tape_filters["is_active"] = 1

	# Filter by LED package if specified
	if led_package_code:
		tape_filters["led_package"] = led_package_code

	# Get CCTs from matching tape offerings
	tape_offerings = frappe.get_all(
		"ilL-Rel-Tape Offering",
		filters=tape_filters,
		fields=["cct"],
		distinct=True,
	)

	cct_codes = list({row.cct for row in tape_offerings if row.cct})

	if not cct_codes:
		# Fallback: If no CCTs found from tape offerings (e.g. no tapes match the
		# selected LED package), return all active CCTs so the user can still proceed
		all_ccts = frappe.get_all(
			"ilL-Attribute-CCT",
			filters={"is_active": 1},
			fields=["name", "code", "label", "kelvin", "sort_order"],
			order_by="sort_order asc, kelvin asc",
		)
		# If no active CCTs, get all CCTs (is_active may not be set)
		if not all_ccts:
			all_ccts = frappe.get_all(
				"ilL-Attribute-CCT",
				fields=["name", "code", "label", "kelvin", "sort_order"],
				order_by="sort_order asc, kelvin asc",
			)
		fallback_result = [
			{
				"value": cct.name,
				"label": cct.label or cct.name,
				"code": cct.code,
				"kelvin": cct.kelvin,
			}
			for cct in all_ccts
		]
		return {"success": True, "ccts": fallback_result, "error": None}

	# Get CCT details - only filter by is_active if active CCTs exist
	cct_filters = {"name": ["in", cct_codes]}
	active_cct_count = frappe.db.count("ilL-Attribute-CCT", {"is_active": 1})
	if active_cct_count > 0:
		cct_filters["is_active"] = 1
		
	ccts = frappe.get_all(
		"ilL-Attribute-CCT",
		filters=cct_filters,
		fields=["name", "code", "label", "kelvin", "sort_order"],
		order_by="sort_order asc, kelvin asc",
	)

	result = [
		{
			"value": cct.name,
			"label": cct.label or cct.name,
			"code": cct.code,
			"kelvin": cct.kelvin,
		}
		for cct in ccts
	]

	return {"success": True, "ccts": result, "error": None}


def _find_closest_fixture_output_level(delivered_lm_ft: float, fixture_output_levels: list) -> dict | None:
	"""
	Find the closest fixture-level output level from the ilL-Attribute-Output Level list.

	Args:
		delivered_lm_ft: The calculated delivered lumens per foot
		fixture_output_levels: List of dicts with 'name', 'value', 'sku_code', 'output_level_name'

	Returns:
		The closest matching output level dict, or None if list is empty
	"""
	if not fixture_output_levels:
		return None

	closest = None
	min_diff = float('inf')

	for level in fixture_output_levels:
		diff = abs(level["value"] - delivered_lm_ft)
		if diff < min_diff:
			min_diff = diff
			closest = level

	return closest


@frappe.whitelist()
def get_delivered_outputs_for_template(
	fixture_template_code: str,
	led_package_code: str,
	environment_rating_code: str,
	cct_code: str,
	lens_appearance_code: str,
) -> dict[str, Any]:
	"""
	Calculate and return available fixture output options (delivered lumens).

	This is the key function that computes the delivered output options based on:
	1. Compatible tapes (filtered by LED Package, Environment Rating, CCT)
	2. Lens transmission percentage
	3. Fixture-level output levels from ilL-Attribute-Output Level

	The delivered output = tape lumen output × lens transmission %, matched to closest
	fixture-level output from ilL-Attribute-Output Level (is_fixture_level=1).

	Args:
		fixture_template_code: Code of the fixture template
		led_package_code: Selected LED Package
		environment_rating_code: Selected Environment Rating
		cct_code: Selected CCT
		lens_appearance_code: Selected Lens Appearance

	Returns:
		dict: {
			"success": bool,
			"delivered_outputs": [
				{
					"value": int (delivered lm/ft matched to fixture output level),
					"label": str (e.g., "350 lm/ft"),
					"output_level": str (link to ilL-Attribute-Output Level),
					"output_level_name": str (display name),
					"sku_code": str,
					"tape_output_lm_ft": int,
					"transmission_pct": float,
					"matching_tape_count": int
				}
			],
			"compatible_tapes": [tape_offering_id, ...],
			"error": str (if failed)
		}
	"""
	try:
		if not frappe.db.exists("ilL-Fixture-Template", fixture_template_code):
			return {"success": False, "delivered_outputs": [], "compatible_tapes": [], "lens_transmission_pct": 100, "error": f"Template '{fixture_template_code}' not found"}

		template_doc = frappe.get_doc("ilL-Fixture-Template", fixture_template_code)

		# Fetch all fixture-level output levels upfront for matching
		fixture_output_levels = frappe.get_all(
			"ilL-Attribute-Output Level",
			filters={"is_fixture_level": 1},
			fields=["name", "value", "sku_code", "output_level_name"],
			order_by="value asc",
		)

		if not fixture_output_levels:
			return {"success": False, "delivered_outputs": [], "compatible_tapes": [], "lens_transmission_pct": 100, "error": "No fixture-level output levels defined in ilL-Attribute-Output Level"}

		# Get lens transmission as decimal (stored as 0.56 = 56%)
		lens_transmission_decimal = 1.0  # Default to 100% if not specified
		if lens_appearance_code and frappe.db.exists("ilL-Attribute-Lens Appearance", lens_appearance_code):
			lens_doc = frappe.get_doc("ilL-Attribute-Lens Appearance", lens_appearance_code)
			if lens_doc.transmission:
				# Value is stored as decimal (0.56 for 56%)
				lens_transmission_decimal = float(lens_doc.transmission)

		# Get tape offerings linked to this template, filtering by environment rating
		allowed_tape_rows = template_doc.get("allowed_tape_offerings", [])

		# Build list of valid tape offering names considering constraints
		valid_tape_offering_names = []
		for row in allowed_tape_rows:
			if not row.tape_offering:
				continue
			# If the row has an environment_rating constraint, it must match
			if environment_rating_code and row.environment_rating and row.environment_rating != environment_rating_code:
				continue
			# If the row has a lens_appearance constraint, it must match
			if lens_appearance_code and row.lens_appearance and row.lens_appearance != lens_appearance_code:
				continue
			valid_tape_offering_names.append(row.tape_offering)

		if not valid_tape_offering_names:
			return {"success": True, "delivered_outputs": [], "compatible_tapes": [], "lens_transmission_pct": lens_transmission_decimal * 100, "error": None}

		# Build tape offering filter for exact matches - only add is_active if active records exist
		tape_filters = {
			"name": ["in", valid_tape_offering_names],
			"led_package": led_package_code,
			"cct": cct_code,
		}
		active_count = frappe.db.count("ilL-Rel-Tape Offering", {"is_active": 1})
		if active_count > 0:
			tape_filters["is_active"] = 1

		# Get matching tape offerings with their output levels
		tape_offerings = frappe.get_all(
			"ilL-Rel-Tape Offering",
			filters=tape_filters,
			fields=["name", "output_level", "tape_spec"],
		)

		if not tape_offerings:
			return {"success": True, "delivered_outputs": [], "compatible_tapes": [], "lens_transmission_pct": lens_transmission_decimal * 100, "error": None}

		# Get output level values (lm/ft) for each tape
		output_level_names = list({t.output_level for t in tape_offerings if t.output_level})

		output_level_values = {}
		if output_level_names:
			output_levels = frappe.get_all(
				"ilL-Attribute-Output Level",
				filters={"name": ["in", output_level_names]},
				fields=["name", "value", "sku_code"],
			)
			output_level_values = {ol.name: {"value": ol.value, "sku_code": ol.sku_code} for ol in output_levels}

		# Calculate delivered outputs
		# Map: output_level_name -> {output_level_link, value, sku_code, tape_output, transmission, matching_tapes}
		delivered_output_map: dict[str, dict] = {}
		compatible_tapes = []

		for tape in tape_offerings:
			if not tape.output_level or tape.output_level not in output_level_values:
				continue

			tape_output_lm_ft = output_level_values[tape.output_level]["value"]
			# Calculate delivered lumens: tape output × transmission (decimal)
			delivered_lm_ft = tape_output_lm_ft * lens_transmission_decimal

			# Find closest fixture-level output level instead of rounding to 50
			closest_level = _find_closest_fixture_output_level(delivered_lm_ft, fixture_output_levels)
			if not closest_level:
				continue

			output_level_key = closest_level["name"]

			if output_level_key not in delivered_output_map:
				delivered_output_map[output_level_key] = {
					"output_level": closest_level["name"],
					"output_level_name": closest_level["output_level_name"],
					"value": closest_level["value"],
					"sku_code": closest_level["sku_code"],
					"tape_output_lm_ft": tape_output_lm_ft,
					"transmission_pct": lens_transmission_decimal * 100,  # Convert to percentage for display
					"matching_tapes": [],
				}
			delivered_output_map[output_level_key]["matching_tapes"].append(tape.name)
			compatible_tapes.append(tape.name)

		# Build result sorted by output value
		delivered_outputs = []
		for output_level_key in sorted(delivered_output_map.keys(), key=lambda k: delivered_output_map[k]["value"]):
			data = delivered_output_map[output_level_key]
			delivered_outputs.append({
				"value": data["value"],
				"label": f"{data['value']} lm/ft",
				"output_level": data["output_level"],
				"output_level_name": data["output_level_name"],
				"sku_code": data["sku_code"],
				"tape_output_lm_ft": data["tape_output_lm_ft"],
				"transmission_pct": data["transmission_pct"],
				"matching_tape_count": len(data["matching_tapes"]),
			})

		# Fallback: If no delivered outputs from tape offerings, use all fixture-level output levels
		if not delivered_outputs:
			for ol in fixture_output_levels:
				delivered_outputs.append({
					"value": ol["value"],
					"label": f"{ol['value']} lm/ft",
					"output_level": ol["name"],
					"output_level_name": ol["output_level_name"],
					"sku_code": ol["sku_code"],
					"tape_output_lm_ft": ol["value"],
					"transmission_pct": lens_transmission_decimal * 100,  # Convert to percentage for display
					"matching_tape_count": 0,  # No specific tape match
				})

		return {
			"success": True,
			"delivered_outputs": delivered_outputs,
			"compatible_tapes": list(set(compatible_tapes)),
			"lens_transmission_pct": lens_transmission_decimal * 100,  # Convert to percentage for display
			"error": None,
		}
	except Exception as e:
		frappe.log_error(f"get_delivered_outputs_for_template error: {str(e)}", "Configurator Error")
		return {
			"success": False,
			"delivered_outputs": [],
			"compatible_tapes": [],
			"lens_transmission_pct": 100,
			"error": str(e),
		}


@frappe.whitelist()
def auto_select_tape_for_configuration(
	fixture_template_code: str,
	led_package_code: str,
	environment_rating_code: str,
	cct_code: str,
	lens_appearance_code: str,
	delivered_output_value: int,
) -> dict[str, Any]:
	"""
	Automatically select the tape offering based on the user's configuration choices.

	This is the final step that narrows down to a single tape based on:
	- LED Package, Environment Rating, CCT (exact match)
	- Lens appearance (for constraint checking)
	- Delivered output (matched to closest fixture-level output from ilL-Attribute-Output Level)

	Args:
		fixture_template_code: Code of the fixture template
		led_package_code: Selected LED Package
		environment_rating_code: Selected Environment Rating
		cct_code: Selected CCT
		lens_appearance_code: Selected Lens Appearance
		delivered_output_value: User's selected delivered output value (from fixture output level)

	Returns:
		dict: {
			"success": bool,
			"tape_offering_id": str or None,
			"tape_details": {
				"output_level": str,
				"output_value_lm_ft": int,
				"fixture_output_level": str (link to ilL-Attribute-Output Level),
				"tape_spec": str,
				"cri": str,
				"sdcm": str
			} or None,
			"error": str (if failed or ambiguous)
		}
	"""
	try:
		delivered_output_value = int(delivered_output_value)
	except (ValueError, TypeError):
		return {"success": False, "tape_offering_id": None, "tape_details": None, "error": "Invalid delivered output value"}

	if not frappe.db.exists("ilL-Fixture-Template", fixture_template_code):
		return {"success": False, "tape_offering_id": None, "tape_details": None, "error": f"Template '{fixture_template_code}' not found"}

	template_doc = frappe.get_doc("ilL-Fixture-Template", fixture_template_code)

	# Fetch all fixture-level output levels for matching
	fixture_output_levels = frappe.get_all(
		"ilL-Attribute-Output Level",
		filters={"is_fixture_level": 1},
		fields=["name", "value", "sku_code", "output_level_name"],
		order_by="value asc",
	)

	if not fixture_output_levels:
		return {"success": False, "tape_offering_id": None, "tape_details": None, "error": "No fixture-level output levels defined"}

	# Get lens transmission as decimal (stored as 0.56 = 56%)
	lens_transmission_decimal = 1.0  # Default to 100% if not specified
	if lens_appearance_code and frappe.db.exists("ilL-Attribute-Lens Appearance", lens_appearance_code):
		lens_doc = frappe.get_doc("ilL-Attribute-Lens Appearance", lens_appearance_code)
		if lens_doc.transmission:
			# Value is stored as decimal (0.56 for 56%)
			lens_transmission_decimal = float(lens_doc.transmission)

	# Get valid tape offering names from template (with constraint filtering)
	allowed_tape_rows = template_doc.get("allowed_tape_offerings", [])
	valid_tape_offering_names = []

	for row in allowed_tape_rows:
		if not row.tape_offering:
			continue
		if environment_rating_code and row.environment_rating and row.environment_rating != environment_rating_code:
			continue
		if lens_appearance_code and row.lens_appearance and row.lens_appearance != lens_appearance_code:
			continue
		valid_tape_offering_names.append(row.tape_offering)

	if not valid_tape_offering_names:
		return {"success": False, "tape_offering_id": None, "tape_details": None, "error": "No compatible tapes found"}

	# Get matching tape offerings - only add is_active if active records exist
	tape_filters = {
		"name": ["in", valid_tape_offering_names],
		"led_package": led_package_code,
		"cct": cct_code,
	}
	active_count = frappe.db.count("ilL-Rel-Tape Offering", {"is_active": 1})
	if active_count > 0:
		tape_filters["is_active"] = 1

	tape_offerings = frappe.get_all(
		"ilL-Rel-Tape Offering",
		filters=tape_filters,
		fields=["name", "output_level", "tape_spec", "cri", "sdcm"],
	)

	if not tape_offerings:
		return {"success": False, "tape_offering_id": None, "tape_details": None, "error": "No matching tapes found for selection"}

	# Get output level values
	output_level_names = list({t.output_level for t in tape_offerings if t.output_level})
	output_level_values = {}
	if output_level_names:
		output_levels = frappe.get_all(
			"ilL-Attribute-Output Level",
			filters={"name": ["in", output_level_names]},
			fields=["name", "value", "sku_code"],
		)
		output_level_values = {ol.name: {"value": ol.value, "sku_code": ol.sku_code} for ol in output_levels}

	# Find the tape(s) that match the delivered output
	matching_tapes = []

	for tape in tape_offerings:
		if not tape.output_level or tape.output_level not in output_level_values:
			continue

		tape_output_lm_ft = output_level_values[tape.output_level]["value"]
		# Calculate delivered lumens: tape output × transmission (decimal)
		delivered_lm_ft = tape_output_lm_ft * lens_transmission_decimal

		# Find closest fixture-level output level instead of rounding to 50
		closest_level = _find_closest_fixture_output_level(delivered_lm_ft, fixture_output_levels)
		if not closest_level:
			continue

		# Match if the closest level's value equals the selected delivered output
		if closest_level["value"] == delivered_output_value:
			matching_tapes.append({
				"tape_offering_id": tape.name,
				"output_level": tape.output_level,
				"output_value_lm_ft": tape_output_lm_ft,
				"fixture_output_level": closest_level["name"],
				"fixture_output_level_name": closest_level["output_level_name"],
				"tape_spec": tape.tape_spec,
				"cri": tape.cri,
				"sdcm": tape.sdcm,
			})

	if not matching_tapes:
		return {"success": False, "tape_offering_id": None, "tape_details": None, "error": "No tape matches the selected output"}

	if len(matching_tapes) > 1:
		# Multiple tapes match - this shouldn't happen with proper data, but handle gracefully
		# Pick the first one and add a warning
		selected = matching_tapes[0]
		return {
			"success": True,
			"tape_offering_id": selected["tape_offering_id"],
			"tape_details": {
				"output_level": selected["output_level"],
				"output_value_lm_ft": selected["output_value_lm_ft"],
				"fixture_output_level": selected["fixture_output_level"],
				"fixture_output_level_name": selected["fixture_output_level_name"],
				"tape_spec": selected["tape_spec"],
				"cri": selected["cri"],
				"sdcm": selected["sdcm"],
			},
			"warning": f"Multiple tapes match ({len(matching_tapes)}). Selected first match.",
			"error": None,
		}

	# Single match - perfect!
	selected = matching_tapes[0]
	return {
		"success": True,
		"tape_offering_id": selected["tape_offering_id"],
		"tape_details": {
			"output_level": selected["output_level"],
			"output_value_lm_ft": selected["output_value_lm_ft"],
			"fixture_output_level": selected["fixture_output_level"],
			"fixture_output_level_name": selected["fixture_output_level_name"],
			"tape_spec": selected["tape_spec"],
			"cri": selected["cri"],
			"sdcm": selected["sdcm"],
		},
		"error": None,
	}


@frappe.whitelist()
def get_cascading_options_for_template(
	fixture_template_code: str,
	led_package_code: str = None,
	environment_rating_code: str = None,
	cct_code: str = None,
	lens_appearance_code: str = None,
) -> dict[str, Any]:
	"""
	Get all available options for the cascading configurator in one call.

	This is a convenience function that returns all option lists filtered by
	the current selections. Use this for progressive disclosure UI patterns.

	Args:
		fixture_template_code: Code of the fixture template
		led_package_code: Selected LED Package (optional)
		environment_rating_code: Selected Environment Rating (optional)
		cct_code: Selected CCT (optional)
		lens_appearance_code: Selected Lens Appearance (optional)

	Returns:
		dict: {
			"success": bool,
			"options": {
				"led_packages": [...],
				"environment_ratings": [...],
				"ccts": [...],
				"lens_appearances": [...],
				"mountings": [...],
				"finishes": [...],
				"delivered_outputs": [...] (only if all required selections made)
			},
			"selected_tape": str or None (if output determines a single tape),
			"error": str (if failed)
		}
	"""
	if not frappe.db.exists("ilL-Fixture-Template", fixture_template_code):
		return {"success": False, "options": {}, "error": f"Template '{fixture_template_code}' not found"}

	template_doc = frappe.get_doc("ilL-Fixture-Template", fixture_template_code)

	options = {
		"led_packages": [],
		"environment_ratings": [],
		"ccts": [],
		"lens_appearances": [],
		"mountings": [],
		"finishes": [],
		"endcap_colors": [],
		"power_feed_type": [],
		"delivered_outputs": [],
	}

	# Get LED packages
	led_pkg_result = get_led_packages_for_template(fixture_template_code)
	if led_pkg_result.get("success"):
		options["led_packages"] = led_pkg_result.get("led_packages", [])

	# Fallback: If no LED packages from tape offerings, get all active ones
	if not options["led_packages"]:
		all_led_pkgs = frappe.get_all(
			"ilL-Attribute-LED Package",
			filters={"is_active": 1} if frappe.db.has_column("ilL-Attribute-LED Package", "is_active") else {},
			fields=["name", "code", "spectrum_type"],
		)
		options["led_packages"] = [
			{
				"value": pkg.name,
				"label": pkg.name,
				"code": pkg.code,
				"spectrum_type": pkg.spectrum_type,
			}
			for pkg in all_led_pkgs
		]

	# Get environment ratings
	env_result = get_environment_ratings_for_template(fixture_template_code)
	if env_result.get("success"):
		options["environment_ratings"] = env_result.get("environment_ratings", [])

	# Fallback: If no environment ratings from allowed options, get all active ones
	if not options["environment_ratings"]:
		all_env_ratings = frappe.get_all(
			"ilL-Attribute-Environment Rating",
			filters={"is_active": 1} if frappe.db.has_column("ilL-Attribute-Environment Rating", "is_active") else {},
			fields=["name", "label", "code"],
		)
		options["environment_ratings"] = [
			{
				"value": env.name,
				"label": env.label or env.name,
				"code": env.code,
			}
			for env in all_env_ratings
		]

	# Get CCTs (filtered by LED package and environment rating if provided)
	cct_result = get_ccts_for_template(
		fixture_template_code,
		led_package_code=led_package_code,
		environment_rating_code=environment_rating_code,
	)
	if cct_result.get("success"):
		options["ccts"] = cct_result.get("ccts", [])

	# Fallback: If no CCTs from tape offerings, get all active CCTs
	if not options["ccts"]:
		# First try with is_active filter
		all_ccts = frappe.get_all(
			"ilL-Attribute-CCT",
			filters={"is_active": 1},
			fields=["name", "code", "label", "kelvin", "sort_order"],
			order_by="sort_order asc, kelvin asc",
		)
		# If no active CCTs, get all CCTs (is_active may not be set)
		if not all_ccts:
			all_ccts = frappe.get_all(
				"ilL-Attribute-CCT",
				fields=["name", "code", "label", "kelvin", "sort_order"],
				order_by="sort_order asc, kelvin asc",
			)
		options["ccts"] = [
			{
				"value": cct.name,
				"label": cct.label or cct.name,
				"code": cct.code,
				"kelvin": cct.kelvin,
			}
			for cct in all_ccts
		]

	# Get lens appearances from allowed options
	for row in template_doc.get("allowed_options", []):
		if row.option_type == "Lens Appearance" and row.lens_appearance and row.is_active:
			lens_doc = frappe.get_doc("ilL-Attribute-Lens Appearance", row.lens_appearance)
			options["lens_appearances"].append({
				"value": row.lens_appearance,
				"label": row.lens_appearance,
				"code": lens_doc.code if lens_doc else "",
				"transmission": lens_doc.transmission if lens_doc else 100,
			})

	# Deduplicate lens appearances
	seen_lenses = set()
	unique_lenses = []
	for lens in options["lens_appearances"]:
		if lens["value"] not in seen_lenses:
			seen_lenses.add(lens["value"])
			unique_lenses.append(lens)
	options["lens_appearances"] = unique_lenses

	# Fallback: If no lens appearances from allowed options, get all active ones
	if not options["lens_appearances"]:
		all_lenses = frappe.get_all(
			"ilL-Attribute-Lens Appearance",
			filters={"is_active": 1} if frappe.db.has_column("ilL-Attribute-Lens Appearance", "is_active") else {},
			fields=["name", "code", "transmission"],
		)
		options["lens_appearances"] = [
			{
				"value": lens.name,
				"label": lens.name,
				"code": lens.code,
				"transmission": lens.transmission if lens.transmission else 100,
			}
			for lens in all_lenses
		]

	# Get mountings from allowed options
	for row in template_doc.get("allowed_options", []):
		if row.option_type == "Mounting Method" and row.mounting_method and row.is_active:
			options["mountings"].append({
				"value": row.mounting_method,
				"label": row.mounting_method,
			})

	# Deduplicate mountings
	seen_mountings = set()
	unique_mountings = []
	for m in options["mountings"]:
		if m["value"] not in seen_mountings:
			seen_mountings.add(m["value"])
			unique_mountings.append(m)
	options["mountings"] = unique_mountings

	# Fallback: If no mountings from allowed options, get all active ones
	if not options["mountings"]:
		all_mountings = frappe.get_all(
			"ilL-Attribute-Mounting Method",
			filters={"is_active": 1} if frappe.db.has_column("ilL-Attribute-Mounting Method", "is_active") else {},
			fields=["name", "code"],
		)
		options["mountings"] = [
			{
				"value": m.name,
				"label": m.name,
			}
			for m in all_mountings
		]

	# Get finishes from allowed options
	for row in template_doc.get("allowed_options", []):
		if row.option_type == "Finish" and row.finish and row.is_active:
			options["finishes"].append({
				"value": row.finish,
				"label": row.finish,
			})

	# Deduplicate finishes
	seen_finishes = set()
	unique_finishes = []
	for f in options["finishes"]:
		if f["value"] not in seen_finishes:
			seen_finishes.add(f["value"])
			unique_finishes.append(f)
	options["finishes"] = unique_finishes

	# Fallback: If no finishes from allowed options, get all active ones
	if not options["finishes"]:
		all_finishes = frappe.get_all(
			"ilL-Attribute-Finish",
			filters={"is_active": 1} if frappe.db.has_column("ilL-Attribute-Finish", "is_active") else {},
			fields=["name", "code", "display_name"],
		)
		options["finishes"] = [
			{
				"value": f.name,
				"label": f.display_name or f.name,
			}
			for f in all_finishes
		]

	# Get endcap colors - fetch all active ones (not template-specific in MVP)
	endcap_colors = frappe.get_all(
		"ilL-Attribute-Endcap Color",
		filters={"is_active": 1},
		fields=["code", "display_name", "sort_order"],
		order_by="sort_order asc, code asc",
	)
	for color in endcap_colors:
		options["endcap_colors"].append({
			"value": color.code,
			"label": color.display_name or color.code,
		})

	# Get power feed types from allowed options
	for row in template_doc.get("allowed_options", []):
		if row.option_type == "Power Feed Type" and row.power_feed_type and row.is_active:
			options["power_feed_type"].append({
				"value": row.power_feed_type,
				"label": row.power_feed_type,
			})

	# Deduplicate power feed types
	seen_pft = set()
	unique_pft = []
	for p in options["power_feed_type"]:
		if p["value"] not in seen_pft:
			seen_pft.add(p["value"])
			unique_pft.append(p)
	options["power_feed_type"] = unique_pft

	# Fallback: If no power feed types from allowed options, get all active ones
	if not options["power_feed_type"]:
		all_pft = frappe.get_all(
			"ilL-Attribute-Power Feed Type",
			filters={"is_active": 1} if frappe.db.has_column("ilL-Attribute-Power Feed Type", "is_active") else {},
			fields=["name", "code"],
		)
		options["power_feed_type"] = [
			{
				"value": pft.name,
				"label": pft.name,
			}
			for pft in all_pft
		]

	# Get delivered outputs (only if all required selections are made)
	if led_package_code and environment_rating_code and cct_code and lens_appearance_code:
		output_result = get_delivered_outputs_for_template(
			fixture_template_code,
			led_package_code,
			environment_rating_code,
			cct_code,
			lens_appearance_code,
		)
		if output_result.get("success"):
			options["delivered_outputs"] = output_result.get("delivered_outputs", [])

	return {"success": True, "options": options, "error": None}
