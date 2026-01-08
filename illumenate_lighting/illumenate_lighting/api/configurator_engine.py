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
        "endcap_style_code": str,                # Required: Endcap style option code
        "endcap_color_code": str,                # Required: Endcap color option code
        "power_feed_type_code": str,             # Required: Power feed type option code
        "environment_rating_code": str,          # Required: Environment rating option code
        "tape_offering_id": str,                 # Required: Tape offering ID or code
        "requested_overall_length_mm": int,      # Required: Requested overall length in millimeters
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
            "endcap_allowance_mm_per_side": float,
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


@frappe.whitelist()
def validate_and_quote(
	fixture_template_code: str,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_style_code: str,
	endcap_color_code: str,
	power_feed_type_code: str,
	environment_rating_code: str,
	tape_offering_id: str,
	requested_overall_length_mm: int,
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
		endcap_style_code: Endcap style option code
		endcap_color_code: Endcap color option code
		power_feed_type_code: Power feed type option code
		environment_rating_code: Environment rating option code
		tape_offering_id: Tape offering ID or code
		requested_overall_length_mm: Requested overall length in millimeters
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
			"endcap_allowance_mm_per_side": 0.0,
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
			"endcap_item": None,
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
		endcap_style_code,
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
		endcap_style_code,
		power_feed_type_code,
		lens_appearance_code,
		finish_code,
		template_doc=validation_result.get("template_doc"),
		tape_offering_doc=validation_result.get("tape_offering_doc"),
	)

	response["computed"].update(computed_result)

	# Step 3: Resolve items
	resolved_result, mapping_messages, mappings_valid = _resolve_items(
		fixture_template_code,
		finish_code,
		lens_appearance_code,
		mounting_method_code,
		endcap_style_code,
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

	# Step 4: Calculate pricing
	pricing_result = _calculate_pricing(
		fixture_template_code,
		resolved_result,
		computed_result,
		finish_code,
		lens_appearance_code,
		mounting_method_code,
		endcap_style_code,
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
		endcap_style_code,
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

	return response


def _validate_configuration(
	fixture_template_code: str,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_style_code: str,
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
		"endcap_style_code": endcap_style_code,
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
		"Endcap Style": ("endcap_style", endcap_style_code, "endcap_style_code", "ilL-Attribute-Endcap Style"),
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
	endcap_style_code: str,
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

	# E = endcap_style.mm_per_side (from Endcap Style attribute)
	endcap_allowance_mm_per_side = 0.0
	if endcap_style_code and frappe.db.exists("ilL-Attribute-Endcap Style", endcap_style_code):
		endcap_doc = frappe.get_doc("ilL-Attribute-Endcap Style", endcap_style_code)
		endcap_allowance_mm_per_side = float(endcap_doc.allowance_mm_per_side or 0)

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

	# L_internal = L_req - 2E - A_leader
	L_req = float(requested_overall_length_mm)
	E = endcap_allowance_mm_per_side
	A_leader = leader_allowance_mm_per_fixture
	L_internal = L_req - (2 * E) - A_leader

	# L_tape_cut = floor(L_internal / cut_increment) * cut_increment
	# Handle edge cases: if cut_increment invalid or L_internal <= 0, L_tape_cut = 0
	if cut_increment_mm > 0 and L_internal > 0:
		L_tape_cut = math.floor(L_internal / cut_increment_mm) * cut_increment_mm
	else:
		L_tape_cut = 0 if L_internal <= 0 or cut_increment_mm <= 0 else max(0, L_internal)

	# L_mfg = L_tape_cut + 2E + A_leader
	L_mfg = L_tape_cut + (2 * E) + A_leader

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
		"endcap_allowance_mm_per_side": endcap_allowance_mm_per_side,
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


def _resolve_items(
	fixture_template_code: str,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_style_code: str,
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
		"endcap_item": None,
		"mounting_item": None,
		"leader_item": None,
		"driver_plan": {
			"status": "suggested",
			"drivers": [{"item_code": "DRIVER-PLACEHOLDER", "qty": 1, "watts_capacity": 100.0}],
		},
	}

	template_doc = template_doc or frappe.get_doc("ilL-Fixture-Template", fixture_template_code)
	profile_family = template_doc.default_profile_family or fixture_template_code

	profile_rows = frappe.get_all(
		"ilL-Spec-Profile",
		filters={"family": profile_family, "variant_code": finish_code, "is_active": 1},
		fields=["name", "item", "lens_interface"],
		limit=1,
	)

	if not profile_rows:
		messages.append(
			{
				"severity": "error",
				"text": f"Missing map: ilL-Spec-Profile for family '{profile_family}' and finish '{finish_code}'",
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
	for lens_row in lens_candidates:
		lens_doc = frappe.get_doc("ilL-Spec-Lens", lens_row.name)
		if environment_rating_code:
			env_supported = {row.environment_rating for row in lens_doc.get("supported_environment_ratings", [])}
			if env_supported and environment_rating_code not in env_supported:
				continue
		lens_item = lens_row.item
		break

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

	endcap_candidates = frappe.get_all(
		"ilL-Rel-Endcap-Map",
		filters={
			"fixture_template": fixture_template_code,
			"endcap_style": endcap_style_code,
			"endcap_color": endcap_color_code,
			"is_active": 1,
		},
		fields=["name", "endcap_item", "power_feed_type", "environment_rating"],
	)

	endcap_item = None
	for endcap_row in endcap_candidates:
		if endcap_row.get("power_feed_type") and endcap_row.power_feed_type != power_feed_type_code:
			continue
		if endcap_row.get("environment_rating") and endcap_row.environment_rating != environment_rating_code:
			continue
		endcap_item = endcap_row.endcap_item
		break

	if not endcap_item:
		messages.append(
			{
				"severity": "error",
				"text": (
					f"Missing map: ilL-Rel-Endcap-Map for template '{fixture_template_code}', "
					f"style '{endcap_style_code}', color '{endcap_color_code}'"
				),
				"field": "endcap_style_code",
			}
		)
		return resolved, messages, False

	resolved["endcap_item"] = endcap_item

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


def _calculate_pricing(
	fixture_template_code: str,
	resolved_items: dict,
	computed: dict,
	finish_code: str,
	lens_appearance_code: str,
	mounting_method_code: str,
	endcap_style_code: str,
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
		endcap_style_code: Selected endcap style code
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
		"Endcap Style": ("endcap_style", endcap_style_code),
		"Power Feed Type": ("power_feed_type", power_feed_type_code),
		"Environment Rating": ("environment_rating", environment_rating_code),
	}

	total_option_adders = 0.0
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
	endcap_style_code: str,
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

	Returns:
		str: Name of the created/updated ilL-Configured-Fixture document
	"""
	# Create config data for hashing (all input parameters)
	config_data = {
		"fixture_template_code": fixture_template_code,
		"finish_code": finish_code,
		"lens_appearance_code": lens_appearance_code,
		"mounting_method_code": mounting_method_code,
		"endcap_style_code": endcap_style_code,
		"endcap_color_code": endcap_color_code,
		"power_feed_type_code": power_feed_type_code,
		"environment_rating_code": environment_rating_code,
		"tape_offering_id": tape_offering_id,
		"requested_overall_length_mm": requested_overall_length_mm,
	}

	# Generate hash: first 32 hex characters (128 bits of entropy) from SHA-256 for collision resistance
	config_hash = hashlib.sha256(json.dumps(config_data, sort_keys=True).encode()).hexdigest()[:32]

	# Check if this configuration already exists
	# Note: The document name IS the config_hash (autoname: "field:config_hash" in DocType)
	existing = frappe.db.exists("ilL-Configured-Fixture", config_hash)

	if existing:
		doc = frappe.get_doc("ilL-Configured-Fixture", config_hash)
	else:
		doc = frappe.new_doc("ilL-Configured-Fixture")
		doc.config_hash = config_hash  # This will become the document name

	# Set identity fields
	doc.engine_version = "1.0.0"
	doc.fixture_template = fixture_template_code

	# Set selected options
	doc.finish = finish_code
	doc.lens_appearance = lens_appearance_code
	doc.mounting_method = mounting_method_code
	doc.endcap_style = endcap_style_code
	doc.endcap_color = endcap_color_code
	doc.power_feed_type = power_feed_type_code
	doc.environment_rating = environment_rating_code
	doc.tape_offering = tape_offering_id

	# Set length inputs/outputs
	doc.requested_overall_length_mm = requested_overall_length_mm
	doc.endcap_allowance_mm_per_side = computed["endcap_allowance_mm_per_side"]
	doc.leader_allowance_mm = computed["leader_allowance_mm_per_fixture"]
	doc.internal_length_mm = computed["internal_length_mm"]
	doc.tape_cut_length_mm = computed["tape_cut_length_mm"]
	doc.manufacturable_overall_length_mm = computed["manufacturable_overall_length_mm"]

	# Set computed outputs
	doc.runs_count = computed["runs_count"]
	doc.total_watts = computed["total_watts"]
	doc.assembly_mode = computed["assembly_mode"]

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
				"run_len_mm": run["run_len_mm"],
				"run_watts": run["run_watts"],
				"leader_item": run.get("leader_item") or resolved_items.get("leader_item"),
				"leader_len_mm": run["leader_len_mm"],
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
		doc.save()
	else:
		doc.insert()

	return doc.name
