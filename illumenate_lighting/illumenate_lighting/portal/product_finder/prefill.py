"""Resolve Finder answers against the chosen template's actual selectable values."""

import frappe

from illumenate_lighting.illumenate_lighting.portal.product_finder import engine, matcher
from illumenate_lighting.illumenate_lighting.portal.product_finder.facts import TEMPLATES
from illumenate_lighting.illumenate_lighting.portal.quiz_prefill import (
	FIELDS,
	SPECTRUM_TYPES,
	_linear_candidates,
	_norm,
)

AXES = {
	"environment_rating": ("Environment Rating", "environment_rating"),
	"cct": ("CCT", "cct"),
	"finish": ("Finish", "finish"),
	"lens_appearance": ("Lens Appearance", "lens_appearance"),
	"mounting_method": ("Mounting Method", "mounting_method"),
	"lumens_per_ft": ("Output Level", "output_level"),
	"output_voltage": ("Voltage Output", "voltage_output"),
	"driver_wattage": ("Wattage", "wattage"),
	"controller_type": ("Controller Type", "controller_type"),
	"wireless_protocol": ("Wireless Protocol", "wireless_protocol"),
	"controller_mounting": ("Mounting Type", "mounting_type"),
}


def prefill_for_template(family, template, answers, definition):
	result = {"template": template, "selections": {}, "applied": [], "unmatched": []}
	if family not in TEMPLATES or not template:
		return result
	info = TEMPLATES[family]
	doc = frappe.get_cached_doc(info[0], template)
	if not doc.is_active:
		return result
	answers = engine.prune(definition, answers)
	needed = matcher.requirements(definition, answers)
	linear = {}
	if family == "Linear Fixture":
		light = next((r["answer"] for r in needed if r["facet"] == "light_type"), None)
		linear = _linear_candidates(template, {"light_type": light})
		if linear.get("led_package"):
			result["selections"]["led_package_code"] = linear["led_package"]
	for req in needed:
		facet = req["facet"]
		axis = AXES.get(facet)
		if facet == "dimming_protocol" and family in ("Driver", "Controller"):
			axis = (
				("Input Protocol", "input_protocol")
				if family == "Driver"
				else ("Output Protocol", "output_protocol")
			)
		if not axis:
			continue
		option_type, key = axis
		candidates = []
		if family == "Linear Fixture":
			for doctype, linear_key, _tape_key, _list in FIELDS.values():
				if linear_key == key + "_code":
					candidates = linear.get(doctype, [])
			key += "_code"
		elif family in ("Driver", "Controller"):
			from illumenate_lighting.illumenate_lighting.api.driver_controller_configurator import (
				_allowed_values,
			)

			candidates = _allowed_values(doc, option_type)
		else:
			for row in doc.get("allowed_options") or []:
				if row.is_active and row.option_type == option_type:
					value = row.get(key) or row.get("attribute_link")
					if value:
						candidates.append({"value": value, "is_default": row.get("is_default")})
			if family in ("LED Tape", "LED Neon") and facet == "environment_rating":
				candidates += [
					{"value": row.environment_rating, "is_default": row.get("is_default")}
					for row in doc.get("allowed_tape_specs") or []
					if row.get("is_active", 1) and row.get("environment_rating")
				]
		candidates.sort(key=lambda c: not c.get("is_default"))
		value = next(
			(
				c["value"]
				for c in candidates
				if c["value"] in req["wanted"] or _norm(c["value"]) in req["wanted"]
			),
			None,
		)
		if facet == "driver_wattage":
			threshold = float(req["answer"])
			valid = [(float(c["value"]), c["value"]) for c in candidates if float(c["value"]) >= threshold]
			value = min(valid)[1] if valid else None
		elif facet == "lumens_per_ft" and candidates and req["selected"]:
			band = req["selected"][0]
			mid = (band["numeric_min"] + band["numeric_max"]) / 2
			levels = frappe.get_all(
				"ilL-Attribute-Output Level",
				filters={"name": ["in", [c["value"] for c in candidates]]},
				fields=["name", "value"],
			)
			value = min(levels, key=lambda r: abs(float(r.value) - mid)).name if levels else None
		if value is None:
			result["unmatched"].append({"field": facet, "answer": req["answer_label"]})
		else:
			result["selections"][key] = value
			result["applied"].append({"field": facet, "answer": req["answer_label"], "value": value})
	# Sheet spec choices include package and CCT; never fabricate options absent from the template.
	if family == "LED Sheet":
		light = next((r["answer"] for r in needed if r["facet"] == "light_type"), None)
		if light:
			names = [r.spec for r in doc.get("allowed_specs") or [] if r.is_active]
			specs = frappe.get_all(
				"ilL-Spec-LED-Sheet",
				filters={"name": ["in", names], "is_active": 1},
				fields=["name", "led_package", "cct"],
			)
			packages = frappe.get_all(
				"ilL-Attribute-LED Package",
				filters={"spectrum_type": ["in", list(SPECTRUM_TYPES.get(light, []))]},
				pluck="name",
			)
			selected = next(
				(
					s
					for s in specs
					if s.led_package in packages
					and (not result["selections"].get("cct") or s.cct == result["selections"]["cct"])
				),
				None,
			)
			if selected:
				result["selections"]["spec"] = selected.name
				result["applied"].append(
					{"field": "light_type", "answer": light, "value": selected.led_package}
				)
			else:
				result["unmatched"].append({"field": "light_type", "answer": light})
	if family == "LED Sheet":
		selected = result["selections"]
		options = {
			AXES[facet][0]: selected[key]
			for facet, (_label, key) in AXES.items()
			if key in selected and facet in ("cct", "environment_rating", "finish")
		}
		result["selections"] = {
			"template": template,
			"options": options,
			**({"spec": selected["spec"]} if selected.get("spec") else {}),
		}
	return result
