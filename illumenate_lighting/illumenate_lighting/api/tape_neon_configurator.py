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
        if ol.get("numeric_value"):
            ol["label"] = f"{ol['numeric_value']} lm/ft"

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
        if ol.get("numeric_value"):
            ol["label"] = f"{ol['numeric_value']} lm/ft"

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
    logger = frappe.logger("tape_neon_configurator", allow_site=True)
    try:
        sel = json.loads(selections) if isinstance(selections, str) else selections
    except json.JSONDecodeError:
        return {"success": False, "is_valid": False, "error": "Invalid selections JSON"}

    logger.info(f"validate_tape_configuration called with selections: {sel}")

    messages = []

    # ── Required fields ───────────────────────────────────────────────
    # Check string fields for presence (non-empty); check numeric fields separately
    required_str = ["cct", "output_level", "pcb_mounting", "pcb_finish", "feed_type"]
    missing = [f for f in required_str if not sel.get(f)]
    if sel.get("lead_length_inches") is None or sel.get("lead_length_inches") == "":
        missing.append("lead_length_inches")
    if missing:
        logger.warning(f"validate_tape: Missing required fields: {missing}")
        return {
            "success": False,
            "is_valid": False,
            "error": f"Missing required fields: {', '.join(missing)}",
            "missing_fields": missing,
        }

    # ── Parse requested tape length ───────────────────────────────────
    requested_length_mm = _parse_tape_length(sel)
    logger.info(f"validate_tape: parsed tape length = {requested_length_mm} mm")
    if requested_length_mm is None or requested_length_mm <= 0:
        logger.warning(f"validate_tape: Invalid tape length: {requested_length_mm}")
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

    # ── Find matching tape specs ──────────────────────────────────────
    logger.info(f"validate_tape: looking for tape specs with category=LED Tape, pcb_mounting={sel.get('pcb_mounting')}, pcb_finish={sel.get('pcb_finish')}")
    all_matching_specs = _find_all_matching_tape_specs(
        product_category="LED Tape",
        pcb_mounting=sel.get("pcb_mounting"),
        pcb_finish=sel.get("pcb_finish"),
    )
    if not all_matching_specs:
        logger.warning(f"validate_tape: No tape spec found for pcb_mounting={sel.get('pcb_mounting')}, pcb_finish={sel.get('pcb_finish')}")
        return {
            "success": False,
            "is_valid": False,
            "error": f"No LED Tape spec found for PCB Mounting='{sel.get('pcb_mounting')}' and Finish='{sel.get('pcb_finish')}'. Check that a matching ilL-Spec-LED Tape record exists.",
        }
    spec_names = [s.name for s in all_matching_specs]
    logger.info(f"validate_tape: found {len(all_matching_specs)} matching tape specs: {spec_names}")

    # ── Find matching tape offering across all matching specs ─────────
    logger.info(f"validate_tape: looking for offering with specs={spec_names}, cct={sel.get('cct')}, output_level={sel.get('output_level')}")
    tape_offering = _find_matching_tape_offering(
        tape_spec_name=spec_names,
        cct=sel.get("cct"),
        output_level=sel.get("output_level"),
    )
    if not tape_offering:
        logger.warning(f"validate_tape: No offering found for specs={spec_names}, cct={sel.get('cct')}, output_level={sel.get('output_level')}")
        return {
            "success": False,
            "is_valid": False,
            "error": f"No tape offering found for CCT='{sel.get('cct')}' and Output Level='{sel.get('output_level')}' on specs {spec_names}. Check that a matching ilL-Rel-Tape Offering record exists and is active.",
        }
    logger.info(f"validate_tape: found offering = {tape_offering.name}")

    # Resolve the correct tape spec from the offering
    tape_spec = next(s for s in all_matching_specs if s.name == tape_offering.tape_spec)
    logger.info(f"validate_tape: resolved tape spec = {tape_spec.name} from offering")

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
    part_number = _build_tape_part_number(sel, tape_spec, tape_offering, manufacturable_length_mm)

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
        if ol.get("numeric_value"):
            ol["label"] = f"{ol['numeric_value']} lm/ft"

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
            "start_feed_directions": feed_directions,
            "end_feed_directions": feed_directions,
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
    logger = frappe.logger("tape_neon_configurator", allow_site=True)
    try:
        sel = json.loads(selections) if isinstance(selections, str) else selections
        segments = json.loads(segments_json) if isinstance(segments_json, str) else segments_json
    except json.JSONDecodeError:
        return {"success": False, "is_valid": False, "error": "Invalid JSON input"}

    logger.info(f"validate_neon_configuration called with selections: {sel}, segments: {segments}")

    messages = []

    # ── Required top-level fields ─────────────────────────────────────
    required = ["cct", "output_level", "mounting", "finish"]
    missing = [f for f in required if not sel.get(f)]
    if missing:
        logger.warning(f"validate_neon: Missing required fields: {missing}")
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

    # ── Find matching tape specs ──────────────────────────────────────
    logger.info(f"validate_neon: looking for tape specs with category=LED Neon, pcb_mounting={sel.get('mounting')}, pcb_finish={sel.get('finish')}")
    all_matching_specs = _find_all_matching_tape_specs(
        product_category="LED Neon",
        pcb_mounting=sel.get("mounting"),
        pcb_finish=sel.get("finish"),
    )
    if not all_matching_specs:
        logger.warning(f"validate_neon: No tape spec found for mounting={sel.get('mounting')}, finish={sel.get('finish')}")
        return {
            "success": False,
            "is_valid": False,
            "error": f"No LED Neon spec found for Mounting='{sel.get('mounting')}' and Finish='{sel.get('finish')}'. Check that a matching ilL-Spec-LED Tape record (product_category=LED Neon) exists.",
        }
    spec_names = [s.name for s in all_matching_specs]
    logger.info(f"validate_neon: found {len(all_matching_specs)} matching tape specs: {spec_names}")

    # ── Find matching tape offering across all matching specs ─────────
    logger.info(f"validate_neon: looking for offering with specs={spec_names}, cct={sel.get('cct')}, output_level={sel.get('output_level')}")
    tape_offering = _find_matching_tape_offering(
        tape_spec_name=spec_names,
        cct=sel.get("cct"),
        output_level=sel.get("output_level"),
    )
    if not tape_offering:
        logger.warning(f"validate_neon: No offering found for specs={spec_names}, cct={sel.get('cct')}, output_level={sel.get('output_level')}")
        return {
            "success": False,
            "is_valid": False,
            "error": f"No neon offering found for CCT='{sel.get('cct')}' and Output Level='{sel.get('output_level')}' on specs {spec_names}. Check that a matching ilL-Rel-Tape Offering record exists and is active.",
        }
    logger.info(f"validate_neon: found offering = {tape_offering.name}")

    # Resolve the correct tape spec from the offering
    tape_spec = next(s for s in all_matching_specs if s.name == tape_offering.tape_spec)
    logger.info(f"validate_neon: resolved tape spec = {tape_spec.name} from offering")

    # ── Process each segment ──────────────────────────────────────────
    is_free_cutting = tape_spec.is_free_cutting
    cut_increment_mm = tape_spec.cut_increment_mm or 0

    computed_segments = []
    total_requested_mm = 0
    total_mfg_mm = 0

    for idx, seg in enumerate(segments):
        seg_num = idx + 1

        # Validate required segment fields
        seg_required = ["ip_rating", "start_feed_direction", "start_lead_length_inches"]
        # end_feed fields only required when end_type is Jumper (not Endcap)
        if seg.get("end_type", "Endcap") != "Endcap":
            seg_required += ["end_feed_direction", "end_feed_length_inches"]
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
            "end_type": seg.get("end_type", "Endcap"),
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
# SPEC-DERIVED TAPE / NEON CONFIGURATOR (no template required)
# ═══════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_tape_neon_spec_init(product_category: str = "LED Tape") -> dict:
    """
    Initialise the LED Tape or LED Neon configurator by deriving options
    directly from ``ilL-Spec-LED Tape`` and ``ilL-Rel-Tape Offering``
    records.  No ``ilL-Tape-Neon-Template`` record is required.

    This is the fallback used on the unified ``/configure`` page when no
    templates are available for the selected product category.

    For LED Tape returns:
      environment_ratings, ccts, output_levels, pcb_mountings, pcb_finishes,
      feed_types

    For LED Neon returns:
      ccts, output_levels, ip_ratings, feed_directions, mounting_methods,
      finishes, endcap_styles
    """
    if product_category not in ("LED Tape", "LED Neon"):
        return {"success": False, "error": f"Invalid product category: {product_category}"}

    is_neon = product_category == "LED Neon"

    tape_specs = frappe.get_all(
        "ilL-Spec-LED Tape",
        filters={"product_category": product_category},
        fields=[
            "name", "item", "led_package", "input_voltage",
            "watts_per_foot", "cut_increment_mm", "is_free_cutting",
            "pcb_mounting", "pcb_finish", "lumens_per_foot",
            "leader_cable_item", "voltage_drop_max_run_length_ft",
        ],
        order_by="name asc",
        ignore_permissions=True,
    )

    if not tape_specs:
        return {"success": False, "error": f"No {product_category} specs found"}

    spec_names = [s.name for s in tape_specs]
    tape_offerings = frappe.get_all(
        "ilL-Rel-Tape Offering",
        filters={"tape_spec": ["in", spec_names], "is_active": 1},
        fields=["name", "tape_spec", "cct", "cri", "sdcm", "led_package", "output_level"],
        ignore_permissions=True,
    )

    # ── Build options ─────────────────────────────────────────────────
    ccts = _collect_attribute_options(
        tape_offerings, "cct", "ilL-Attribute-CCT",
        ["name", "code", "kelvin", "description"],
    )
    output_levels = _collect_attribute_options(
        tape_offerings, "output_level", "ilL-Attribute-Output Level",
        ["name", "value", "sku_code"],
    )
    for ol in output_levels:
        if ol.get("numeric_value"):
            ol["label"] = f"{ol['numeric_value']} lm/ft"

    options: dict[str, Any] = {
        "ccts": ccts,
        "output_levels": output_levels,
    }

    if not is_neon:
        # LED Tape specific
        options["environment_ratings"] = _get_environment_ratings_for_tape_offerings(
            tape_offerings, spec_names,
        )
        pcb_mountings = sorted({s.pcb_mounting for s in tape_specs if s.pcb_mounting})
        options["pcb_mountings"] = [{"value": m, "label": m} for m in pcb_mountings]
        pcb_finishes = sorted({s.pcb_finish for s in tape_specs if s.pcb_finish})
        options["pcb_finishes"] = [{"value": f, "label": f} for f in pcb_finishes]
        options["feed_types"] = _get_feed_types()
        options["feed_directions"] = _get_feed_directions()
    else:
        # LED Neon specific
        options["ip_ratings"] = _get_ip_ratings()
        all_dirs = _get_feed_directions()
        options["feed_directions"] = all_dirs
        options["start_feed_directions"] = all_dirs
        options["end_feed_directions"] = all_dirs
        mountings = sorted({s.pcb_mounting for s in tape_specs if s.pcb_mounting})
        options["mounting_methods"] = [{"value": m, "label": m} for m in mountings]
        finishes = sorted({s.pcb_finish for s in tape_specs if s.pcb_finish})
        options["finishes"] = [{"value": f, "label": f} for f in finishes]

    # Use the first spec for shared metadata
    default_spec = tape_specs[0]

    return {
        "success": True,
        "product_category": product_category,
        "is_neon": is_neon,
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
        "options": options,
        "meta": {
            "cut_increment_mm": default_spec.cut_increment_mm or 0,
            "is_free_cutting": bool(default_spec.is_free_cutting),
            "watts_per_foot": default_spec.watts_per_foot or 0,
            "max_run_length_ft": default_spec.voltage_drop_max_run_length_ft or 0,
            "input_voltage": default_spec.input_voltage,
        },
    }


