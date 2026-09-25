"""Pure family previews composed into one independent-member engineering build."""

import json

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	canonical_json,
	fingerprint,
	finite_number,
)
from illumenate_lighting.illumenate_lighting.api.group_contract import (
	ENGINE_VERSION,
	TEMPLATE_TYPES,
	merge_components,
	normalize,
)
from illumenate_lighting.illumenate_lighting.api.power_planner import MAX_CIRCUITS, plan_power


def engineering(value):
	"""Remove commercial calculation fields recursively from manufacturing identity."""
	if isinstance(value, dict):
		return {
			k: engineering(v)
			for k, v in value.items()
			if not any(part in k.lower() for part in ("price", "pricing", "msrp", "cost"))
		}
	if isinstance(value, list):
		return [engineering(v) for v in value]
	return value


def _preview_member(request, geometry):
	from illumenate_lighting.illumenate_lighting.api.configured_product_builder import _dispatch_calculate
	from illumenate_lighting.illumenate_lighting.portal.configuration import normalized_payload

	family, template = request["family"], request["template"]
	selection = {**request["shared"], **geometry, **request["power"], "include_power_supply": False}
	if family == "Linear Fixture":
		selection["fixture_template_code"] = template
	elif family == "LED Sheet":
		selection["template"] = template
		# Derive Sheet feed size from the filtered eligible drivers when group power is included.
		selection["include_power_supply"] = request["power"]["include_power_supply"]
	payload = normalized_payload(
		family, selection, product_slug=template, template=template, segments=geometry.get("segments")
	)
	result = _dispatch_calculate(
		family,
		payload,
		parent_configured_fixture=None,
		parent_configured_tape_neon=None,
		tape_neon_template=template,
	)
	if not result.get("is_valid"):
		messages = "; ".join(
			m.get("text", "") for m in result.get("messages", []) if m.get("severity") == "error"
		)
		raise ValueError(result.get("error") or messages or "A group member could not be calculated")
	if family == "Linear Fixture":
		build = result["build_snapshot"]
		pricing_inputs = result["pricing_inputs"]
		unit_msrp = result["pricing"]["msrp_unit"]
		offering = frappe.get_doc("ilL-Rel-Tape Offering", payload["tape_offering_id"])
		spec = frappe.get_doc("ilL-Spec-LED Tape", offering.tape_spec)
	elif family == "LED Sheet":
		build = json.loads(result["build_snapshot_json"])
		pricing_inputs = {"sheet_template": template}
		unit_msrp = result["total_msrp"] - result["pricing"].get("power_supplies_msrp", 0)
		# Keep physical Sheet feeds/leaders, then allocate supplies once at the parent.
		build["include_power_supply"] = False
		build["components"] = [r for r in build["components"] if r.get("role") != "power"]
		build["power_plan"] = {
			"status": "excluded",
			"drivers": [],
			"allocations": [],
			"requirements": build["power_plan"]["requirements"],
		}
		for feed in build["groups"]:
			for key in (
				"compatible_driver",
				"driver_spec",
				"driver_max_wattage",
				"supply_number",
				"output_number",
			):
				feed.pop(key, None)
		spec = frappe.get_doc("ilL-Spec-LED-Sheet", result["spec"])
	else:
		build = result["build_snapshot"]
		pricing_inputs = {"tape_neon_template": template, "product_category": family}
		unit_msrp = result["computed"]["total_price_msrp"]
		spec = frappe.get_doc("ilL-Spec-LED Tape", result["resolved_items"]["tape_spec"])
	voltage, protocol = spec.get("input_voltage"), spec.get("input_protocol")
	if not voltage or not protocol:
		raise ValueError("Member light engines require an approved voltage and output protocol")
	build = engineering(build)
	if family == "LED Sheet":
		circuits = [{"run_key": str(g["group_number"]), "watts": g["group_watts"]} for g in build["groups"]]
	else:
		circuits = [
			{"run_key": str(i + 1), "watts": run["run_watts"]}
			for i, run in enumerate(build["computed"]["runs"])
		]
	return {
		"build": build,
		"pricing_inputs": pricing_inputs,
		"circuits": circuits,
		"voltage": voltage,
		"output_protocol": protocol,
		"unit_msrp": finite_number(unit_msrp, minimum=0, field="member MSRP"),
	}


