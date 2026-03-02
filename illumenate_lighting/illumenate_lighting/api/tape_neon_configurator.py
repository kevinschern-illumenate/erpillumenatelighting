# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
LED Tape & LED Neon Configurator Engine API

Provides the configuration, validation, and part-number-building flow for:
  - LED Tape (standalone tape reels, not assembled into a fixture)
  - LED Neon (silicone neon extrusion products with endcaps and segments)

Both product types follow a similar step-by-step selection process to build a
configured part number and calculate a manufacturable length based on the
tape's cut increment (or free cutting flag).

LED Tape flow:
  Environment → CCT → Output → PCB Mounting → PCB Finish
  → Feed Direction (always End) → Feed Type → Lead Length (in)
  → Tape Length (in / ft / ft+in) → Calculate ▸ Part Number + Mfg Length

LED Neon flow (multi-segment):
  CCT → Output → Mounting → Finish
  Per-segment: IP type → Start Feed Direction → Start Lead Length
               → Fixture Length → End Feed Direction → End Feed (jumper) Length

When added to a schedule and converted to a Sales Order, LED Tape produces
two SO lines: leader cable (qty = lead length) and tape item (qty = mfg length).
LED Neon produces similar lines per segment.
"""

import json
import math
from typing import Any, Optional

import frappe
from frappe import _
from frappe.utils import now

from illumenate_lighting.illumenate_lighting.api.unit_conversion import (
    inches_to_mm,
    mm_to_inches,
)


# ═══════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════
MM_PER_INCH = 25.4
MM_PER_FOOT = 304.8
INCHES_PER_FOOT = 12


# ═══════════════════════════════════════════════════════════════════════
# LED TAPE CONFIGURATOR
# ═══════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_tape_configurator_init(tape_spec_name: str = None) -> dict:
    """
    Initialise the LED Tape configurator.

    If *tape_spec_name* is given, pre-select that tape spec and narrow options.
    Otherwise return all active LED Tape specs and the union of their options .

    Returns everything the front-end needs to render the step UI:
      - Available tape specs (for a product selector)
      - Environment ratings, CCTs, output levels available across those tapes
      - PCB Mounting / PCB Finish options available across those tapes
      - Feed direction (always "End Feed" for tape)
      - Feed types (power feed type options)
    """
    filters = {"product_category": "LED Tape"}
    if tape_spec_name:
        filters["name"] = tape_spec_name

    tape_specs = frappe.get_all(
        "ilL-Spec-LED Tape",
        filters=filters,
        fields=[
            "name", "item", "led_package", "input_voltage",
            "watts_per_foot", "cut_increment_mm", "is_free_cutting",
            "pcb_mounting", "pcb_finish", "lumens_per_foot",
            "leader_cable_item", "voltage_drop_max_run_length_ft",
        ],
        order_by="name asc",
    )

    if not tape_specs:
        return {"success": False, "error": "No LED Tape specs found"}

    # Collect tape offering data linked to these specs
    spec_names = [s.name for s in tape_specs]
    tape_offerings = frappe.get_all(
        "ilL-Rel-Tape Offering",
        filters={"tape_spec": ["in", spec_names], "is_active": 1},
        fields=["name", "tape_spec", "cct", "cri", "sdcm", "led_package", "output_level"],
    )

    # Build option sets
    environment_ratings = _get_environment_ratings_for_tape_offerings(tape_offerings, spec_names)
    ccts = _collect_attribute_options(tape_offerings, "cct", "ilL-Attribute-CCT",
                                     ["name", "code", "kelvin", "description"])
    output_levels = _collect_attribute_options(tape_offerings, "output_level", "ilL-Attribute-Output Level",
                                              ["name", "value", "sku_code"])
    # Format output levels with lm/ft labels
    for ol in output_levels:
        if ol.get("value"):
            ol["label"] = f"{ol['value']} lm/ft"

    # Collect unique PCB mountings and PCB finishes from tape specs
    pcb_mountings = sorted({s.pcb_mounting for s in tape_specs if s.pcb_mounting})
    pcb_finishes = sorted({s.pcb_finish for s in tape_specs if s.pcb_finish})

    # Feed types
    feed_types = _get_feed_types()

    return {
        "success": True,
        "product_category": "LED Tape",
        "tape_specs": [
            {
                "name": s.name,
                "item": s.item,
                "led_package": s.led_package,
                "watts_per_foot": s.watts_per_foot,
                "cut_increment_mm": s.cut_increment_mm,
                "is_free_cutting": s.is_free_cutting,
                "pcb_mounting": s.pcb_mounting,
                "pcb_finish": s.pcb_finish,
                "leader_cable_item": s.leader_cable_item,
            }
            for s in tape_specs
        ],
        "options": {
            "environment_ratings": environment_ratings,
            "ccts": ccts,
            "output_levels": output_levels,
            "pcb_mountings": [{"value": m, "label": m} for m in pcb_mountings],
            "pcb_finishes": [{"value": f, "label": f} for f in pcb_finishes],
            "feed_types": feed_types,
        },
    }


@frappe.whitelist()
def get_tape_cascading_options(
    environment_rating: str = None,
    cct: str = None,
    pcb_mounting: str = None,
    pcb_finish: str = None,
) -> dict:
    """
    Return filtered options for the LED Tape configurator based on prior selections.

    Cascading logic:
      - Environment → filters available CCTs & outputs from matching tape offerings
      - CCT → filters available outputs
      - PCB Mounting / Finish → filters available tape specs
    """
    base_filters = {"product_category": "LED Tape"}
    spec_filters = dict(base_filters)
    if pcb_mounting:
        spec_filters["pcb_mounting"] = pcb_mounting
    if pcb_finish:
        spec_filters["pcb_finish"] = pcb_finish

    matching_specs = frappe.get_all(
        "ilL-Spec-LED Tape",
        filters=spec_filters,
        fields=["name"],
    )
    spec_names = [s.name for s in matching_specs]
    if not spec_names:
        return {"success": True, "ccts": [], "output_levels": []}

    offering_filters = {"tape_spec": ["in", spec_names], "is_active": 1}
    tape_offerings = frappe.get_all(
        "ilL-Rel-Tape Offering",
        filters=offering_filters,
        fields=["name", "tape_spec", "cct", "output_level"],
    )

    # Filter offerings by environment if selected
    if environment_rating:
        # Environment rating filtering happens at the template/offering level
        # For standalone tape, we pass through all offerings for now
        # but filter ccts/outputs from matching ones
        pass

    # Filter by cct if selected
    filtered_offerings = tape_offerings
    if cct:
        filtered_offerings = [o for o in tape_offerings if o.cct == cct]

    ccts = _collect_attribute_options(tape_offerings, "cct", "ilL-Attribute-CCT",
                                     ["name", "code", "kelvin", "description"])
    output_levels = _collect_attribute_options(filtered_offerings, "output_level",
                                              "ilL-Attribute-Output Level",
                                              ["name", "value", "sku_code"])
    for ol in output_levels:
        if ol.get("value"):
            ol["label"] = f"{ol['value']} lm/ft"

    return {
        "success": True,
        "ccts": ccts,
        "output_levels": output_levels,
    }


@frappe.whitelist()
def validate_tape_configuration(
    selections: str,
) -> dict:
    """
    Validate a complete LED Tape configuration and compute manufacturable length.

    Selections dict keys:
      - environment_rating     (str)
      - cct                    (str)
      - output_level           (str)
      - pcb_mounting           (str)
      - pcb_finish             (str)
      - feed_direction         (str) – always "End Feed" for tape
      - feed_type              (str) – power feed type code
      - lead_length_inches     (float)
      - tape_length_value      (float) – the numeric value
      - tape_length_unit       (str) – "in", "ft", or "ft_in"
      - tape_length_feet       (float) – only when unit is ft_in
      - tape_length_inches     (float) – only when unit is ft_in

    Returns:
      - is_valid
      - part_number
      - build_description
      - requested_length_mm
      - manufacturable_length_mm
      - resolved tape spec + tape offering + leader cable item
    """
    try:
        sel = json.loads(selections) if isinstance(selections, str) else selections
    except json.JSONDecodeError:
        return {"success": False, "is_valid": False, "error": "Invalid selections JSON"}

    messages = []

    # ── Required fields ───────────────────────────────────────────────
    required = ["cct", "output_level", "pcb_mounting", "pcb_finish",
                "feed_type", "lead_length_inches"]
    missing = [f for f in required if not sel.get(f)]
    if missing:
        return {
            "success": False,
            "is_valid": False,
            "error": f"Missing required fields: {', '.join(missing)}",
            "missing_fields": missing,
        }

    # ── Parse requested tape length ───────────────────────────────────
    requested_length_mm = _parse_tape_length(sel)
    if requested_length_mm is None or requested_length_mm <= 0:
        return {
            "success": False,
            "is_valid": False,
            "error": "Invalid tape length. Please enter a positive length.",
        }

    lead_length_inches = float(sel.get("lead_length_inches", 0))
    if lead_length_inches <= 0:
        return {
            "success": False,
            "is_valid": False,
            "error": "Lead length must be a positive number.",
        }

    # ── Find matching tape spec ───────────────────────────────────────
    tape_spec = _find_matching_tape_spec(
        product_category="LED Tape",
        pcb_mounting=sel.get("pcb_mounting"),
        pcb_finish=sel.get("pcb_finish"),
    )
    if not tape_spec:
        return {
            "success": False,
            "is_valid": False,
            "error": "No LED Tape spec found for the selected PCB Mounting and Finish.",
        }

    # ── Find matching tape offering ───────────────────────────────────
    tape_offering = _find_matching_tape_offering(
        tape_spec_name=tape_spec.name,
        cct=sel.get("cct"),
        output_level=sel.get("output_level"),
    )
    if not tape_offering:
        return {
            "success": False,
            "is_valid": False,
            "error": "No tape offering found for the selected CCT and Output Level.",
        }

    # ── Compute manufacturable length ─────────────────────────────────
    is_free_cutting = tape_spec.is_free_cutting
    cut_increment_mm = tape_spec.cut_increment_mm or 0

    if is_free_cutting or cut_increment_mm <= 0:
        manufacturable_length_mm = requested_length_mm
    else:
        # Snap to nearest cut increment
        increments = math.floor(requested_length_mm / cut_increment_mm)
        if increments < 1:
            increments = 1
        manufacturable_length_mm = increments * cut_increment_mm

    difference_mm = requested_length_mm - manufacturable_length_mm

    # Warn if there's a length difference
    if abs(difference_mm) > 0.5:
        diff_in = difference_mm / MM_PER_INCH
        messages.append({
            "severity": "warning",
            "text": (
                f"Requested length adjusted by {abs(diff_in):.2f}\" "
                f"({abs(difference_mm):.1f} mm) to fit the nearest cut increment "
                f"of {cut_increment_mm:.1f} mm."
            ),
            "field": "tape_length",
        })

    # ── Build part number ─────────────────────────────────────────────
    part_number = _build_tape_part_number(sel, tape_spec, tape_offering)

    # ── Build description ─────────────────────────────────────────────
    mfg_length_in = manufacturable_length_mm / MM_PER_INCH
    mfg_length_ft = manufacturable_length_mm / MM_PER_FOOT
    build_description = _build_tape_description(sel, tape_spec, tape_offering,
                                                manufacturable_length_mm,
                                                lead_length_inches)

    # ── Resolved items ────────────────────────────────────────────────
    # The tape item is from the tape spec, leader cable item is also on the spec
    tape_item = tape_spec.item
    leader_cable_item = tape_spec.leader_cable_item

    return {
        "success": True,
        "is_valid": True,
        "messages": messages,
        "product_category": "LED Tape",
        "part_number": part_number,
        "build_description": build_description,
        "computed": {
            "requested_length_mm": requested_length_mm,
            "requested_length_in": round(requested_length_mm / MM_PER_INCH, 2),
            "manufacturable_length_mm": round(manufacturable_length_mm, 1),
            "manufacturable_length_in": round(mfg_length_in, 2),
            "manufacturable_length_ft": round(mfg_length_ft, 2),
            "difference_mm": round(difference_mm, 1),
            "is_free_cutting": bool(is_free_cutting),
            "cut_increment_mm": cut_increment_mm,
            "lead_length_inches": lead_length_inches,
            "watts_per_foot": tape_spec.watts_per_foot or 0,
            "total_watts": round((mfg_length_ft) * (tape_spec.watts_per_foot or 0), 2),
        },
        "resolved_items": {
            "tape_spec": tape_spec.name,
            "tape_offering": tape_offering.name,
            "tape_item": tape_item,
            "leader_cable_item": leader_cable_item,
        },
        "selections": sel,
    }


# ═══════════════════════════════════════════════════════════════════════
# LED NEON CONFIGURATOR
# ═══════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_neon_configurator_init(tape_spec_name: str = None) -> dict:
    """
    Initialise the LED Neon configurator.

    LED Neon is similar to LED Tape but:
      - No environment selection (endcap IP rating chosen per-segment instead)
      - Additional mounting + finish selections
      - Multi-segment with jumper cables between segments
    """
    filters = {"product_category": "LED Neon"}
    if tape_spec_name:
        filters["name"] = tape_spec_name

    tape_specs = frappe.get_all(
        "ilL-Spec-LED Tape",
        filters=filters,
        fields=[
            "name", "item", "led_package", "input_voltage",
            "watts_per_foot", "cut_increment_mm", "is_free_cutting",
            "pcb_mounting", "pcb_finish", "lumens_per_foot",
            "leader_cable_item", "voltage_drop_max_run_length_ft",
        ],
        order_by="name asc",
    )

    if not tape_specs:
        return {"success": False, "error": "No LED Neon specs found"}

    spec_names = [s.name for s in tape_specs]
    tape_offerings = frappe.get_all(
        "ilL-Rel-Tape Offering",
        filters={"tape_spec": ["in", spec_names], "is_active": 1},
        fields=["name", "tape_spec", "cct", "cri", "sdcm", "led_package", "output_level"],
    )

    ccts = _collect_attribute_options(tape_offerings, "cct", "ilL-Attribute-CCT",
                                     ["name", "code", "kelvin", "description"])
    output_levels = _collect_attribute_options(tape_offerings, "output_level",
                                              "ilL-Attribute-Output Level",
                                              ["name", "value", "sku_code"])
    for ol in output_levels:
        if ol.get("value"):
            ol["label"] = f"{ol['value']} lm/ft"

    # Neon-specific: mounting and finish options
    pcb_mountings = sorted({s.pcb_mounting for s in tape_specs if s.pcb_mounting})
    pcb_finishes = sorted({s.pcb_finish for s in tape_specs if s.pcb_finish})

    # IP ratings for endcap selection (IP67 standard, IP68 waterproof)
    ip_ratings = _get_ip_ratings()

    # Feed directions
    feed_directions = _get_feed_directions()

    return {
        "success": True,
        "product_category": "LED Neon",
        "tape_specs": [
            {
                "name": s.name,
                "item": s.item,
                "led_package": s.led_package,
                "watts_per_foot": s.watts_per_foot,
                "cut_increment_mm": s.cut_increment_mm,
                "is_free_cutting": s.is_free_cutting,
                "pcb_mounting": s.pcb_mounting,
                "pcb_finish": s.pcb_finish,
                "leader_cable_item": s.leader_cable_item,
            }
            for s in tape_specs
        ],
        "options": {
            "ccts": ccts,
            "output_levels": output_levels,
            "mountings": [{"value": m, "label": m} for m in pcb_mountings],
            "finishes": [{"value": f, "label": f} for f in pcb_finishes],
            "ip_ratings": ip_ratings,
            "feed_directions": feed_directions,
        },
    }


@frappe.whitelist()
def validate_neon_configuration(
    selections: str,
    segments_json: str,
) -> dict:
    """
    Validate a complete LED Neon configuration with multi-segment support.

    Selections dict keys:
      - cct                 (str)
      - output_level        (str)
      - mounting            (str)
      - finish              (str)

    Segments list (per segment):
      - ip_rating           (str) – IP67 or IP68
      - start_feed_direction (str)
      - start_lead_length_inches (float)
      - fixture_length_value (float)
      - fixture_length_unit  (str) – "in", "ft", or "ft_in"
      - fixture_length_feet  (float) – when unit=ft_in
      - fixture_length_inches (float) – when unit=ft_in
      - end_feed_direction   (str)
      - end_feed_length_inches (float) – jumper/exit cable length
    """
    try:
        sel = json.loads(selections) if isinstance(selections, str) else selections
        segments = json.loads(segments_json) if isinstance(segments_json, str) else segments_json
    except json.JSONDecodeError:
        return {"success": False, "is_valid": False, "error": "Invalid JSON input"}

    messages = []

    # ── Required top-level fields ─────────────────────────────────────
    required = ["cct", "output_level", "mounting", "finish"]
    missing = [f for f in required if not sel.get(f)]
    if missing:
        return {
            "success": False,
            "is_valid": False,
            "error": f"Missing required fields: {', '.join(missing)}",
            "missing_fields": missing,
        }

    if not segments or len(segments) == 0:
        return {
            "success": False,
            "is_valid": False,
            "error": "At least one segment is required.",
        }

    # ── Find matching tape spec ───────────────────────────────────────
    tape_spec = _find_matching_tape_spec(
        product_category="LED Neon",
        pcb_mounting=sel.get("mounting"),
        pcb_finish=sel.get("finish"),
    )
    if not tape_spec:
        return {
            "success": False,
            "is_valid": False,
            "error": "No LED Neon spec found for the selected Mounting and Finish.",
        }

    # ── Find matching tape offering ───────────────────────────────────
    tape_offering = _find_matching_tape_offering(
        tape_spec_name=tape_spec.name,
        cct=sel.get("cct"),
        output_level=sel.get("output_level"),
    )
    if not tape_offering:
        return {
            "success": False,
            "is_valid": False,
            "error": "No neon offering found for the selected CCT and Output Level.",
        }

    # ── Process each segment ──────────────────────────────────────────
    is_free_cutting = tape_spec.is_free_cutting
    cut_increment_mm = tape_spec.cut_increment_mm or 0

    computed_segments = []
    total_requested_mm = 0
    total_mfg_mm = 0

    for idx, seg in enumerate(segments):
        seg_num = idx + 1

        # Validate required segment fields
        seg_required = ["ip_rating", "start_feed_direction", "start_lead_length_inches",
                        "end_feed_direction", "end_feed_length_inches"]
        seg_missing = [f for f in seg_required if not seg.get(f) and seg.get(f) != 0]
        if seg_missing:
            return {
                "success": False,
                "is_valid": False,
                "error": f"Segment {seg_num}: Missing fields: {', '.join(seg_missing)}",
            }

        # Parse fixture length
        fixture_length_mm = _parse_neon_fixture_length(seg)
        if fixture_length_mm is None or fixture_length_mm <= 0:
            return {
                "success": False,
                "is_valid": False,
                "error": f"Segment {seg_num}: Invalid fixture length.",
            }

        # Compute manufacturable length
        if is_free_cutting or cut_increment_mm <= 0:
            mfg_length_mm = fixture_length_mm
        else:
            increments = math.floor(fixture_length_mm / cut_increment_mm)
            if increments < 1:
                increments = 1
            mfg_length_mm = increments * cut_increment_mm

        diff_mm = fixture_length_mm - mfg_length_mm
        if abs(diff_mm) > 0.5:
            diff_in = diff_mm / MM_PER_INCH
            messages.append({
                "severity": "warning",
                "text": (
                    f"Segment {seg_num}: Length adjusted by {abs(diff_in):.2f}\" "
                    f"({abs(diff_mm):.1f} mm) to nearest cut increment."
                ),
                "field": f"segment_{seg_num}_length",
            })

        total_requested_mm += fixture_length_mm
        total_mfg_mm += mfg_length_mm

        computed_segments.append({
            "segment_index": seg_num,
            "ip_rating": seg.get("ip_rating"),
            "start_feed_direction": seg.get("start_feed_direction"),
            "start_lead_length_inches": float(seg.get("start_lead_length_inches", 0)),
            "requested_length_mm": round(fixture_length_mm, 1),
            "requested_length_in": round(fixture_length_mm / MM_PER_INCH, 2),
            "manufacturable_length_mm": round(mfg_length_mm, 1),
            "manufacturable_length_in": round(mfg_length_mm / MM_PER_INCH, 2),
            "difference_mm": round(diff_mm, 1),
            "end_feed_direction": seg.get("end_feed_direction"),
            "end_feed_length_inches": float(seg.get("end_feed_length_inches", 0)),
        })

    # ── Build part number & description ───────────────────────────────
    part_number = _build_neon_part_number(sel, tape_spec, tape_offering, computed_segments)
    build_description = _build_neon_description(sel, tape_spec, tape_offering, computed_segments)

    # ── Resolved items ────────────────────────────────────────────────
    tape_item = tape_spec.item
    leader_cable_item = tape_spec.leader_cable_item

    mfg_length_ft = total_mfg_mm / MM_PER_FOOT

    return {
        "success": True,
        "is_valid": True,
        "messages": messages,
        "product_category": "LED Neon",
        "part_number": part_number,
        "build_description": build_description,
        "computed": {
            "total_requested_length_mm": round(total_requested_mm, 1),
            "total_requested_length_in": round(total_requested_mm / MM_PER_INCH, 2),
            "total_manufacturable_length_mm": round(total_mfg_mm, 1),
            "total_manufacturable_length_in": round(total_mfg_mm / MM_PER_INCH, 2),
            "total_manufacturable_length_ft": round(mfg_length_ft, 2),
            "segment_count": len(computed_segments),
            "segments": computed_segments,
            "is_free_cutting": bool(is_free_cutting),
            "cut_increment_mm": cut_increment_mm,
            "watts_per_foot": tape_spec.watts_per_foot or 0,
            "total_watts": round(mfg_length_ft * (tape_spec.watts_per_foot or 0), 2),
        },
        "resolved_items": {
            "tape_spec": tape_spec.name,
            "tape_offering": tape_offering.name,
            "tape_item": tape_item,
            "leader_cable_item": leader_cable_item,
        },
        "selections": sel,
    }


# ═══════════════════════════════════════════════════════════════════════
# SAVE TO SCHEDULE  /  SALES ORDER HELPERS
# ═══════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def save_tape_to_schedule(
    schedule_name: str,
    line_idx: int = None,
    configuration_result: str = None,
) -> dict:
    """
    Save a validated LED Tape or LED Neon configuration to a fixture schedule line.

    Stores:
      - product_type = "LED Tape" or "LED Neon"
      - part number as the configured fixture reference
      - build description in notes
      - manufacturable length

    Args:
        schedule_name: ilL-Project-Fixture-Schedule name
        line_idx: existing line index to overwrite, or None for new line
        configuration_result: JSON string of the validate_tape/neon_configuration result
    """
    if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
        return {"success": False, "error": "Schedule not found"}

    schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

    from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
        has_permission,
    )
    if not has_permission(schedule, "write", frappe.session.user):
        return {"success": False, "error": "No write permission on this schedule"}

    if schedule.status not in ["DRAFT", "READY"]:
        return {"success": False, "error": "Schedule is not in an editable status"}

    try:
        result = json.loads(configuration_result) if isinstance(configuration_result, str) else configuration_result
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid configuration result JSON"}

    if not result.get("is_valid"):
        return {"success": False, "error": "Configuration is not valid"}

    product_category = result.get("product_category", "LED Tape")
    part_number = result.get("part_number", "")
    build_desc = result.get("build_description", "")
    computed = result.get("computed", {})
    resolved = result.get("resolved_items", {})

    # Determine manufacturable length
    if product_category == "LED Neon":
        mfg_length_mm = computed.get("total_manufacturable_length_mm", 0)
    else:
        mfg_length_mm = computed.get("manufacturable_length_mm", 0)

    try:
        if line_idx is not None:
            line_idx = int(line_idx)
            if 0 <= line_idx < len(schedule.lines):
                line = schedule.lines[line_idx]
            else:
                return {"success": False, "error": "Invalid line index"}
        else:
            line = schedule.append("lines", {})

        line.manufacturer_type = "ILLUMENATE"
        line.product_type = product_category
        line.configuration_status = "Configured"
        line.ill_item_code = part_number
        line.manufacturable_length_mm = round(mfg_length_mm)
        line.notes = build_desc

        # Store full configuration as JSON for later SO conversion
        line.variant_selections = json.dumps({
            "product_category": product_category,
            "part_number": part_number,
            "build_description": build_desc,
            "computed": computed,
            "resolved_items": resolved,
            "selections": result.get("selections", {}),
        })

        schedule.save()

        return {
            "success": True,
            "message": f"{product_category} configuration saved to schedule",
            "line_idx": line.idx - 1 if hasattr(line, "idx") else len(schedule.lines) - 1,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_tape_neon_so_lines(so, line, config_data: dict) -> dict:
    """
    Called during Sales Order creation to add LED Tape / LED Neon item lines.

    For LED Tape:
      Line 1: Leader cable item, QTY = lead length (inches)
      Line 2: Tape item, QTY = manufacturable length (inches or feet depending on UoM)

    For LED Neon:
      Per-segment pairs of leader cable + neon tape items

    Args:
        so: The Sales Order document being built
        line: The schedule line
        config_data: Parsed JSON from line.variant_selections

    Returns:
        dict with items_added count and messages
    """
    product_category = config_data.get("product_category", "LED Tape")
    computed = config_data.get("computed", {})
    resolved = config_data.get("resolved_items", {})
    selections = config_data.get("selections", {})

    tape_item = resolved.get("tape_item")
    leader_cable_item = resolved.get("leader_cable_item")
    part_number = config_data.get("part_number", "")
    build_desc = config_data.get("build_description", "")

    items_added = 0
    messages = []

    if product_category == "LED Tape":
        lead_length_in = computed.get("lead_length_inches", 0)
        mfg_length_in = computed.get("manufacturable_length_in", 0)

        # Line 1: Leader cable
        if leader_cable_item and lead_length_in > 0:
            so_item = so.append("items", {})
            so_item.item_code = leader_cable_item
            so_item.qty = lead_length_in
            so_item.description = f"Leader Cable for {part_number} – {lead_length_in}\" lead"
            items_added += 1
        elif not leader_cable_item:
            messages.append("Warning: No leader cable item defined on tape spec")

        # Line 2: Tape
        if tape_item and mfg_length_in > 0:
            so_item = so.append("items", {})
            so_item.item_code = tape_item
            so_item.qty = mfg_length_in
            so_item.description = (
                f"{part_number}\n{build_desc}"
            )
            items_added += 1
        elif not tape_item:
            messages.append("Warning: No tape item defined on tape spec")

    elif product_category == "LED Neon":
        segments = computed.get("segments", [])

        for seg in segments:
            seg_idx = seg.get("segment_index", 0)
            lead_in = seg.get("start_lead_length_inches", 0)
            mfg_in = seg.get("manufacturable_length_in", 0)

            # Leader cable for this segment
            if leader_cable_item and lead_in > 0:
                so_item = so.append("items", {})
                so_item.item_code = leader_cable_item
                so_item.qty = lead_in
                so_item.description = (
                    f"Leader Cable for {part_number} Seg {seg_idx} – "
                    f"{lead_in}\" lead"
                )
                items_added += 1

            # Neon tape for this segment
            if tape_item and mfg_in > 0:
                so_item = so.append("items", {})
                so_item.item_code = tape_item
                so_item.qty = mfg_in
                so_item.description = (
                    f"{part_number} Seg {seg_idx} – "
                    f"{mfg_in}\" manufacturable length"
                )
                items_added += 1

            # Jumper cable (end feed) – uses same leader cable item
            end_feed_in = seg.get("end_feed_length_inches", 0)
            if leader_cable_item and end_feed_in > 0:
                so_item = so.append("items", {})
                so_item.item_code = leader_cable_item
                so_item.qty = end_feed_in
                so_item.description = (
                    f"Jumper Cable for {part_number} Seg {seg_idx} → "
                    f"Seg {seg_idx + 1} – {end_feed_in}\" jumper"
                )
                items_added += 1

    return {"items_added": items_added, "messages": messages}


# ═══════════════════════════════════════════════════════════════════════
# PRIVATE HELPERS
# ═══════════════════════════════════════════════════════════════════════

def _parse_tape_length(sel: dict) -> Optional[float]:
    """Parse the tape length from user selections into millimeters."""
    unit = sel.get("tape_length_unit", "in")

    if unit == "ft_in":
        feet = float(sel.get("tape_length_feet", 0) or 0)
        inches = float(sel.get("tape_length_inches", 0) or 0)
        total_inches = feet * INCHES_PER_FOOT + inches
        return total_inches * MM_PER_INCH
    elif unit == "ft":
        feet = float(sel.get("tape_length_value", 0) or 0)
        return feet * MM_PER_FOOT
    else:  # "in" or default
        inches = float(sel.get("tape_length_value", 0) or 0)
        return inches * MM_PER_INCH


def _parse_neon_fixture_length(seg: dict) -> Optional[float]:
    """Parse a neon segment's fixture length into millimeters."""
    unit = seg.get("fixture_length_unit", "in")

    if unit == "ft_in":
        feet = float(seg.get("fixture_length_feet", 0) or 0)
        inches = float(seg.get("fixture_length_inches", 0) or 0)
        total_inches = feet * INCHES_PER_FOOT + inches
        return total_inches * MM_PER_INCH
    elif unit == "ft":
        val = float(seg.get("fixture_length_value", 0) or 0)
        return val * MM_PER_FOOT
    else:  # "in"
        val = float(seg.get("fixture_length_value", 0) or 0)
        return val * MM_PER_INCH