@frappe.whitelist()
def get_tape_neon_spec_cascading(
    product_category: str = "LED Tape",
    environment_rating: str = None,
    cct: str = None,
    pcb_mounting: str = None,
    pcb_finish: str = None,
) -> dict:
    """
    Return filtered options for the spec-based tape/neon configurator.

    Cascading logic (no template needed):
      - environment_rating → narrows available CCTs & outputs
      - cct → narrows available output_levels
      - pcb_mounting / pcb_finish → narrows tape specs → narrows offerings
    """
    if product_category not in ("LED Tape", "LED Neon"):
        return {"success": False, "error": f"Invalid product category: {product_category}"}

    spec_filters: dict[str, Any] = {"product_category": product_category}
    if pcb_mounting:
        spec_filters["pcb_mounting"] = pcb_mounting
    if pcb_finish:
        spec_filters["pcb_finish"] = pcb_finish

    matching_specs = frappe.get_all(
        "ilL-Spec-LED Tape",
        filters=spec_filters,
        fields=["name"],
        ignore_permissions=True,
    )
    spec_names = [s.name for s in matching_specs]
    if not spec_names:
        return {"success": True, "ccts": [], "output_levels": []}

    offering_filters: dict[str, Any] = {"tape_spec": ["in", spec_names], "is_active": 1}
    tape_offerings = frappe.get_all(
        "ilL-Rel-Tape Offering",
        filters=offering_filters,
        fields=["name", "tape_spec", "cct", "output_level"],
        ignore_permissions=True,
    )

    # Filter by cct if already selected
    filtered_offerings = tape_offerings
    if cct:
        filtered_offerings = [o for o in tape_offerings if o.cct == cct]

    ccts = _collect_attribute_options(
        tape_offerings, "cct", "ilL-Attribute-CCT",
        ["name", "code", "kelvin", "description"],
    )
    output_levels = _collect_attribute_options(
        filtered_offerings, "output_level", "ilL-Attribute-Output Level",
        ["name", "value", "sku_code"],
    )
    for ol in output_levels:
        if ol.get("numeric_value"):
            ol["label"] = f"{ol['numeric_value']} lm/ft"

    return {
        "success": True,
        "ccts": ccts,
        "output_levels": output_levels,
    }