def calculate(request):
	from illumenate_lighting.illumenate_lighting.api.driver_catalog import candidates
	from illumenate_lighting.illumenate_lighting.api.tape_neon_build import item_row
	from illumenate_lighting.illumenate_lighting.api.tape_neon_pricing import selling_amount

	raw = json.loads(request) if isinstance(request, str) else request
	request = normalize(raw)
	from illumenate_lighting.illumenate_lighting.api.group_contract import member_presentation

	presentation = member_presentation(raw, request)
	family, template = request["family"], request["template"]
	template_doc = frappe.get_doc(TEMPLATE_TYPES[family], template)
	if not template_doc.get("is_active"):
		raise ValueError("This group template is unavailable")
	if family in {"LED Tape", "LED Neon"} and template_doc.product_category != family:
		raise ValueError("Group template does not match its family")
	members, circuits, components, breakdown = [], [], [], []
	compatibility = None
	for index, geometry in enumerate(request["members"], 1):
		member = _preview_member(request, geometry)
		electrical = (member["voltage"], member["output_protocol"])
		if compatibility is not None and electrical != compatibility:
			raise ValueError("Group members require the same voltage and output protocol")
		compatibility = electrical
		key = f"M{index}"
		member_circuits = [
			{**c, "run_key": key + ":" + c["run_key"], "member": key} for c in member["circuits"]
		]
		circuits.extend(member_circuits)
		if len(circuits) > MAX_CIRCUITS:
			raise ValueError("This group exceeds 12 independent circuits; engineering review is required")
		member_components = member["build"]["components"]
		if any(row.get("role") == "power" for row in member_components):
			raise ValueError("Member previews must exclude individual power supplies")
		components.extend(member_components)
		members.append(
			{
				"member_key": key,
				"geometry": geometry,
				"build": member["build"],
				"pricing_inputs": member["pricing_inputs"],
				"circuits": member_circuits,
			}
		)
		breakdown.append(
			{"member": key, "qty": 1, "unit_msrp": member["unit_msrp"], "extended_msrp": member["unit_msrp"]}
		)
	include = request["power"]["include_power_supply"]
	drivers, revisions = (
		candidates(
			TEMPLATE_TYPES[family], template, *compatibility, request["power"]["dimming_protocol_code"]
		)
		if include
		else ([], {})
	)
	plan = plan_power(circuits, drivers, include_power=include)
	plan["dependency_revisions"] = {
		row["driver_item"]: revisions[row["driver_item"]] for row in plan["drivers"]
	}
	for row in plan["drivers"]:
		components.append(item_row(row["driver_item"], row["qty"], "power"))
		rate = selling_amount(row["driver_item"], 1)
		breakdown.append(
			{
				"item_code": row["driver_item"],
				"role": "power",
				"qty": row["qty"],
				"unit_msrp": rate,
				"extended_msrp": rate * row["qty"],
			}
		)
	build = {
		"engine_version": ENGINE_VERSION,
		"request": request,
		"members": members,
		"components": merge_components(components),
		"power_plan": plan,
		"voltage": compatibility[0],
		"output_protocol": compatibility[1],
		"total_watts": sum(c["watts"] for c in circuits),
	}
	return {
		"success": True,
		"is_valid": True,
		"build": build,
		"presentation": presentation,
		"input_hash": fingerprint(request),
		"config_hash": fingerprint(build),
		"build_snapshot_json": canonical_json(build),
		"pricing": {
			"breakdown": breakdown,
			"msrp_unit": round(sum(r["extended_msrp"] for r in breakdown), 2),
		},
		"messages": [],
	}


@frappe.whitelist(methods=["POST"])
def preview(request):
	from illumenate_lighting.illumenate_lighting.api.configuration_contract import parse_bool
	from illumenate_lighting.illumenate_lighting.api.pricing_utils import get_tier_price_for_customer
	from illumenate_lighting.illumenate_lighting.portal.access import require_catalog_access

	require_catalog_access()
	if not parse_bool(frappe.conf.get("ill_portal_fixture_groups"), default=False):
		frappe.throw("Independent fixture groups are not enabled for this site", frappe.PermissionError)
	result = calculate(request)
	result["pricing"].update(get_tier_price_for_customer(result["pricing"]["msrp_unit"]))
	return result
