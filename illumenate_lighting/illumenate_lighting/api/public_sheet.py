"""Unpriced Sheet choices and filled PDF generation using the shared engineering calculation."""

import json

import frappe
from frappe.rate_limiter import rate_limit

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint


def product_and_template(slug):
	name = frappe.db.get_value(
		"ilL-Webflow-Product", {"product_slug": slug, "product_type": "LED Sheet", "is_active": 1}, "name"
	)
	if not name:
		raise ValueError("LED Sheet product is unavailable")
	product = frappe.get_doc("ilL-Webflow-Product", name)
	if not product.led_sheet_template:
		raise ValueError("Select an approved LED Sheet template for this product")
	template = frappe.get_doc("ilL-LED-Sheet-Template", product.led_sheet_template)
	if not template.is_active:
		raise ValueError("LED Sheet template is unavailable")
	return product, template


def data(slug):
	product, template = product_and_template(slug)
	specs = []
	for row in template.allowed_specs or []:
		if not row.is_active:
			continue
		spec = frappe.get_doc("ilL-Spec-LED-Sheet", row.spec)
		if not spec.is_active:
			continue
		specs.append(
			{
				key: spec.get(key)
				for key in (
					"name",
					"cct",
					"led_package",
					"sheet_width_ft",
					"sheet_height_ft",
					"sheet_area_sqft",
					"watts_per_sqft",
					"total_sheet_watts",
					"lumens_per_sqft",
					"total_sheet_lumens",
					"input_voltage",
					"ip_rating",
				)
			}
		)
	options = {}
	for row in template.allowed_options or []:
		if row.is_active:
			options.setdefault(row.option_type, []).append(
				{"attribute": row.attribute_link, "code": row.option_code, "is_default": row.is_default}
			)
	from illumenate_lighting.illumenate_lighting.api.driver_catalog import input_protocols

	return {
		"success": True,
		"product": {
			key: product.get(key) for key in ("name", "product_name", "product_slug", "led_sheet_template")
		},
		"template": {
			key: template.get(key) for key in ("name", "template_code", "template_name", "sku_series_code")
		},
		"specs": specs,
		"options": options,
		"input_protocols": input_protocols(template.doctype, template.name)["protocols"],
	}


def request(slug, selections):
	"""Translate public choices to editable intent, without requiring a complete build."""
	from illumenate_lighting.illumenate_lighting.api.led_sheet_configurator import _norm_option_key

	_, template = product_and_template(slug)
	selected = json.loads(selections) if isinstance(selections, str) else selections
	allowed = {
		"spec",
		"options",
		"coverage_width_ft",
		"coverage_height_ft",
		"coverage_width_value",
		"coverage_width_unit",
		"coverage_height_value",
		"coverage_height_unit",
		"include_power_supply",
		"dimming_protocol_code",
	}
	if not isinstance(selected, dict) or set(selected) - allowed:
		raise ValueError("Use the displayed Sheet selections; project context is entered separately")
	values = dict(selected)
	options = values.get("options") or {}
	if not isinstance(options, dict):
		raise ValueError("Sheet options must be an object")
	resolved = {}
	for key, value in options.items():
		kind = _norm_option_key(key)
		choices = [
			row.attribute_link
			for row in template.allowed_options or []
			if row.is_active and row.option_type == kind and value in (row.attribute_link, row.option_code)
		]
		if len(set(choices)) != 1:
			raise ValueError(f"Choose one approved {kind} option")
		resolved[kind] = choices[0]
	values["options"] = resolved
	if values.get("spec") and values["spec"] not in {
		row.spec for row in template.allowed_specs or [] if row.is_active
	}:
		raise ValueError("Select an approved Sheet specification")
	if not values.get("spec"):
		choices = [row.spec for row in template.allowed_specs or [] if row.is_active]
		if len(choices) == 1:
			values["spec"] = choices[0]
	return {"schema_version": 2, "family": "LED Sheet", "template": template.name, "selections": values}


def calculate(slug, selections):
	from illumenate_lighting.illumenate_lighting.api.led_sheet_configurator import _calculate_sheet
	from illumenate_lighting.illumenate_lighting.portal.rollout import require_family

	require_family("LED Sheet", public=True)

	intent = request(slug, selections)
	if not intent["selections"].get("spec"):
		raise ValueError("Select a Sheet specification")
	return _calculate_sheet(intent["template"], commercial=False, **intent["selections"])


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=30, seconds=60)
def preview(product_slug, selections):
	result = calculate(product_slug, selections)
	# Public output contains selected engineering facts, never Item pricing, costs or build storage.
	fields = (
		"part_number",
		"coverage_width_ft",
		"coverage_height_ft",
		"panels_wide",
		"panels_tall",
		"panels_needed",
		"watts_per_panel",
		"total_system_watts",
		"total_groups",
		"panels_per_group",
		"leader_cable_qty",
		"jumper_cable_qty",
		"include_power_supply",
	)
	return {
		"success": True,
		**{key: result.get(key) for key in fields},
		"configuration_hash": result["config_hash"],
	}


def generate(slug, selections, project_name="", project_location="", fixture_type=""):
	from illumenate_lighting.illumenate_lighting.api.led_sheet_configurator import OPTION_FIELD_BY_TYPE
	from illumenate_lighting.illumenate_lighting.api.spec_submittal import generate_filled_sheet_submittal

	if not frappe.flags.get("ill_product_download"):
		raise ValueError("Use the isolated public product download endpoint")
	result = calculate(slug, selections)
	values = {
		**result,
		"name": "preview-" + fingerprint({"slug": slug, "build": result["config_hash"]})[:16],
		"doctype": "ilL-Configured-LED-Sheet",
		"sheet_template": result["template"],
		"sheet_spec": result["spec"],
	}
	values.update({OPTION_FIELD_BY_TYPE[key]: value for key, value in result["options"].items()})
	configured = frappe._dict(values)
	overrides = {
		"project_name": project_name,
		"project_location": project_location,
		"fixture_type": fixture_type,
	}
	output = generate_filled_sheet_submittal(
		configured.name,
		webflow_overrides=overrides,
		_configured_doc=configured,
		_schedule_context=(None, None, None),
	)
	if not output.get("success"):
		return {
			"success": False,
			"error": output.get("message") or "Sheet PDF mapping requires engineering setup",
		}
	return {
		"success": True,
		"file_url": output["file_url"],
		"filename": "Sheet-" + configured.name + ".pdf",
		"part_number": result["part_number"],
		"document_kind": "filled_submittal",
	}