def _find_matching_tape_spec(
    product_category: str,
    pcb_mounting: str = None,
    pcb_finish: str = None,
) -> Optional[Any]:
    """Find an ilL-Spec-LED Tape matching the given filters."""
    filters: dict[str, Any] = {"product_category": product_category}
    if pcb_mounting:
        filters["pcb_mounting"] = pcb_mounting
    if pcb_finish:
        filters["pcb_finish"] = pcb_finish

    specs = frappe.get_all(
        "ilL-Spec-LED Tape",
        filters=filters,
        fields=[
            "name", "item", "led_package", "input_voltage",
            "watts_per_foot", "cut_increment_mm", "is_free_cutting",
            "pcb_mounting", "pcb_finish", "lumens_per_foot",
            "leader_cable_item", "voltage_drop_max_run_length_ft",
        ],
        order_by="name asc",
        limit=1,
    )
    return specs[0] if specs else None


def _find_matching_tape_offering(
    tape_spec_name: str,
    cct: str = None,
    output_level: str = None,
) -> Optional[Any]:
    """Find an ilL-Rel-Tape Offering matching the tape spec, CCT and output."""
    filters: dict[str, Any] = {"tape_spec": tape_spec_name, "is_active": 1}
    if cct:
        filters["cct"] = cct
    if output_level:
        filters["output_level"] = output_level

    offerings = frappe.get_all(
        "ilL-Rel-Tape Offering",
        filters=filters,
        fields=["name", "tape_spec", "cct", "cri", "sdcm", "led_package", "output_level"],
        limit=1,
    )
    return offerings[0] if offerings else None