# ═══════════════════════════════════════════════════════════════════════
# TEMPLATE-AWARE TAPE / NEON CONFIGURATOR (unified /configure page)
# ═══════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_tape_neon_template_init(template_code: str) -> dict:
    """
    Initialise the configurator for a specific ilL-Tape-Neon-Template.

    Returns everything the unified /configure page needs to render the
    tape or neon configuration steps:
      - Template metadata (name, category, description, image)
      - Allowed options grouped by option_type (from the template's allowed_options)
      - Resolved tape specs (from the template's allowed_tape_specs)
      - Tape offerings linked to those specs
      - Computed metadata (cut increment, free cutting, watts/ft)

    For LED Tape:
      Environment Rating → CCT → Output Level → PCB Mounting → PCB Finish
      → Feed Type → Lead Length → Tape Length

    For LED Neon:
      CCT → Output Level → Mounting Method → Finish
      Per-segment: IP Rating → Start Feed Direction → Start Lead Length
                   → Fixture Length → End Type → End Params
    """
    if not template_code:
        return {"success": False, "error": "template_code is required"}

    template = frappe.get_all(
        "ilL-Tape-Neon-Template",
        filters={"template_code": template_code, "is_active": 1},
        fields=[
            "name", "template_code", "template_name", "product_category",
            "series", "description", "image", "notes",
            "default_tape_spec", "leader_allowance_mm_per_fixture",
            "base_price_msrp", "price_per_ft_msrp",
            "webflow_product",
        ],
        limit=1,
        ignore_permissions=True,
    )
    if not template:
        return {"success": False, "error": f"Template '{template_code}' not found or inactive"}
    template = template[0]

    product_category = template.product_category  # "LED Tape" or "LED Neon"
    is_neon = product_category == "LED Neon"

    # ── Allowed tape specs ────────────────────────────────────────────
    allowed_spec_rows = frappe.get_all(
        "ilL-Child-Tape-Neon-Allowed-Spec",
        filters={"parent": template.name, "parenttype": "ilL-Tape-Neon-Template"},
        fields=["tape_spec", "is_default", "environment_rating", "notes"],
        order_by="idx asc",
        ignore_permissions=True,
    )
    spec_names = [r.tape_spec for r in allowed_spec_rows if r.tape_spec]
    if not spec_names:
        # Fallback: if no specs are explicitly allowed, use the default_tape_spec
        if template.default_tape_spec:
            spec_names = [template.default_tape_spec]
        else:
            return {"success": False, "error": "No tape specs configured for this template"}

    tape_specs = frappe.get_all(
        "ilL-Spec-LED Tape",
        filters={"name": ["in", spec_names]},
        fields=[
            "name", "item", "led_package", "input_voltage",
            "watts_per_foot", "cut_increment_mm", "is_free_cutting",
            "pcb_mounting", "pcb_finish", "lumens_per_foot",
            "leader_cable_item", "voltage_drop_max_run_length_ft",
        ],
        order_by="name asc",
        ignore_permissions=True,
    )
    if not tape_specs:
        return {"success": False, "error": "No matching tape specs found"}

    # ── Tape offerings for allowed specs ──────────────────────────────
    tape_offerings = frappe.get_all(
        "ilL-Rel-Tape Offering",
        filters={"tape_spec": ["in", spec_names], "is_active": 1},
        fields=["name", "tape_spec", "cct", "cri", "sdcm", "led_package", "output_level"],
        ignore_permissions=True,
    )

    # ── Allowed options from template (grouped by option_type) ────────
    allowed_option_rows = frappe.get_all(
        "ilL-Child-Tape-Neon-Allowed-Option",
        filters={
            "parent": template.name,
            "parenttype": "ilL-Tape-Neon-Template",
            "is_active": 1,
        },
        fields=[
            "option_type", "cct", "output_level", "environment_rating",
            "ip_rating", "feed_direction", "feed_position", "power_feed_type",
            "pcb_mounting", "pcb_finish", "mounting_method", "finish",
            "endcap_style", "is_default", "msrp_adder",
        ],
        order_by="idx asc",
        ignore_permissions=True,
    )

    # Build grouped options dict
    options = _build_template_options(
        allowed_option_rows, tape_offerings, tape_specs, product_category
    )

    # ── Compute shared metadata ───────────────────────────────────────
    # Use the default spec (or first spec) for meta
    default_spec_name = template.default_tape_spec or spec_names[0]
    default_spec = next((s for s in tape_specs if s.name == default_spec_name), tape_specs[0])

    return {
        "success": True,
        "product_category": product_category,
        "is_neon": is_neon,
        "template": {
            "template_code": template.template_code,
            "template_name": template.template_name,
            "product_category": product_category,
            "series": template.series,
            "description": template.description,
            "image": template.image,
            "webflow_product": template.webflow_product,
            "leader_allowance_mm_per_fixture": template.leader_allowance_mm_per_fixture or 0,
        },
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
        "options": options,
        "meta": {
            "cut_increment_mm": default_spec.cut_increment_mm or 0,
            "is_free_cutting": bool(default_spec.is_free_cutting),
            "watts_per_foot": default_spec.watts_per_foot or 0,
            "max_run_length_ft": default_spec.voltage_drop_max_run_length_ft or 0,
            "input_voltage": default_spec.input_voltage,
        },
        "pricing": {
            "base_price_msrp": template.base_price_msrp or 0,
            "price_per_ft_msrp": template.price_per_ft_msrp or 0,
        },
    }


