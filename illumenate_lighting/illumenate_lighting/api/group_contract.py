"""Canonical independent-member requests. No database or customer metadata."""

import json

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	FAMILY_ALIASES,
	canonical_json,
	finite_number,
	length_mm,
	optional_positive,
	parse_bool,
)

ENGINE_VERSION = "fixture-group-1"
TEMPLATE_TYPES = {
	"Linear Fixture": "ilL-Fixture-Template",
	"LED Tape": "ilL-Tape-Neon-Template",
	"LED Neon": "ilL-Tape-Neon-Template",
	"LED Sheet": "ilL-LED-Sheet-Template",
}
SHARED_FIELDS = {
	"Linear Fixture": {
		"finish_code",
		"lens_appearance_code",
		"mounting_method_code",
		"environment_rating_code",
		"endcap_color_code",
		"tape_offering_id",
		"led_package_code",
		"cct_code",
		"delivered_output_value",
	},
	"LED Tape": {
		"cct",
		"output_level",
		"environment_rating",
		"finish",
		"tape_spec",
		"mounting_accessory_item",
		"mounting_accessory_qty",
		"pcb_finish",
		"pcb_mounting",
	},
	"LED Neon": {
		"cct",
		"output_level",
		"environment_rating",
		"finish",
		"tape_spec",
		"mounting_accessory_item",
		"mounting_accessory_qty",
		"pcb_finish",
		"pcb_mounting",
	},
	"LED Sheet": {"spec", "options"},
}


def member_presentation(raw, normalized=None):
	"""Match display labels to canonical members, consuming duplicates once each."""
	normalized = normalized or normalize(raw)
	available = list(enumerate(normalized["members"], 1))
	result = []
	for member in raw["members"]:
		geometry = normalize({**raw, "members": [member]})["members"][0]
		index, _ = next(pair for pair in available if pair[1] == geometry)
		available.remove((index, geometry))
		result.append(
			{
				"member_key": f"M{index}",
				"label": str(member.get("label") or f"M{index}")[:100],
				"member_id": member.get("member_id"),
			}
		)
	return result


def object_value(value, label):
	if isinstance(value, str):
		value = json.loads(value)
	if not isinstance(value, dict):
		raise ValueError(f"{label} must be an object")
	return value


def _length(value, unit, *, positive=False):
	result = round(length_mm(value, unit), 6)
	if positive and result <= 0:
		raise ValueError("Member lengths must be positive")
	return result


def _segment(raw, family, index):
	raw = object_value(raw, "segment")
	for field in set().union(*SHARED_FIELDS.values()) | {
		"family",
		"template",
		"include_power_supply",
		"override_max_run_ft",
		"dimming_protocol_code",
		"ordering_mode",
	}:
		if field in raw:
			raise ValueError("Segment specifications and power must be selected once for the group: " + field)
	linear = family == "Linear Fixture"
	prefix = "tape" if family == "LED Tape" else "fixture"
	if "requested_length_mm" in raw:
		mm = _length(raw["requested_length_mm"], "mm", positive=True)
	else:
		unit = raw.get(prefix + "_length_unit") or raw.get("length_unit") or "in"
		if unit == "ft_in":
			mm = _length(raw.get(prefix + "_length_feet", 0), "ft") + _length(
				raw.get(prefix + "_length_inches", 0), "in"
			)
		else:
			mm = _length(raw.get(prefix + "_length_value", raw.get("length_value")), unit, positive=True)
	if mm <= 0:
		raise ValueError("Member lengths must be positive")
	end = raw.get("end_type") or "Endcap"
	if end not in {"Endcap", "Jumper"}:
		raise ValueError("Segment end must be Endcap or Jumper")
	result = {"segment_index": index, "requested_length_mm": round(mm, 6), "end_type": end}
	if raw.get("ip_rating"):
		result["ip_rating"] = str(raw["ip_rating"])
	for key in ("start_feed_direction", "end_feed_direction", "start_power_feed_type", "end_power_feed_type"):
		result[key] = str(raw.get(key) or "").strip()
	if linear:
		result["start_leader_cable_length_mm"] = _length(raw.get("start_leader_cable_length_mm", 0), "mm")
		result["end_jumper_cable_length_mm"] = (
			_length(raw.get("end_jumper_cable_length_mm", 0), "mm") if end == "Jumper" else 0
		)
	else:
		result["start_lead_length_inches"] = round(
			_length(raw.get("start_lead_length_inches", 0), "in") / 25.4, 8
		)
		result["end_feed_length_inches"] = round(
			_length(raw.get("end_feed_length_inches", 0), "in") / 25.4, 8
		)
		result[prefix + "_length_value"] = round(mm / 25.4, 8)
		result[prefix + "_length_unit"] = "in"
		# The normalized millimeter value carries identity; inches adapt the existing engine.
	return result