def _get_environment_ratings_for_tape_offerings(tape_offerings, spec_names) -> list:
    """Get environment ratings from template-level tape offering rows (if any exist)."""
    # For standalone tape products, environment may come from the template's
    # allowed_tape_offerings child rows.  If none, return a default set.
    env_names = set()

    # Check if any fixture templates reference these tape specs
    template_rows = frappe.get_all(
        "ilL-Child-Template-Allowed-TapeOffering",
        filters={"tape_offering": ["in", [o.name for o in tape_offerings]]},
        fields=["environment_rating"],
    )
    for row in template_rows:
        if row.environment_rating:
            env_names.add(row.environment_rating)

    if not env_names:
        # Fallback: get all active environment ratings
        all_envs = frappe.get_all(
            "ilL-Attribute-Environment Rating",
            filters={"is_active": 1} if frappe.db.has_column("ilL-Attribute-Environment Rating", "is_active") else {},
            fields=["name", "code", "notes"],
            order_by="name asc",
        )
        return [{"value": e.name, "label": e.name, "code": e.get("code")} for e in all_envs]

    result = []
    for env_name in env_names:
        env = frappe.db.get_value(
            "ilL-Attribute-Environment Rating", env_name,
            ["name", "code", "notes"], as_dict=True,
        )
        if env:
            result.append({"value": env.name, "label": env.name, "code": env.get("code")})
    return sorted(result, key=lambda x: x["label"])