@frappe.whitelist()
def get_tape_neon_template_cascading(
    template_code: str,
    environment_rating: str = None,
    cct: str = None,
    output_level: str = None,
    pcb_mounting: str = None,
    pcb_finish: str = None,
    mounting_method: str = None,
    finish: str = None,
) -> dict:
    """
    Return filtered options for the tape/neon template configurator based
    on prior selections.

    Cascading logic narrows options through two lenses:
      1. Template-level: only options in the template's allowed_options table
      2. Offering-level: only CCT/output combos that exist in tape offerings

    For LED Tape:
      environment_rating → narrows tape specs by environment_rating in
                           allowed_tape_specs → narrows CCT & output
      cct → narrows output_levels
      pcb_mounting + pcb_finish → narrows tape specs → narrows offerings

    For LED Neon:
      cct → narrows output_levels
      (mounting_method + finish are independent selections from template)
    """
    if not template_code:
        return {"success": False, "error": "template_code is required"}

    template = frappe.get_all(
        "ilL-Tape-Neon-Template",
        filters={"template_code": template_code, "is_active": 1},
        fields=["name", "product_category", "default_tape_spec"],
        limit=1,
        ignore_permissions=True,
    )
    if not template:
        return {"success": False, "error": f"Template '{template_code}' not found"}
    template = template[0]

    product_category = template.product_category

    # ── Get allowed specs, optionally filtered by environment ─────────
    spec_filters = {
        "parent": template.name,
        "parenttype": "ilL-Tape-Neon-Template",
    }
    if environment_rating:
        spec_filters["environment_rating"] = environment_rating

    allowed_spec_rows = frappe.get_all(
        "ilL-Child-Tape-Neon-Allowed-Spec",
        filters=spec_filters,
        fields=["tape_spec"],
        ignore_permissions=True,
    )
    spec_names = [r.tape_spec for r in allowed_spec_rows if r.tape_spec]
    if not spec_names:
        # If environment filter returned nothing, fall back to unfiltered
        allowed_spec_rows = frappe.get_all(
            "ilL-Child-Tape-Neon-Allowed-Spec",
            filters={"parent": template.name, "parenttype": "ilL-Tape-Neon-Template"},
            fields=["tape_spec"],
            ignore_permissions=True,
        )
        spec_names = [r.tape_spec for r in allowed_spec_rows if r.tape_spec]
        if not spec_names and template.default_tape_spec:
            spec_names = [template.default_tape_spec]

    if not spec_names:
        return {"success": True, "ccts": [], "output_levels": []}

    # ── Further filter specs by PCB mounting/finish ───────────────────
    spec_db_filters = {"name": ["in", spec_names]}
    if pcb_mounting:
        spec_db_filters["pcb_mounting"] = pcb_mounting
    if pcb_finish:
        spec_db_filters["pcb_finish"] = pcb_finish
    # For neon: mounting_method and finish map to pcb_mounting and pcb_finish
    if mounting_method and not pcb_mounting:
        spec_db_filters["pcb_mounting"] = mounting_method
    if finish and not pcb_finish:
        spec_db_filters["pcb_finish"] = finish

    matching_specs = frappe.get_all(
        "ilL-Spec-LED Tape",
        filters=spec_db_filters,
        fields=["name"],
    )
    filtered_spec_names = [s.name for s in matching_specs] or spec_names

    # ── Get tape offerings for the filtered specs ─────────────────────
    offering_filters = {"tape_spec": ["in", filtered_spec_names], "is_active": 1}
    tape_offerings = frappe.get_all(
        "ilL-Rel-Tape Offering",
        filters=offering_filters,
        fields=["name", "tape_spec", "cct", "output_level"],
    )

    # ── Get template-allowed options for CCT and Output Level ─────────
    allowed_ccts = _get_template_allowed_values(template.name, "CCT", "cct")
    allowed_outputs = _get_template_allowed_values(template.name, "Output Level", "output_level")

    # Intersect with tape offerings
    offering_ccts = {o.cct for o in tape_offerings if o.cct}
    offering_outputs = {o.output_level for o in tape_offerings if o.output_level}

    # If template has explicit allowed options, intersect; otherwise use offerings only
    if allowed_ccts:
        available_ccts = offering_ccts & allowed_ccts
    else:
        available_ccts = offering_ccts

    if allowed_outputs:
        available_outputs = offering_outputs & allowed_outputs
    else:
        available_outputs = offering_outputs

    # If cct is already selected, further narrow output levels
    if cct:
        cct_filtered = [o for o in tape_offerings if o.cct == cct]
        cct_output_set = {o.output_level for o in cct_filtered if o.output_level}
        available_outputs = available_outputs & cct_output_set if available_outputs else cct_output_set

    # Resolve attribute details
    ccts = _resolve_attribute_list("ilL-Attribute-CCT", available_ccts,
                                   ["name", "code", "kelvin", "description"])
    output_levels = _resolve_attribute_list("ilL-Attribute-Output Level", available_outputs,
                                            ["name", "value", "sku_code"])
    for ol in output_levels:
        if ol.get("numeric_value"):
            ol["label"] = f"{ol['numeric_value']} lm/ft"

    return {
        "success": True,
        "ccts": ccts,
        "output_levels": output_levels,
    }


@frappe.whitelist()
def validate_tape_neon_template_config(
    template_code: str,
    selections: str,
    segments_json: str = None,
) -> dict:
    """
    Validate a complete tape/neon template configuration and return computed results.

    This is the template-aware version of validate_tape_configuration /
    validate_neon_configuration.  It ensures all selections are within the
    template's allowed options before delegating to the standard validation
    logic.

    After successful validation, creates (or reuses) an ilL-Configured-Tape-Neon
    record and returns its name.

    Args:
        template_code: The ilL-Tape-Neon-Template template_code
        selections: JSON string of configuration selections
        segments_json: JSON string of neon segments (required for LED Neon)
    """
    if not template_code:
        return {"success": False, "is_valid": False, "error": "template_code is required"}

    logger = frappe.logger("tape_neon_configurator", allow_site=True)
    logger.info(f"validate_tape_neon_template_config called: template_code={template_code}, selections={selections}, segments_json={'(present)' if segments_json else '(none)'}")

    template_list = frappe.get_all(
        "ilL-Tape-Neon-Template",
        filters={"template_code": template_code, "is_active": 1},
        fields=["name", "template_code", "template_name", "product_category",
                "default_tape_spec", "leader_allowance_mm_per_fixture"],
        limit=1,
        ignore_permissions=True,
    )
    if not template_list:
        logger.warning(f"validate_tape_neon_template_config: Template '{template_code}' not found or inactive")
        return {"success": False, "is_valid": False,
                "error": f"Template '{template_code}' not found or inactive"}
    template = template_list[0]
    logger.info(f"validate_tape_neon_template_config: Found template '{template.name}', category={template.product_category}")

    product_category = template.product_category
    is_neon = product_category == "LED Neon"

    # Delegate to the standard validation (which already computes everything)
    if is_neon:
        if not segments_json:
            return {"success": False, "is_valid": False,
                    "error": "segments_json is required for LED Neon"}
        logger.info("validate_tape_neon_template_config: Delegating to validate_neon_configuration")
        result = validate_neon_configuration(selections, segments_json)
    else:
        logger.info("validate_tape_neon_template_config: Delegating to validate_tape_configuration")
        result = validate_tape_configuration(selections)

    if not result.get("is_valid"):
        logger.warning(f"validate_tape_neon_template_config: Validation failed: {result.get('error')}")
        return result

    # ── Augment result with template info ─────────────────────────────
    result["template_code"] = template.template_code
    result["template_name"] = template.template_name

    # ── Create or reuse ilL-Configured-Tape-Neon record ───────────────
    try:
        configured_name = _create_or_reuse_configured_tape_neon(
            template, result, is_neon
        )
        result["configured_tape_neon"] = configured_name
    except Exception as e:
        # Don't fail validation just because record creation failed
        result["configured_tape_neon"] = None
        result.setdefault("messages", []).append({
            "severity": "warning",
            "text": f"Could not create configured record: {str(e)}",
        })

    return result


