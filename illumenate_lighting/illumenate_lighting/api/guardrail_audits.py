# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Guardrail Coverage Audits API

This module provides programmatic coverage checks to help administrators
identify missing mappings for active fixture templates before customers
encounter configuration errors.

Epic 2 Task 2.1: Guardrail completeness audits
"""

from typing import Any

import frappe
from frappe import _


@frappe.whitelist()
def run_coverage_audit(fixture_template: str = None) -> dict[str, Any]:
	"""
	Run coverage audit for one or all active fixture templates.

	Checks for:
	- Endcap map coverage for allowed styles/colors/feed combos
	- Mounting map coverage for allowed mounting methods
	- Leader cable map coverage for allowed feed/environment combos
	- Tape offering whitelist non-empty

	Args:
		fixture_template: Specific template to audit (optional, defaults to all active)

	Returns:
		dict: Audit results with missing mappings for each template
	"""
	results = {
		"success": True,
		"total_templates": 0,
		"templates_with_issues": 0,
		"templates": [],
	}

	# Get templates to audit
	filters = {"is_active": 1}
	if fixture_template:
		filters["template_code"] = fixture_template

	templates = frappe.get_all(
		"ilL-Fixture-Template",
		filters=filters,
		fields=["name", "template_code", "template_name"],
	)

	results["total_templates"] = len(templates)

	for template in templates:
		template_result = _audit_template(template.name)
		results["templates"].append(template_result)

		if template_result["has_issues"]:
			results["templates_with_issues"] += 1

	return results


def _audit_template(template_name: str) -> dict[str, Any]:
	"""
	Audit a single fixture template for mapping completeness.

	Args:
		template_name: Name of the fixture template

	Returns:
		dict: Audit results for this template
	"""
	template = frappe.get_doc("ilL-Fixture-Template", template_name)

	result = {
		"template_code": template.template_code,
		"template_name": template.template_name,
		"has_issues": False,
		"missing_endcap_maps": [],
		"missing_mounting_maps": [],
		"missing_leader_maps": [],
		"missing_tape_offerings": False,
		"ambiguous_mappings": [],
	}

	# Gather allowed options from template
	allowed_options = _get_allowed_options(template)

	# 1. Check endcap map coverage
	endcap_issues = _check_endcap_map_coverage(template.template_code, allowed_options)
	result["missing_endcap_maps"] = endcap_issues

	# 2. Check mounting map coverage
	mounting_issues = _check_mounting_map_coverage(template.template_code, allowed_options)
	result["missing_mounting_maps"] = mounting_issues

	# 3. Check leader cable map coverage
	leader_issues = _check_leader_map_coverage(template, allowed_options)
	result["missing_leader_maps"] = leader_issues

	# 4. Check tape offerings whitelist
	tape_offerings_empty = len(template.allowed_tape_offerings or []) == 0
	result["missing_tape_offerings"] = tape_offerings_empty

	# 5. Check for ambiguous mappings
	ambiguous = _check_ambiguous_mappings(template.template_code, allowed_options)
	result["ambiguous_mappings"] = ambiguous

	# Determine if template has issues
	result["has_issues"] = (
		len(result["missing_endcap_maps"]) > 0
		or len(result["missing_mounting_maps"]) > 0
		or len(result["missing_leader_maps"]) > 0
		or result["missing_tape_offerings"]
		or len(result["ambiguous_mappings"]) > 0
	)

	return result


def _get_allowed_options(template) -> dict[str, list]:
	"""
	Extract allowed options from template organized by type.

	Args:
		template: ilL-Fixture-Template document

	Returns:
		dict: Allowed options organized by type
	"""
	options = {
		"finishes": [],
		"endcap_styles": [],
		"endcap_colors": [],
		"mounting_methods": [],
		"power_feed_types": [],
		"environment_ratings": [],
		"lens_appearances": [],
	}

	for opt in template.allowed_options or []:
		if not opt.is_active:
			continue

		if opt.option_type == "Finish" and opt.finish:
			options["finishes"].append(opt.finish)
		elif opt.option_type == "Endcap Style" and opt.endcap_style:
			options["endcap_styles"].append(opt.endcap_style)
		elif opt.option_type == "Mounting Method" and opt.mounting_method:
			options["mounting_methods"].append(opt.mounting_method)
		elif opt.option_type == "Power Feed Type" and opt.power_feed_type:
			options["power_feed_types"].append(opt.power_feed_type)
		elif opt.option_type == "Environment Rating" and opt.environment_rating:
			options["environment_ratings"].append(opt.environment_rating)
		elif opt.option_type == "Lens Appearance" and opt.lens_appearance:
			options["lens_appearances"].append(opt.lens_appearance)

	# Get endcap colors from attribute doctype (usually global)
	endcap_colors = frappe.get_all(
		"ilL-Attribute-Endcap Color",
		filters={"is_active": 1} if frappe.db.has_column("ilL-Attribute-Endcap Color", "is_active") else {},
		fields=["name", "code"],
	)
	options["endcap_colors"] = [c.name for c in endcap_colors]

	return options


def _check_endcap_map_coverage(
	template_code: str, allowed_options: dict
) -> list[dict[str, str]]:
	"""
	Check for missing endcap map entries.

	For each allowed (endcap_style, endcap_color) combination, check if
	a mapping exists in ilL-Rel-Endcap-Map.

	Args:
		template_code: The fixture template code
		allowed_options: Dict of allowed options

	Returns:
		list: Missing mappings as dicts with details
	"""
	missing = []

	# Get existing maps for this template
	existing_maps = frappe.get_all(
		"ilL-Rel-Endcap-Map",
		filters={"fixture_template": template_code, "is_active": 1},
		fields=["endcap_style", "endcap_color", "power_feed_type", "environment_rating"],
	)

	# Create lookup set
	existing_set = {
		(m.endcap_style, m.endcap_color)
		for m in existing_maps
	}

	# Check all combinations
	for style in allowed_options["endcap_styles"]:
		for color in allowed_options["endcap_colors"]:
			if (style, color) not in existing_set:
				missing.append({
					"type": "endcap_map",
					"endcap_style": style,
					"endcap_color": color,
					"message": f"Missing endcap map for style '{style}' + color '{color}'",
				})

	return missing


def _check_mounting_map_coverage(
	template_code: str, allowed_options: dict
) -> list[dict[str, str]]:
	"""
	Check for missing mounting accessory map entries.

	Args:
		template_code: The fixture template code
		allowed_options: Dict of allowed options

	Returns:
		list: Missing mappings as dicts with details
	"""
	missing = []

	# Get existing maps for this template
	existing_maps = frappe.get_all(
		"ilL-Rel-Mounting-Accessory-Map",
		filters={"fixture_template": template_code, "is_active": 1},
		fields=["mounting_method", "environment_rating"],
	)

	# Create lookup set (mounting_method is the key, env_rating is optional)
	existing_methods = {m.mounting_method for m in existing_maps}

	# Check all allowed mounting methods
	for method in allowed_options["mounting_methods"]:
		if method not in existing_methods:
			missing.append({
				"type": "mounting_map",
				"mounting_method": method,
				"message": f"Missing mounting map for method '{method}'",
			})

	return missing


def _check_leader_map_coverage(template, allowed_options: dict) -> list[dict[str, str]]:
	"""
	Check for missing leader cable map entries.

	Leader cable maps are keyed by (tape_spec, power_feed_type).

	Args:
		template: The fixture template document
		allowed_options: Dict of allowed options

	Returns:
		list: Missing mappings as dicts with details
	"""
	missing = []

	# Get tape specs from allowed tape offerings
	tape_specs = set()
	for offering in template.allowed_tape_offerings or []:
		if offering.tape_offering:
			tape_spec = frappe.db.get_value(
				"ilL-Rel-Tape Offering", offering.tape_offering, "tape_spec"
			)
			if tape_spec:
				tape_specs.add(tape_spec)

	if not tape_specs:
		# No tape offerings configured - this is caught separately
		return missing

	# Get existing leader maps
	existing_maps = frappe.get_all(
		"ilL-Rel-Leader-Cable-Map",
		filters={"tape_spec": ["in", list(tape_specs)], "is_active": 1},
		fields=["tape_spec", "power_feed_type"],
	)

	# Create lookup set
	existing_set = {(m.tape_spec, m.power_feed_type) for m in existing_maps}

	# Check all (tape_spec, power_feed_type) combinations
	for tape_spec in tape_specs:
		for feed_type in allowed_options["power_feed_types"]:
			if (tape_spec, feed_type) not in existing_set:
				missing.append({
					"type": "leader_map",
					"tape_spec": tape_spec,
					"power_feed_type": feed_type,
					"message": f"Missing leader map for tape '{tape_spec}' + feed '{feed_type}'",
				})

	return missing


def _check_ambiguous_mappings(
	template_code: str, allowed_options: dict
) -> list[dict[str, str]]:
	"""
	Check for ambiguous mappings (multiple matches for the same key).

	This implements Epic 2 Task 2.3: Deterministic "most specific match wins".

	Args:
		template_code: The fixture template code
		allowed_options: Dict of allowed options

	Returns:
		list: Ambiguous mappings as dicts with details
	"""
	ambiguous = []

	# Check endcap maps for ambiguity
	for style in allowed_options["endcap_styles"]:
		for color in allowed_options["endcap_colors"]:
			matches = frappe.get_all(
				"ilL-Rel-Endcap-Map",
				filters={
					"fixture_template": template_code,
					"endcap_style": style,
					"endcap_color": color,
					"is_active": 1,
				},
				fields=["name", "power_feed_type", "environment_rating"],
			)

			# Check for multiple generic (null power_feed_type and null env_rating) matches
			generic_matches = [
				m for m in matches
				if not m.power_feed_type and not m.environment_rating
			]
			if len(generic_matches) > 1:
				ambiguous.append({
					"type": "endcap_map",
					"endcap_style": style,
					"endcap_color": color,
					"matches": len(generic_matches),
					"message": (
						f"Ambiguous: {len(generic_matches)} generic endcap maps for "
						f"style '{style}' + color '{color}'"
					),
				})

	# Check mounting maps for ambiguity
	for method in allowed_options["mounting_methods"]:
		matches = frappe.get_all(
			"ilL-Rel-Mounting-Accessory-Map",
			filters={
				"fixture_template": template_code,
				"mounting_method": method,
				"is_active": 1,
			},
			fields=["name", "environment_rating"],
		)

		generic_matches = [m for m in matches if not m.environment_rating]
		if len(generic_matches) > 1:
			ambiguous.append({
				"type": "mounting_map",
				"mounting_method": method,
				"matches": len(generic_matches),
				"message": (
					f"Ambiguous: {len(generic_matches)} generic mounting maps for "
					f"method '{method}'"
				),
			})

	return ambiguous


@frappe.whitelist()
def get_coverage_summary() -> dict[str, Any]:
	"""
	Get a quick summary of coverage status across all active templates.

	Returns:
		dict: Summary statistics
	"""
	audit_results = run_coverage_audit()

	summary = {
		"total_templates": audit_results["total_templates"],
		"healthy_templates": audit_results["total_templates"] - audit_results["templates_with_issues"],
		"templates_with_issues": audit_results["templates_with_issues"],
		"total_missing_endcap_maps": 0,
		"total_missing_mounting_maps": 0,
		"total_missing_leader_maps": 0,
		"templates_missing_tape_offerings": 0,
		"total_ambiguous_mappings": 0,
	}

	for template in audit_results["templates"]:
		summary["total_missing_endcap_maps"] += len(template["missing_endcap_maps"])
		summary["total_missing_mounting_maps"] += len(template["missing_mounting_maps"])
		summary["total_missing_leader_maps"] += len(template["missing_leader_maps"])
		if template["missing_tape_offerings"]:
			summary["templates_missing_tape_offerings"] += 1
		summary["total_ambiguous_mappings"] += len(template["ambiguous_mappings"])

	return summary