def _collect_attribute_options(offerings, field_name, doctype, fields) -> list:
    """Collect unique attribute options from tape offerings."""
    values = {getattr(o, field_name, None) or o.get(field_name) for o in offerings}
    values.discard(None)
    values.discard("")

    result = []
    for val in values:
        data = frappe.db.get_value(doctype, val, fields, as_dict=True)
        if data:
            entry = {"value": data.name, "label": data.name}
            for f in fields:
                if f != "name":
                    entry[f] = data.get(f)
            result.append(entry)

    # Sort by kelvin (CCT), value (Output), or name
    if "kelvin" in fields:
        return sorted(result, key=lambda x: x.get("kelvin") or 0)
    if "value" in fields:
        return sorted(result, key=lambda x: x.get("value") or 0)
    return sorted(result, key=lambda x: x.get("label", ""))


def _get_feed_types() -> list:
    """Get power feed type options."""
    if frappe.db.exists("DocType", "ilL-Attribute-Power Feed Type"):
        types = frappe.get_all(
            "ilL-Attribute-Power Feed Type",
            filters={"is_active": 1} if frappe.db.has_column("ilL-Attribute-Power Feed Type", "is_active") else {},
            fields=["name", "code", "label"],
            order_by="name",
        )
        return [{"value": t.name, "label": t.get("label") or t.name, "code": t.get("code")} for t in types]
    return [{"value": "Standard", "label": "Standard", "code": "S"}]


