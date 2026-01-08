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
            "endcap_allowance_mm_per_side": float,
            "leader_allowance_mm_per_fixture": float,
            "internal_length_mm": int,
            "tape_cut_length_mm": int,
            "manufacturable_overall_length_mm": int,
            "difference_mm": int,                 # requested - manufacturable
            "segments": [                         # Cut plan
                {
                    "segment_index": int,
                    "profile_cut_len_mm": int,
                    "lens_cut_len_mm": int,
                    "notes": str
                }
            ],
            "runs": [                             # Run plan
                {
                    "run_index": int,
                    "run_len_mm": int,
                    "run_watts": float,
                    "leader_item": str,           # Item code
                    "leader_len_mm": int
                }
            ],
            "runs_count": int,
            "total_watts": float,
            "assembly_mode": str                  # "ASSEMBLED" or "SHIP_PIECES"
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
			"endcap_allowance_mm_per_side": 0.0,
			"leader_allowance_mm_per_fixture": 0.0,
			"internal_length_mm": 0,
			"tape_cut_length_mm": 0,
			"manufacturable_overall_length_mm": 0,
			"difference_mm": 0,
			"segments": [],
			"runs": [],
			"runs_count": 0,
			"total_watts": 0.0,
			"assembly_mode": "ASSEMBLED",
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
		qty,
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
) -> dict[str, Any]:
	"""
	Compute manufacturable dimensions, segments, and runs.

	Returns:
		dict: Computed values including dimensions, segments, runs, watts, etc.
	"""
	# Placeholder computations - these should be replaced with actual business logic
	# based on the fixture template, tape specs, and other factors

	# Example: endcap allowance (would come from endcap spec)
	endcap_allowance_mm_per_side = 15.0  # Placeholder

	# Example: leader allowance (would come from power feed type)
	leader_allowance_mm_per_fixture = 150.0  # Placeholder

	# Calculate internal length
	internal_length_mm = int(requested_overall_length_mm - (2 * endcap_allowance_mm_per_side))

	# Calculate tape cut length (would factor in leader allowance)
	tape_cut_length_mm = int(internal_length_mm - leader_allowance_mm_per_fixture)

	# For v1, assume single segment and single run
	segments = [
		{
			"segment_index": 1,
			"profile_cut_len_mm": internal_length_mm,
			"lens_cut_len_mm": internal_length_mm,
			"notes": "Single segment configuration",
		}
	]

	runs = [
		{
			"run_index": 1,
			"run_len_mm": tape_cut_length_mm,
			"run_watts": tape_cut_length_mm * 0.01,  # Placeholder: 10W per meter
			"leader_item": None,  # Will be resolved in _resolve_items
			"leader_len_mm": int(leader_allowance_mm_per_fixture),
		}
	]

	runs_count = len(runs)
	total_watts = sum(run["run_watts"] for run in runs)

	# Manufacturable length is what we can actually make
	manufacturable_overall_length_mm = requested_overall_length_mm

	# Difference between requested and manufacturable
	difference_mm = requested_overall_length_mm - manufacturable_overall_length_mm

	return {
		"endcap_allowance_mm_per_side": endcap_allowance_mm_per_side,
		"leader_allowance_mm_per_fixture": leader_allowance_mm_per_fixture,
		"internal_length_mm": internal_length_mm,
		"tape_cut_length_mm": tape_cut_length_mm,
		"manufacturable_overall_length_mm": manufacturable_overall_length_mm,
		"difference_mm": difference_mm,
		"segments": segments,
		"runs": runs,
		"runs_count": runs_count,
		"total_watts": total_watts,
		"assembly_mode": "ASSEMBLED",
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
	qty: int,
) -> dict[str, Any]:
	"""
	Calculate MSRP, tier pricing, and adders.

	Returns:
		dict: Pricing information
	"""
	# Placeholder pricing logic - would query price lists and calculate based on:
	# - Base fixture price
	# - Length-based pricing
	# - Option adders (finish, lens, mounting, etc.)
	# - Quantity breaks

	base_price = 100.0  # Placeholder
	length_adder = computed["manufacturable_overall_length_mm"] * 0.05  # $0.05 per mm
	finish_adder = 20.0  # Placeholder
	lens_adder = 15.0  # Placeholder
	mounting_adder = 10.0  # Placeholder

	msrp_unit = base_price + length_adder + finish_adder + lens_adder + mounting_adder
	tier_unit = msrp_unit * 0.7  # 30% discount for tier pricing

	adder_breakdown = [
		{"component": "base", "description": "Base fixture price", "amount": base_price},
		{
			"component": "length",
			"description": f"Length adder ({computed['manufacturable_overall_length_mm']}mm)",
			"amount": length_adder,
		},
		{"component": "finish", "description": f"Finish ({finish_code})", "amount": finish_adder},
		{
			"component": "lens",
			"description": f"Lens ({lens_appearance_code})",
			"amount": lens_adder,
		},
		{
			"component": "mounting",
			"description": f"Mounting ({mounting_method_code})",
			"amount": mounting_adder,
		},
	]

	return {"msrp_unit": msrp_unit, "tier_unit": tier_unit, "adder_breakdown": adder_breakdown}


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

	# Set pricing snapshot
	doc.pricing_snapshot = []
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
