"""Recover engineering input only after authorization through its owning schedule."""

import json

import frappe

from illumenate_lighting.illumenate_lighting.portal.configuration import (
	FAMILIES,
	resolve_line,
	schedule_context,
)


def for_line(line):
	if line.get("ill_configurator_request"):
		return json.loads(line.ill_configurator_request)
	if line.get("configured_group"):
		from illumenate_lighting.illumenate_lighting.portal.group_display import stored_request

		doc = frappe.get_doc("ilL-Configured-Group", line.configured_group)
		return {
			"schema_version": 3,
			"family": doc.family,
			"template": doc.template,
			"selections": {"group_request": stored_request(doc)},
		}
	family = line.get("product_type")
	if family not in FAMILIES:
		return None
	link, doctype, template_field = FAMILIES[family]
	if not line.get(link):
		return None
	doc = frappe.get_doc(doctype, line.get(link))
	build = json.loads(doc.get("build_snapshot_json") or "{}")
	if family == "Linear Fixture":
		inputs = dict(build.get("inputs") or {})
		for field, source in {
			"fixture_template_code": "fixture_template",
			"finish_code": "finish",
			"lens_appearance_code": "lens_appearance",
			"mounting_method_code": "mounting_method",
			"endcap_color_code": "endcap_color",
			"environment_rating_code": "environment_rating",
			"tape_offering_id": "tape_offering",
		}.items():
			inputs.setdefault(field, doc.get(source))
		segments = inputs.pop("user_segments", None) or [
			dict(row.as_dict()) for row in doc.get("user_segments") or []
		]
		inputs["segments"] = segments
		inputs["include_power_supply"] = inputs.get("include_power_supply", doc.get("include_power_supply"))
		inputs["dimming_protocol_code"] = inputs.pop("dimming_protocol", None)
		# The offering supplies selectors omitted from older geometry identities.
		if inputs.get("tape_offering_id"):
			offering = frappe.get_doc("ilL-Rel-Tape Offering", inputs["tape_offering_id"])
			for field, source in {"led_package_code": "led_package", "cct_code": "cct"}.items():
				inputs.setdefault(field, offering.get(source))
	elif family in {"LED Tape", "LED Neon"}:
		inputs = dict(build.get("selections") or {})
		for field in ("cct", "output_level", "environment_rating", "finish", "include_power_supply"):
			inputs.setdefault(field, doc.get(field))
		segments = []
		for row in build.get("segments") or doc.get("segments") or []:
			segment = dict(row.as_dict()) if hasattr(row, "as_dict") else dict(row)
			prefix = "tape" if family == "LED Tape" else "fixture"
			segment[prefix + "_length_unit"] = "in"
			segment[prefix + "_length_value"] = float(segment.get("requested_length_mm") or 0) / 25.4
			segment.setdefault("end_feed_length_inches", segment.get("end_cable_length_inches") or 0)
			segments.append(segment)
		if doc.get("assembly_mode") == "BULK_REEL":
			inputs["ordering_mode"] = "BULK_REEL"
			segments = None
	else:
		inputs = {
			"template": doc.sheet_template,
			"spec": doc.sheet_spec,
			"options": {
				key: doc.get(field)
				for key, field in {
					"CCT": "selected_cct",
					"Output Level": "selected_output_level",
					"Environment Rating": "selected_environment_rating",
					"Mounting": "selected_mounting",
					"Finish": "selected_finish",
				}.items()
			},
			"coverage_width_value": build.get("coverage_width_ft", doc.coverage_width_ft),
			"coverage_width_unit": "ft",
			"coverage_height_value": build.get("coverage_height_ft", doc.coverage_height_ft),
			"coverage_height_unit": "ft",
			"include_power_supply": doc.include_power_supply,
			"dimming_protocol_code": build.get("dimming_protocol_code"),
		}
		segments = None
	return {
		"schema_version": 2,
		"family": family,
		"template": line.get(template_field) or doc.get(template_field),
		"selections": inputs,
		"segments": segments,
	}


@frappe.whitelist()
def load(schedule_name, line_key=None, line_idx=None):
	schedule = schedule_context(schedule_name)
	line = resolve_line(schedule, line_key, line_idx)
	if line is None:
		raise ValueError("Choose a schedule line to reopen")
	return {
		"request": for_line(line),
		"line_key": line.get("line_key") or line.name,
		"modified": str(schedule.modified),
	}