def _get_ip_ratings() -> list:
    """Get IP rating options for LED Neon endcaps."""
    if frappe.db.exists("DocType", "ilL-Attribute-IP Rating"):
        ratings = frappe.get_all(
            "ilL-Attribute-IP Rating",
            fields=["name", "code", "notes"],
            order_by="name",
        )
        return [{"value": r.name, "label": r.name, "code": r.get("code")} for r in ratings]
    # Fallback
    return [
        {"value": "IP67", "label": "IP67 – Standard", "code": "67"},
        {"value": "IP68", "label": "IP68 – Waterproof", "code": "68"},
    ]


def _get_feed_directions() -> list:
    """Get feed direction options for LED Neon."""
    if frappe.db.exists("DocType", "ilL-Attribute-Feed-Direction"):
        dirs = frappe.get_all(
            "ilL-Attribute-Feed-Direction",
            filters={"is_active": 1} if frappe.db.has_column("ilL-Attribute-Feed-Direction", "is_active") else {},
            fields=["direction_name as name", "code", "description"],
            order_by="direction_name",
        )
        return [{"value": d.name, "label": d.name, "code": d.get("code")} for d in dirs]
    return [
        {"value": "End", "label": "End", "code": "E"},
        {"value": "Back", "label": "Back", "code": "B"},
    ]