@frappe.whitelist()
def save_tape_neon_template_to_schedule(
    schedule_name: str,
    line_idx: int = None,
    template_code: str = None,
    configuration_result: str = None,
) -> dict:
    """
    Save a template-based tape/neon configuration to a fixture schedule line.

    This is the template-aware version of save_tape_to_schedule.  In addition
    to storing the standard configuration data, it sets:
      - tape_neon_template  → link to ilL-Tape-Neon-Template
      - configured_tape_neon → link to ilL-Configured-Tape-Neon

    Args:
        schedule_name: ilL-Project-Fixture-Schedule name
        line_idx: existing line index to overwrite, or None for new line
        template_code: ilL-Tape-Neon-Template template_code
        configuration_result: JSON string of validation result
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
    configured_name = result.get("configured_tape_neon")

    # Resolve template name from template_code
    template_name = None
    if template_code:
        template_name = frappe.db.get_value(
            "ilL-Tape-Neon-Template",
            {"template_code": template_code},
            "name",
        )

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

        # Template and configured record references
        if template_name:
            line.tape_neon_template = template_name
        if configured_name:
            line.configured_tape_neon = configured_name

        # Store full configuration for SO conversion
        line.variant_selections = json.dumps({
            "product_category": product_category,
            "template_code": template_code,
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
            "tape_neon_template": template_name,
            "configured_tape_neon": configured_name,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════
# PRIVATE HELPERS – TEMPLATE-AWARE
# ═══════════════════════════════════════════════════════════════════════

def _build_template_options(
    allowed_option_rows: list,
    tape_offerings: list,
    tape_specs: list,
    product_category: str,
) -> dict:
    """
    Group the template's allowed option rows into a front-end-friendly dict.

    Returns:
        {
          "environment_ratings": [...],        # LED Tape only
          "ccts": [...],
          "output_levels": [...],
          "pcb_mountings": [...],              # LED Tape only
          "pcb_finishes": [...],               # LED Tape only
          "feed_types": [...],                 # LED Tape only
          "ip_ratings": [...],                 # LED Neon only
          "feed_directions": [...],            # LED Neon only (all directions)
          "start_feed_directions": [...],      # LED Neon only (start-position subset)
          "end_feed_directions": [...],        # LED Neon only (end-position subset)
          "mounting_methods": [...],           # LED Neon only
          "finishes": [...],                   # LED Neon only
          "endcap_styles": [...],              # LED Neon only
        }
    """
    is_neon = product_category == "LED Neon"

    # Group rows by option_type
    grouped = {}
    for row in allowed_option_rows:
        otype = row.option_type
        if otype:
            grouped.setdefault(otype, []).append(row)

    options = {}

    # ── CCT ───────────────────────────────────────────────────────────
    cct_rows = grouped.get("CCT", [])
    if cct_rows:
        cct_names = [r.cct for r in cct_rows if r.cct]
        options["ccts"] = _resolve_attribute_list(
            "ilL-Attribute-CCT", set(cct_names),
            ["name", "code", "kelvin", "description"],
        )
        # Mark defaults
        default_ccts = {r.cct for r in cct_rows if r.is_default}
        for o in options["ccts"]:
            o["is_default"] = o["value"] in default_ccts
    else:
        # Derive from tape offerings
        options["ccts"] = _collect_attribute_options(
            tape_offerings, "cct", "ilL-Attribute-CCT",
            ["name", "code", "kelvin", "description"],
        )

    # ── Output Level ──────────────────────────────────────────────────
    ol_rows = grouped.get("Output Level", [])
    if ol_rows:
        ol_names = [r.output_level for r in ol_rows if r.output_level]
        options["output_levels"] = _resolve_attribute_list(
            "ilL-Attribute-Output Level", set(ol_names),
            ["name", "value", "sku_code"],
        )
        default_ols = {r.output_level for r in ol_rows if r.is_default}
        for o in options["output_levels"]:
            o["is_default"] = o["value"] in default_ols
            if o.get("numeric_value"):
                o["label"] = f"{o['numeric_value']} lm/ft"
    else:
        options["output_levels"] = _collect_attribute_options(
            tape_offerings, "output_level", "ilL-Attribute-Output Level",
            ["name", "value", "sku_code"],
        )
        for ol in options["output_levels"]:
            if ol.get("numeric_value"):
                ol["label"] = f"{ol['numeric_value']} lm/ft"

    # ── LED Tape specific options ─────────────────────────────────────
    if not is_neon:
        # Environment Rating
        env_rows = grouped.get("Environment Rating", [])
        if env_rows:
            env_names = [r.environment_rating for r in env_rows if r.environment_rating]
            options["environment_ratings"] = _resolve_attribute_list(
                "ilL-Attribute-Environment Rating", set(env_names),
                ["name", "code", "notes"],
            )
            default_envs = {r.environment_rating for r in env_rows if r.is_default}
            for o in options["environment_ratings"]:
                o["is_default"] = o["value"] in default_envs
        else:
            options["environment_ratings"] = _get_environment_ratings_for_tape_offerings(
                tape_offerings, [s.name for s in tape_specs]
            )

        # PCB Mounting
        pcb_mount_rows = grouped.get("PCB Mounting", [])
        if pcb_mount_rows:
            options["pcb_mountings"] = [
                {
                    "value": r.pcb_mounting,
                    "label": r.pcb_mounting,
                    "is_default": bool(r.is_default),
                    "msrp_adder": r.msrp_adder or 0,
                }
                for r in pcb_mount_rows if r.pcb_mounting
            ]
        else:
            pcb_mountings = sorted({s.pcb_mounting for s in tape_specs if s.pcb_mounting})
            options["pcb_mountings"] = [{"value": m, "label": m} for m in pcb_mountings]

        # PCB Finish
        pcb_finish_rows = grouped.get("PCB Finish", [])
        if pcb_finish_rows:
            options["pcb_finishes"] = [
                {
                    "value": r.pcb_finish,
                    "label": r.pcb_finish,
                    "is_default": bool(r.is_default),
                    "msrp_adder": r.msrp_adder or 0,
                }
                for r in pcb_finish_rows if r.pcb_finish
            ]
        else:
            pcb_finishes = sorted({s.pcb_finish for s in tape_specs if s.pcb_finish})
            options["pcb_finishes"] = [{"value": f, "label": f} for f in pcb_finishes]

        # Feed Type
        feed_type_rows = grouped.get("Power Feed Type", [])
        if feed_type_rows:
            options["feed_types"] = [
                {
                    "value": r.power_feed_type,
                    "label": r.power_feed_type,
                    "is_default": bool(r.is_default),
                }
                for r in feed_type_rows if r.power_feed_type
            ]
        else:
            options["feed_types"] = _get_feed_types()

    # ── LED Neon specific options ─────────────────────────────────────
    if is_neon:
        # IP Rating
        ip_rows = grouped.get("IP Rating", [])
        if ip_rows:
            options["ip_ratings"] = [
                {
                    "value": r.ip_rating,
                    "label": r.ip_rating,
                    "is_default": bool(r.is_default),
                }
                for r in ip_rows if r.ip_rating
            ]
        else:
            options["ip_ratings"] = _get_ip_ratings()

        # Feed Direction — split into start and end lists
        fd_rows = grouped.get("Feed Direction", [])
        if fd_rows:
            start_dirs = []
            end_dirs = []
            for r in fd_rows:
                if not r.feed_direction:
                    continue
                entry = {
                    "value": r.feed_direction,
                    "label": r.feed_direction,
                    "is_default": bool(r.is_default),
                }
                position = getattr(r, "feed_position", None) or "Both"
                if position in ("Both", "Start"):
                    start_dirs.append(entry)
                if position in ("Both", "End"):
                    end_dirs.append(entry)
            options["start_feed_directions"] = start_dirs
            options["end_feed_directions"] = end_dirs
            # Keep combined list for backward compatibility
            options["feed_directions"] = [
                {
                    "value": r.feed_direction,
                    "label": r.feed_direction,
                    "is_default": bool(r.is_default),
                }
                for r in fd_rows if r.feed_direction
            ]
        else:
            all_dirs = _get_feed_directions()
            options["feed_directions"] = all_dirs
            options["start_feed_directions"] = all_dirs
            options["end_feed_directions"] = all_dirs

        # Mounting Method
        mm_rows = grouped.get("Mounting Method", [])
        if mm_rows:
            options["mounting_methods"] = [
                {
                    "value": r.mounting_method,
                    "label": r.mounting_method,
                    "is_default": bool(r.is_default),
                    "msrp_adder": r.msrp_adder or 0,
                }
                for r in mm_rows if r.mounting_method
            ]
        else:
            # Derive from tape specs (pcb_mounting represents mounting for neon)
            mountings = sorted({s.pcb_mounting for s in tape_specs if s.pcb_mounting})
            options["mounting_methods"] = [{"value": m, "label": m} for m in mountings]

        # Finish
        fin_rows = grouped.get("Finish", [])
        if fin_rows:
            options["finishes"] = [
                {
                    "value": r.finish,
                    "label": r.finish,
                    "is_default": bool(r.is_default),
                    "msrp_adder": r.msrp_adder or 0,
                }
                for r in fin_rows if r.finish
            ]
        else:
            finishes = sorted({s.pcb_finish for s in tape_specs if s.pcb_finish})
            options["finishes"] = [{"value": f, "label": f} for f in finishes]

        # Endcap Style
        ec_rows = grouped.get("Endcap Style", [])
        if ec_rows:
            options["endcap_styles"] = [
                {
                    "value": r.endcap_style,
                    "label": r.endcap_style,
                    "is_default": bool(r.is_default),
                    "msrp_adder": r.msrp_adder or 0,
                }
                for r in ec_rows if r.endcap_style
            ]

    return options


def _get_template_allowed_values(template_name: str, option_type: str, field_name: str) -> set:
    """Get the set of allowed values for an option_type from a template's allowed_options."""
    rows = frappe.get_all(
        "ilL-Child-Tape-Neon-Allowed-Option",
        filters={
            "parent": template_name,
            "parenttype": "ilL-Tape-Neon-Template",
            "option_type": option_type,
            "is_active": 1,
        },
        fields=[field_name],
        ignore_permissions=True,
    )
    return {getattr(r, field_name, None) or r.get(field_name) for r in rows} - {None, ""}


