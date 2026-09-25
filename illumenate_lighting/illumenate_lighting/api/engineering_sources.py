"""Engineering-only source values sealed with a build for later PDF mapping."""

import json

import frappe

FIELDS = {
	"ilL-Spec-LED Tape": "item led_package product_category leader_cable_item input_voltage watts_per_foot voltage_drop_max_run_length_ft operating_temp input_protocol lumens_per_foot cri_typical led_pitch_mm pcb_mounting pcb_finish cut_increment_mm is_free_cutting",
	"ilL-Rel-Tape Offering": "tape_spec cct cri sdcm led_package output_level watts_per_ft_override cut_increment_mm_override",
	"ilL-Spec-Profile": "item family variant_code series width_mm height_mm dimensions weight_per_meter_grams stock_length_mm max_assembled_length_mm is_cuttable supports_joiners joiner_system lens_interface",
	"ilL-Spec-Lens": "lens_appearance series stock_type stock_length_mm continuous_max_length_mm item family",
	"ilL-Spec-Driver": "item input_voltage input_voltage_min input_voltage_max input_voltage_type voltage_output outputs_count output_type output_protocol max_wattage max_wattage_per_output usable_load_factor sku_control_code sku_wattage_output_code sku_form_code width_mm height_mm depth_mm weight_grams independent_outputs_count",
}


def capture(*, tape_spec=None, tape_offering=None, profile=None, lens=None, driver=None):
	names = dict(zip(FIELDS, (tape_spec, tape_offering, profile, lens, driver), strict=True))
	result = {}
	for doctype, name in names.items():
		values = frappe.db.get_value(doctype, name, FIELDS[doctype].split(), as_dict=True) if name else None
		result[doctype] = {"name": name, **dict(values or {})}
		if doctype == "ilL-Spec-Driver" and name:
			protocols = frappe.get_all(
				"ilL-Child-Driver-Input-Protocol",
				filters={"parent": name},
				fields=["protocol"],
				order_by="idx",
			)
			result[doctype]["input_protocols"] = ", ".join(row.protocol for row in protocols if row.protocol)
	return result


def resolve(configured, doctype, field):
	"""Return (handled, value). A sealed build never falls back to changed masters."""
	if not configured or doctype not in FIELDS:
		return False, None
	raw = configured.get("build_snapshot_json")
	build = json.loads(raw) if raw else configured
	sealed = build.get("engine_version") in ("linear-2", "tape-neon-2")
	if not sealed:
		return False, None
	sources = build.get("engineering_sources") or {}
	return True, (sources.get(doctype) or {}).get(field)