# ── Part Number Builders ──────────────────────────────────────────────

def _get_code(doctype: str, name: str, code_field: str = "code") -> str:
    """Look up an attribute code, returning 'xx' on miss."""
    if not name:
        return "xx"
    code = frappe.db.get_value(doctype, name, code_field)
    return code or "xx"


def _build_tape_part_number(sel: dict, tape_spec, tape_offering) -> str:
    """
    Build LED Tape part number.

    Format: ILL-TAPE-{ENV}-{CCT}-{OUTPUT}-{PCB_MOUNT}-{PCB_FINISH}-{FEED_TYPE}-{LEAD_LEN}in-{TAPE_LEN}
    """
    parts = ["ILL", "TAPE"]

    # Environment (optional for tape)
    env = sel.get("environment_rating")
    if env:
        parts.append(_get_code("ilL-Attribute-Environment Rating", env))

    # CCT
    parts.append(_get_code("ilL-Attribute-CCT", sel.get("cct")))

    # Output
    output_code = "xx"
    if sel.get("output_level"):
        ol_data = frappe.db.get_value(
            "ilL-Attribute-Output Level", sel["output_level"],
            ["sku_code"], as_dict=True,
        )
        if ol_data and ol_data.sku_code:
            output_code = ol_data.sku_code
    parts.append(output_code)

    # PCB Mounting (abbreviation)
    pcb_mount = (sel.get("pcb_mounting") or "xx")[:4].upper()
    parts.append(pcb_mount)

    # PCB Finish (abbreviation)
    pcb_fin = (sel.get("pcb_finish") or "xx")[:3].upper()
    parts.append(pcb_fin)

    # Feed type
    feed_type = sel.get("feed_type", "")
    if feed_type:
        ft_code = _get_code("ilL-Attribute-Power Feed Type", feed_type)
        parts.append(ft_code)

    # Lead length
    lead_in = sel.get("lead_length_inches", 0)
    parts.append(f"{float(lead_in):.0f}in")

    # Tape length (use requested for the part number)
    tape_len_mm = _parse_tape_length(sel)
    if tape_len_mm:
        tape_len_in = tape_len_mm / MM_PER_INCH
        parts.append(f"{tape_len_in:.1f}in")

    return "-".join(parts)