def _resolve_attribute_list(doctype: str, names: set, fields: list) -> list:
    """Resolve a set of attribute names into detailed option dicts."""
    if not names:
        return []

    result = []
    for name in names:
        data = frappe.db.get_value(doctype, name, fields, as_dict=True)
        if data:
            entry = {"value": data.name, "label": data.name}
            for f in fields:
                if f == "name":
                    continue
                key = "numeric_value" if f == "value" else f
                entry[key] = data.get(f)
            result.append(entry)

    # Sort by kelvin (CCT), numeric_value (Output), or name
    if "kelvin" in fields:
        return sorted(result, key=lambda x: x.get("kelvin") or 0)
    if "value" in fields:
        return sorted(result, key=lambda x: x.get("numeric_value") or 0)
    return sorted(result, key=lambda x: x.get("label", ""))


def _create_or_reuse_configured_tape_neon(template, validation_result, is_neon: bool) -> str:
    """
    Create an ilL-Configured-Tape-Neon record (or reuse an existing one
    with the same config_hash).

    Args:
        template: Template dict (from frappe.get_all)
        validation_result: The validated configuration result dict
        is_neon: True if LED Neon, False if LED Tape

    Returns:
        The name of the ilL-Configured-Tape-Neon record
    """
    import hashlib

    sel = validation_result.get("selections", {})
    computed = validation_result.get("computed", {})
    resolved = validation_result.get("resolved_items", {})

    # Build a deterministic hash of the configuration
    hash_parts = [
        template.template_code,
        template.product_category,
        resolved.get("tape_spec", ""),
        resolved.get("tape_offering", ""),
        sel.get("cct", ""),
        sel.get("output_level", ""),
    ]

    if is_neon:
        hash_parts.extend([
            sel.get("mounting", ""),
            sel.get("finish", ""),
        ])
        # Include segment details in hash
        segments = computed.get("segments", [])
        for seg in segments:
            hash_parts.extend([
                str(seg.get("segment_index", "")),
                seg.get("ip_rating", ""),
                seg.get("start_feed_direction", ""),
                str(seg.get("start_lead_length_inches", "")),
                str(seg.get("manufacturable_length_mm", "")),
                seg.get("end_feed_direction", ""),
                str(seg.get("end_feed_length_inches", "")),
            ])
    else:
        hash_parts.extend([
            sel.get("environment_rating", ""),
            sel.get("pcb_mounting", ""),
            sel.get("pcb_finish", ""),
            sel.get("feed_type", ""),
            str(sel.get("lead_length_inches", "")),
            str(computed.get("manufacturable_length_mm", "")),
        ])

    config_hash = hashlib.sha256("|".join(hash_parts).encode()).hexdigest()[:32]

    # Check for existing record with same hash
    existing = frappe.db.get_value(
        "ilL-Configured-Tape-Neon",
        {"config_hash": config_hash},
        "name",
    )
    if existing:
        return existing

    # Create new configured record
    doc_data = {
        "doctype": "ilL-Configured-Tape-Neon",
        "config_hash": config_hash,
        "part_number": validation_result.get("part_number", ""),
        "product_category": template.product_category,
        "tape_neon_template": template.name,
        "engine_version": "2.0",
        "tape_spec": resolved.get("tape_spec"),
        "tape_offering": resolved.get("tape_offering"),
        "cct": sel.get("cct"),
        "output_level": sel.get("output_level"),
        "build_description": validation_result.get("build_description", ""),
    }

    if is_neon:
        doc_data["mounting_method"] = sel.get("mounting")
        doc_data["finish"] = sel.get("finish")
        doc_data["total_segments"] = computed.get("segment_count", 0)
        doc_data["assembly_mode"] = "ASSEMBLED"
        doc_data["requested_length_mm"] = computed.get("total_requested_length_mm", 0)
        doc_data["manufacturable_length_mm"] = computed.get("total_manufacturable_length_mm", 0)
        doc_data["total_watts"] = computed.get("total_watts", 0)

        # Add segments
        segments = computed.get("segments", [])
        doc_data["segments"] = []
        for seg in segments:
            doc_data["segments"].append({
                "segment_index": seg.get("segment_index"),
                "ip_rating": seg.get("ip_rating"),
                "requested_length_mm": seg.get("requested_length_mm", 0),
                "manufacturable_length_mm": seg.get("manufacturable_length_mm", 0),
                "difference_mm": seg.get("difference_mm", 0),
                "start_feed_direction": seg.get("start_feed_direction"),
                "start_lead_length_inches": seg.get("start_lead_length_inches", 0),
                "end_feed_direction": seg.get("end_feed_direction"),
                "end_cable_length_inches": seg.get("end_feed_length_inches", 0),
                "end_type": seg.get("end_type", "Endcap"),
            })
    else:
        doc_data["environment_rating"] = sel.get("environment_rating")
        doc_data["pcb_mounting"] = sel.get("pcb_mounting")
        doc_data["pcb_finish"] = sel.get("pcb_finish")
        doc_data["feed_type"] = sel.get("feed_type")
        doc_data["lead_length_inches"] = sel.get("lead_length_inches")
        doc_data["requested_length_mm"] = computed.get("requested_length_mm", 0)
        doc_data["manufacturable_length_mm"] = computed.get("manufacturable_length_mm", 0)
        doc_data["difference_mm"] = computed.get("difference_mm", 0)
        doc_data["total_watts"] = computed.get("total_watts", 0)
        doc_data["assembly_mode"] = "ASSEMBLED"
        doc_data["total_segments"] = 1

    doc_data["cut_increment_mm"] = computed.get("cut_increment_mm", 0)
    doc_data["is_free_cutting"] = computed.get("is_free_cutting", False)
    doc_data["watts_per_foot"] = computed.get("watts_per_foot", 0)

    # Resolved items
    doc_data["tape_item"] = resolved.get("tape_item")
    doc_data["leader_cable_item"] = resolved.get("leader_cable_item")

    # Store pricing snapshot as child table rows
    import datetime
    doc_data["pricing_snapshot"] = [{
        "msrp_unit": computed.get("total_price_msrp", 0),
        "tier_unit": computed.get("total_price_tier", 0),
        "adder_breakdown_json": json.dumps({
            "computed": computed,
            "resolved_items": resolved,
            "selections": sel,
        }),
        "timestamp": datetime.datetime.now().isoformat(),
    }]

    doc = frappe.get_doc(doc_data)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return doc.name


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
    """Find an ilL-Spec-LED Tape matching the given filters (returns first match)."""
    specs = _find_all_matching_tape_specs(product_category, pcb_mounting, pcb_finish)
    return specs[0] if specs else None