def normalize(value):
	request = object_value(value, "group request")
	family = FAMILY_ALIASES.get(request.get("family"))
	if family not in TEMPLATE_TYPES:
		raise ValueError("Select one supported family for the entire group")
	template = str(request.get("template") or "").strip()
	if not template:
		raise ValueError("A group template is required")
	shared = object_value(request.get("shared") or {}, "shared specifications")
	unknown = set(shared) - SHARED_FIELDS[family]
	if unknown:
		raise ValueError("Unsupported shared specifications: " + ", ".join(sorted(unknown)))
	shared = {k: v for k, v in shared.items() if v not in (None, "")}
	if "delivered_output_value" in shared:
		shared["delivered_output_value"] = finite_number(shared["delivered_output_value"], minimum=0)
	if "mounting_accessory_qty" in shared:
		qty = finite_number(shared["mounting_accessory_qty"], minimum=1)
		if not qty.is_integer():
			raise ValueError("Mounting quantity must be a whole number")
		shared["mounting_accessory_qty"] = int(qty)
	power = object_value(request.get("power") or {}, "power policy")
	override = optional_positive(power.get("override_max_run_ft"), field="maximum run length")
	if family == "LED Sheet" and override is not None:
		raise ValueError("Sheet areas do not support a maximum run override")
	policy = {
		"include_power_supply": parse_bool(power.get("include_power_supply"), default=True),
		"dimming_protocol_code": str(power.get("dimming_protocol_code") or "").strip() or None,
		"override_max_run_ft": override,
	}
	members = request.get("members")
	if not isinstance(members, list) or not 1 <= len(members) <= 12:
		raise ValueError("A group requires between 1 and 12 independent members")
	normalized = []
	for member in members:
		member = object_value(member, "member")
		if member.get("family", family) != family or member.get("template", template) != template:
			raise ValueError("All group members must use the same family and template")
		geometry = object_value(member.get("input"), "member geometry")
		if family == "LED Sheet":
			allowed = {
				"coverage_width_ft",
				"coverage_height_ft",
				"coverage_width_value",
				"coverage_height_value",
				"coverage_width_unit",
				"coverage_height_unit",
			}
			if set(geometry) - allowed:
				raise ValueError("Sheet members contain area dimensions only")
			area = {}
			for axis in ("width", "height"):
				key = "coverage_" + axis
				value = geometry.get(key + "_value", geometry.get(key + "_ft"))
				unit = geometry.get(key + "_unit") or "ft"
				area[key + "_ft"] = round(_length(value, unit, positive=True) / 304.8, 9)
			normalized.append(area)
		else:
			if set(geometry) != {"segments"}:
				raise ValueError(
					"Each member contains segments only; specifications and power belong to the group"
				)
			segments = geometry["segments"]
			if not isinstance(segments, list) or not 1 <= len(segments) <= 24:
				raise ValueError("Each member requires between 1 and 24 segments")
			segments = [_segment(s, family, i + 1) for i, s in enumerate(segments)]
			if segments[-1]["end_type"] != "Endcap":
				raise ValueError("A member's final segment cannot jump to another member")
			normalized.append({"segments": segments})
	# Member labels, UUIDs, ordering, view and commercial quantity are presentation only.
	return {
		"schema_version": 3,
		"engine_version": ENGINE_VERSION,
		"family": family,
		"template": template,
		"shared": shared,
		"power": policy,
		"members": sorted(normalized, key=canonical_json),
	}


def merge_components(rows):
	"""Merge stock quantities only when manufacturing semantics are identical."""
	totals = {}
	for row in rows:
		key_fields = (
			"item_code",
			"stock_uom",
			"uom",
			"conversion_factor",
			"source_warehouse",
			"operation",
			"include_item_in_manufacturing",
		)
		key = canonical_json({k: row.get(k) for k in key_fields})
		if key not in totals:
			totals[key] = {k: row[k] for k in key_fields if row.get(k) is not None}
			totals[key]["qty"] = 0
		qty = finite_number(row.get("qty"), minimum=0, field="component quantity")
		if qty <= 0 or not row.get("item_code") or not row.get("stock_uom"):
			raise ValueError("Each group component requires an Item, stock UOM and positive quantity")
		totals[key]["qty"] += qty
	return [{**totals[k], "qty": round(totals[k]["qty"], 9)} for k in sorted(totals)]