def _build_tape_description(sel, tape_spec, tape_offering, mfg_length_mm, lead_length_in) -> str:
    """Build a human-readable description for LED Tape configuration."""
    lines = []
    lines.append(f"LED Tape: {tape_spec.name}")
    if sel.get("environment_rating"):
        lines.append(f"Environment: {sel['environment_rating']}")
    lines.append(f"CCT: {sel.get('cct', '-')}")
    lines.append(f"Output: {sel.get('output_level', '-')}")
    lines.append(f"PCB Mounting: {sel.get('pcb_mounting', '-')}")
    lines.append(f"PCB Finish: {sel.get('pcb_finish', '-')}")
    lines.append(f"Feed Direction: End Feed")
    lines.append(f"Feed Type: {sel.get('feed_type', '-')}")
    lines.append(f"Lead Length: {lead_length_in}\"")

    mfg_in = mfg_length_mm / MM_PER_INCH
    mfg_ft = mfg_length_mm / MM_PER_FOOT
    lines.append(f"Manufacturable Length: {mfg_in:.2f}\" ({mfg_ft:.2f} ft)")

    if tape_spec.is_free_cutting:
        lines.append("Cutting: Free cutting (no cut increment)")
    else:
        lines.append(f"Cut Increment: {tape_spec.cut_increment_mm} mm")

    return " | ".join(lines)