def _find_all_matching_tape_specs(
    product_category: str,
    pcb_mounting: str = None,
    pcb_finish: str = None,
) -> list:
    """Find all ilL-Spec-LED Tape records matching the given filters."""
    logger = frappe.logger("tape_neon_configurator", allow_site=True)
    filters: dict[str, Any] = {"product_category": product_category}
    if pcb_mounting:
        filters["pcb_mounting"] = pcb_mounting
    if pcb_finish:
        filters["pcb_finish"] = pcb_finish

    logger.info(f"_find_all_matching_tape_specs: filters={filters}")

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
    )
    if not specs:
        # Log all available specs for debugging
        all_specs = frappe.get_all(
            "ilL-Spec-LED Tape",
            filters={"product_category": product_category},
            fields=["name", "pcb_mounting", "pcb_finish"],
        )
        logger.warning(
            f"_find_all_matching_tape_specs: No match for {filters}. "
            f"Available specs for {product_category}: {all_specs}"
        )
    return specs


def _find_matching_tape_offering(
    tape_spec_name,
    cct: str = None,
    output_level: str = None,
) -> Optional[Any]:
    """Find an ilL-Rel-Tape Offering matching the tape spec(s), CCT and output.

    Args:
        tape_spec_name: A single spec name (str) or list of spec names.
        cct: CCT attribute name to filter on.
        output_level: Output level attribute name to filter on.
    """
    logger = frappe.logger("tape_neon_configurator", allow_site=True)
    # Accept either a single name or a list of names
    if isinstance(tape_spec_name, list):
        spec_filter = ["in", tape_spec_name]
    else:
        spec_filter = tape_spec_name
    filters: dict[str, Any] = {"tape_spec": spec_filter, "is_active": 1}
    if cct:
        filters["cct"] = cct
    if output_level:
        filters["output_level"] = output_level

    logger.info(f"_find_matching_tape_offering: filters={filters}")

    offerings = frappe.get_all(
        "ilL-Rel-Tape Offering",
        filters=filters,
        fields=["name", "tape_spec", "cct", "cri", "sdcm", "led_package", "output_level"],
        limit=1,
    )
    if not offerings:
        # Log all available offerings for debugging
        all_offerings = frappe.get_all(
            "ilL-Rel-Tape Offering",
            filters={"tape_spec": spec_filter, "is_active": 1},
            fields=["name", "cct", "output_level", "tape_spec"],
        )
        logger.warning(
            f"_find_matching_tape_offering: No match for {filters}. "
            f"Available offerings for {tape_spec_name}: {all_offerings}"
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
        ignore_permissions=True,
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
            ignore_permissions=True,
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
                if f == "name":
                    continue
                # Avoid overwriting 'value' (the option ID) with the
                # doctype's own 'value' field (e.g. Output Level numeric).
                key = "numeric_value" if f == "value" else f
                entry[key] = data.get(f)
            result.append(entry)

    # Sort by kelvin (CCT), numeric_value (Output), or name
    if "kelvin" in fields:
        return sorted(result, key=lambda x: x.get("kelvin") or 0)
    if "value" in fields:
        return sorted(result, key=lambda x: x.get("numeric_value") or 0)
    return sorted(result, key=lambda x: x.get("label", ""))


def _get_feed_types() -> list:
    """Get power feed type options."""
    if frappe.db.exists("DocType", "ilL-Attribute-Power Feed Type"):
        types = frappe.get_all(
            "ilL-Attribute-Power Feed Type",
            filters={"is_active": 1} if frappe.db.has_column("ilL-Attribute-Power Feed Type", "is_active") else {},
            fields=["name", "code", "label"],
            order_by="name",
            ignore_permissions=True,
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
            ignore_permissions=True,
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
            ignore_permissions=True,
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


def _get_feed_direction_code(direction: str) -> str:
    """Get the short code for a feed direction value."""
    if not direction:
        return "X"
    if frappe.db.exists("DocType", "ilL-Attribute-Feed-Direction"):
        code = frappe.db.get_value(
            "ilL-Attribute-Feed-Direction",
            direction,
            "code",
        )
        if code:
            return code
    # Fallback mapping
    direction_codes = {"End": "E", "Back": "B", "Left": "L", "Right": "R", "Endcap": "CAP"}
    return direction_codes.get(direction, "X")


def _build_tape_part_number(sel: dict, tape_spec, tape_offering, manufacturable_length_mm: float = 0) -> str:
    """
    Build LED Tape part number.

    Format: {tape_spec_name}-{length_inches}-{feed_type_code}{leader_cable_ft}-C

    Uses the tape spec ID as the base, then appends the total manufacturable
    length in inches, followed by the feed direction code with leader cable
    length in feet, and "C" for endcapped (tape is always single-segment/endcapped).
    """
    parts = [tape_spec.name]

    # Total length in inches (manufacturable)
    if manufacturable_length_mm:
        length_in = manufacturable_length_mm / MM_PER_INCH
    else:
        tape_len_mm = _parse_tape_length(sel)
        length_in = (tape_len_mm / MM_PER_INCH) if tape_len_mm else 0
    # Format: remove .0 if whole number, otherwise 1 decimal
    if length_in == int(length_in):
        length_str = str(int(length_in))
    else:
        length_str = f"{length_in:.1f}"
    parts.append(length_str)

    # Feed direction code + leader cable length in feet
    feed_type_code = ""
    feed_type = sel.get("feed_type", "")
    if feed_type:
        feed_type_code = _get_code("ilL-Attribute-Power Feed Type", feed_type)

    lead_length_in = float(sel.get("lead_length_inches", 0))
    cable_length_ft = lead_length_in / INCHES_PER_FOOT
    if cable_length_ft == int(cable_length_ft):
        cable_length_str = str(int(cable_length_ft))
    else:
        cable_length_str = f"{cable_length_ft:.1f}"

    parts.append(f"{feed_type_code}{cable_length_str}")

    # Endcapped
    parts.append("C")

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

    Single-segment (endcapped):
        {tape_spec_name}-{total_length_inches}-{feed_dir_code}{leader_cable_ft}-C

    Multi-segment (jumpered):
        {tape_spec_name}-{total_length_inches}-J({hash})

    Uses the tape spec ID as the base, then appends the total manufacturable
    length in inches.  For single-segment configs the feed direction code and
    leader cable length in feet are added followed by "C" for endcapped.  For
    multi-segment (jumpered) configs, "-J({hash})" is appended where the hash
    differentiates different segment layouts with the same total length.
    """
    import hashlib

    parts = [tape_spec.name]

    # Total manufacturable length in inches (sum of all segments)
    total_mfg_in = sum(s.get("manufacturable_length_in", 0) for s in segments)
    if total_mfg_in == int(total_mfg_in):
        length_str = str(int(total_mfg_in))
    else:
        length_str = f"{total_mfg_in:.1f}"
    parts.append(length_str)

    if len(segments) == 1:
        # Single segment → endcapped: {feed_dir_code}{leader_ft}-C
        seg = segments[0]
        feed_dir = seg.get("start_feed_direction", "")
        feed_dir_code = ""
        if feed_dir:
            feed_dir_code = _get_feed_direction_code(feed_dir)

        lead_in = float(seg.get("start_lead_length_inches", 0))
        cable_ft = lead_in / INCHES_PER_FOOT
        if cable_ft == int(cable_ft):
            cable_str = str(int(cable_ft))
        else:
            cable_str = f"{cable_ft:.1f}"

        parts.append(f"{feed_dir_code}{cable_str}")
        parts.append("C")
    else:
        # Multi-segment → jumpered: J({hash})
        seg_data = []
        for seg in segments:
            seg_data.append({
                "segment_index": seg.get("segment_index"),
                "manufacturable_length_in": seg.get("manufacturable_length_in"),
                "ip_rating": seg.get("ip_rating", ""),
                "start_feed_direction": seg.get("start_feed_direction", ""),
                "start_lead_length_inches": seg.get("start_lead_length_inches", 0),
                "end_feed_direction": seg.get("end_feed_direction", ""),
                "end_feed_length_inches": seg.get("end_feed_length_inches", 0),
            })
        config_str = json.dumps(seg_data, sort_keys=True)
        seg_hash = hashlib.sha256(config_str.encode()).hexdigest()[:4].upper()
        parts.append(f"J({seg_hash})")

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