def _build_neon_part_number(sel, tape_spec, tape_offering, segments) -> str:
    """
    Build LED Neon part number.

    Format: ILL-NEON-{CCT}-{OUTPUT}-{MOUNT}-{FINISH}-{SEG_COUNT}SEG
    """
    parts = ["ILL", "NEON"]

    # CCT
    parts.append(_get_code("ilL-Attribute-CCT", sel.get("cct")))

    # Output
    output_code = "xx"
    if sel.get("output_level"):
        ol_data = frappe.db.get_value(
            "ilL-Attribute-Output Level", sel["output_level"],
            ["sku_code"], as_dict=True,
        )
        if ol_data and ol_data.sku_code:
            output_code = ol_data.sku_code
    parts.append(output_code)

    # Mounting (abbreviation)
    mount = (sel.get("mounting") or "xx")[:4].upper()
    parts.append(mount)

    # Finish (abbreviation)
    finish = (sel.get("finish") or "xx")[:3].upper()
    parts.append(finish)

    # Segment count
    parts.append(f"{len(segments)}SEG")

    return "-".join(parts)


def _build_neon_description(sel, tape_spec, tape_offering, segments) -> str:
    """Build a human-readable description for LED Neon configuration."""
    lines = []
    lines.append(f"LED Neon: {tape_spec.name}")
    lines.append(f"CCT: {sel.get('cct', '-')}")
    lines.append(f"Output: {sel.get('output_level', '-')}")
    lines.append(f"Mounting: {sel.get('mounting', '-')}")
    lines.append(f"Finish: {sel.get('finish', '-')}")
    lines.append(f"Segments: {len(segments)}")

    for seg in segments:
        seg_idx = seg["segment_index"]
        mfg_in = seg["manufacturable_length_in"]
        ip = seg.get("ip_rating", "-")
        start_dir = seg.get("start_feed_direction", "-")
        start_lead = seg.get("start_lead_length_inches", 0)
        end_dir = seg.get("end_feed_direction", "-")
        end_lead = seg.get("end_feed_length_inches", 0)
        lines.append(
            f"Seg {seg_idx}: {mfg_in}\" | IP: {ip} | "
            f"Start: {start_dir} {start_lead}\" | "
            f"End: {end_dir} {end_lead}\""
        )

    if tape_spec.is_free_cutting:
        lines.append("Cutting: Free cutting")
    else:
        lines.append(f"Cut Increment: {tape_spec.cut_increment_mm} mm")

    return " | ".join(lines)
