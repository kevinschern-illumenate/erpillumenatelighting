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
  Environment → CCT → Output → Feed Type → Lead Length (in)
  → Tape Length (in / ft / ft+in) → Calculate ▸ Part Number + Mfg Length
  → Optional Mounting Accessory selection (post-config)

LED Neon flow (multi-segment):
  CCT → Output → Finish
  Per-segment: IP type → Start Feed Direction → Start Lead Length
               → Fixture Length → End Feed Direction → End Feed (jumper) Length
  → Optional Mounting Accessory selection (post-config)

When added to a schedule and converted to a Sales Order, LED Tape produces
two SO lines: leader cable (qty = lead length) and tape item (qty = mfg length).
LED Neon produces similar lines per segment.  If a mounting accessory is
selected, an additional SO line is added for the accessory.
"""

import json
import math
import traceback
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
MAX_WATTS_PER_RUN = 85.0  # Power supply max watts per single tape run
MM_PER_METER = 1000.0


# ═══════════════════════════════════════════════════════════════════════
# PRICING HELPERS
# ═══════════════════════════════════════════════════════════════════════

def _compute_tape_neon_pricing(tape_item, leader_cable_item, length_mm, lead_length_inches=0):
	"""
	Compute MSRP pricing for a tape/neon product using Standard Selling Item Prices.

	Looks up the tape item's Item Price, determines its stock_uom to convert
	*length_mm* to the correct pricing unit, and multiplies by the rate.
	Optionally adds leader cable pricing.

	Args:
		tape_item: Item code for the tape/neon product
		leader_cable_item: Item code for the leader cable (may be None)
		length_mm: Total manufacturable length in mm
		lead_length_inches: Total leader cable length in inches to price.
			The caller is responsible for including all leader cable length
			(e.g., if there are multiple runs, pass the combined lead length).

	Returns:
		dict with ``total_price_msrp`` (float). Components with no Item Price
		in the Standard Selling price list are silently treated as zero-cost.
	"""
	total_msrp = 0.0

	if tape_item and length_mm:
		tape_price = frappe.db.get_value(
			"Item Price",
			{"item_code": tape_item, "price_list": "Standard Selling", "selling": 1},
			"price_list_rate",
		)
		if tape_price:
			tape_rate = float(tape_price)
			# Determine the item's stock UOM to convert length correctly
			stock_uom = frappe.db.get_value("Item", tape_item, "stock_uom") or "Foot"
			uom_lower = stock_uom.lower()

			if uom_lower in ("foot", "ft"):
				qty = float(length_mm) / MM_PER_FOOT
			elif uom_lower in ("meter", "metre", "m"):
				qty = float(length_mm) / MM_PER_METER
			elif uom_lower in ("inch", "in"):
				qty = float(length_mm) / MM_PER_INCH
			else:
				# Default to Foot for unknown UOM
				qty = float(length_mm) / MM_PER_FOOT

			total_msrp += tape_rate * qty

	if leader_cable_item and lead_length_inches:
		leader_price = frappe.db.get_value(
			"Item Price",
			{"item_code": leader_cable_item, "price_list": "Standard Selling", "selling": 1},
			"price_list_rate",
		)
		if leader_price:
			total_msrp += float(leader_price) * float(lead_length_inches)

	return {"total_price_msrp": round(total_msrp, 2)}


def _compute_template_tape_neon_pricing(
	template_name, selections, length_mm, lead_length_inches=0, is_neon=False
):
	"""
	Compute MSRP pricing for a tape/neon product using template-based pricing.

	Formula: total = base_price_msrp + (price_per_ft_msrp × length_ft) + option_adders + leader_cable_pricing

	Args:
		template_name: Name of the ilL-Tape-Neon-Template record
		selections: dict of configuration selections (cct, output_level, etc.)
		length_mm: Total manufacturable length in mm
		lead_length_inches: Total leader cable length in inches to price
		is_neon: True if LED Neon, False if LED Tape

	Returns:
		dict with ``total_price_msrp`` (float) and ``adder_breakdown`` (list of dicts)
	"""
	if not template_name:
		return {"total_price_msrp": 0, "adder_breakdown": []}

	# --- Fetch template pricing fields ---
	template_pricing = frappe.db.get_value(
		"ilL-Tape-Neon-Template",
		template_name,
		["base_price_msrp", "price_per_ft_msrp"],
		as_dict=True,
	)
	if not template_pricing:
		return {"total_price_msrp": 0, "adder_breakdown": []}

	base_price = float(template_pricing.get("base_price_msrp") or 0)
	price_per_ft = float(template_pricing.get("price_per_ft_msrp") or 0)

	# --- Length-based pricing ---
	length_ft = float(length_mm) / MM_PER_FOOT if length_mm else 0.0
	length_adder = length_ft * price_per_ft

	adder_breakdown = [
		{"component": "base", "description": "Base price", "amount": round(base_price, 2)},
		{
			"component": "length",
			"description": f"Length adder ({length_mm:.0f}mm = {length_ft:.2f}ft × ${price_per_ft:.2f}/ft)",
			"amount": round(length_adder, 2),
		},
	]

	# --- Option Adders ---
	if is_neon:
		option_map = {
			"CCT": ("cct", selections.get("cct")),
			"Output Level": ("output_level", selections.get("output_level")),
			"Finish": ("finish", selections.get("finish")),
		}
	else:
		option_map = {
			"Environment Rating": ("environment_rating", selections.get("environment_rating")),
			"CCT": ("cct", selections.get("cct")),
			"Output Level": ("output_level", selections.get("output_level")),
			"Power Feed Type": ("power_feed_type", selections.get("feed_type")),
		}

	total_option_adders = 0.0

	for option_type, (field_name, selected_value) in option_map.items():
		if not selected_value:
			continue

		rows = frappe.get_all(
			"ilL-Child-Tape-Neon-Allowed-Option",
			filters={
				"parent": template_name,
				"parenttype": "ilL-Tape-Neon-Template",
				"option_type": option_type,
				field_name: selected_value,
				"is_active": 1,
			},
			fields=["msrp_adder"],
			limit=1,
			ignore_permissions=True,
		)

		option_adder = float(rows[0].msrp_adder or 0) if rows else 0.0
		total_option_adders += option_adder
		if option_adder != 0:
			adder_breakdown.append({
				"component": field_name,
				"description": f"{option_type} ({selected_value})",
				"amount": round(option_adder, 2),
			})

	# --- Leader cable pricing (same Item Price lookup as existing) ---
	leader_cable_msrp = 0.0
	if lead_length_inches:
		# Look up leader cable item from resolved items or template
		leader_cable_item = selections.get("_leader_cable_item")
		if leader_cable_item:
			leader_price = frappe.db.get_value(
				"Item Price",
				{"item_code": leader_cable_item, "price_list": "Standard Selling", "selling": 1},
				"price_list_rate",
			)
			if leader_price:
				leader_cable_msrp = float(leader_price) * float(lead_length_inches)
				adder_breakdown.append({
					"component": "leader_cable",
					"description": f"Leader cable ({lead_length_inches}in × ${float(leader_price):.2f}/in)",
					"amount": round(leader_cable_msrp, 2),
				})

	total_msrp = base_price + length_adder + total_option_adders + leader_cable_msrp

	return {
		"total_price_msrp": round(total_msrp, 2),
		"adder_breakdown": adder_breakdown,
	}


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

    pcb_mounting and pcb_finish are accepted for backward compatibility but are
    no longer used by the configurator UI (mounting moved to post-config accessory step).
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
    _skip_record_creation: bool = False,
    parent_configured_tape_neon: str | None = None,
    include_power_supply: bool = True,
    dimming_protocol_code: str | None = None,
    variant_origin: str | None = None,
    tape_neon_template: str | None = None,
    override_max_run_ft: float | None = None,
) -> dict:
    """
    Validate a complete LED Tape configuration and compute manufacturable length.

    Selections dict keys:
      - environment_rating     (str)
      - cct                    (str)
      - output_level           (str)
      - feed_direction         (str) – always "End Feed" for tape
      - feed_type              (str) – power feed type code
      - lead_length_inches     (float)
      - tape_length_value      (float) – the numeric value
      - tape_length_unit       (str) – "in", "ft", or "ft_in"
      - tape_length_feet       (float) – only when unit is ft_in
      - tape_length_inches     (float) – only when unit is ft_in

    Optional post-config mounting accessory keys:
      - mounting_accessory_item       (str) – accessory item code
      - mounting_accessory_qty        (int)
      - mounting_accessory_unit_msrp  (float)
      - mounting_accessory_total_msrp (float)

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

    # Normalise stringy booleans (Frappe sends HTTP query params as strings)
    if isinstance(_skip_record_creation, str):
        _skip_record_creation = _skip_record_creation.lower() not in ("0", "false", "no", "")
    if isinstance(include_power_supply, str):
        include_power_supply = include_power_supply.lower() not in ("0", "false", "no", "")

    # Normalise the optional max run length override (Frappe sends strings).
    # Fall back to a value embedded in the selections payload when present.
    if override_max_run_ft in (None, ""):
        override_max_run_ft = sel.get("override_max_run_ft")
    if override_max_run_ft in (None, ""):
        override_max_run_ft = None
    else:
        try:
            override_max_run_ft = float(override_max_run_ft)
            if override_max_run_ft <= 0:
                override_max_run_ft = None
        except (ValueError, TypeError):
            override_max_run_ft = None

    logger.info(f"validate_tape_configuration called with selections: {sel}")

    messages = []

    # ── Required fields ───────────────────────────────────────────────
    # Only CCT and Output Level are required to build a part number.
    # Length, feed_type, and lead_length_inches are now optional — the
    # part number gracefully falls back to an "xx" length placeholder and
    # omits the feed segment entirely when the user has not provided them.
    required_str = ["cct", "output_level"]
    missing = [f for f in required_str if not sel.get(f)]
    if missing:
        logger.warning(f"validate_tape: Missing required fields: {missing}")
        return {
            "success": False,
            "is_valid": False,
            "error": f"Missing required fields: {', '.join(missing)}",
            "missing_fields": missing,
        }

    # ── Parse requested tape length (optional) ────────────────────────
    requested_length_mm = _parse_tape_length(sel)
    logger.info(f"validate_tape: parsed tape length = {requested_length_mm} mm")
    if requested_length_mm is None or requested_length_mm <= 0:
        # Length is optional; treat missing/zero as "not specified".
        requested_length_mm = 0

    # Lead length is optional; default to 0 (no leader cable).
    try:
        lead_length_inches = float(sel.get("lead_length_inches") or 0)
    except (TypeError, ValueError):
        lead_length_inches = 0.0
    if lead_length_inches < 0:
        lead_length_inches = 0.0

    # ── Find matching tape offering ───────────────────────────────────
    # Mounting fields (pcb_mounting/pcb_finish) removed from selections.
    # Search all LED Tape specs directly.
    logger.info("validate_tape: looking for tape specs with category=LED Tape (no mounting filter)")
    all_matching_specs = _find_all_matching_tape_specs(
        product_category="LED Tape",
    )
    spec_names = [s.name for s in all_matching_specs]
    logger.info(f"validate_tape: found {len(all_matching_specs)} matching tape specs: {spec_names}")

    tape_offering = None
    if spec_names:
        tape_offering = _find_matching_tape_offering(
            tape_spec_name=spec_names,
            cct=sel.get("cct"),
            output_level=sel.get("output_level"),
        )

    # Fallback: if no offering found with direct specs, search ALL LED Tape specs.
    if not tape_offering:
        logger.info("validate_tape: no offering found – falling back to all LED Tape specs")
        all_tape_specs = _find_all_matching_tape_specs(product_category="LED Tape")
        all_spec_names = [s.name for s in all_tape_specs]
        tape_offering = _find_matching_tape_offering(
            tape_spec_name=all_spec_names,
            cct=sel.get("cct"),
            output_level=sel.get("output_level"),
        )
        if tape_offering:
            all_matching_specs = all_tape_specs
            logger.info(f"validate_tape: found offering via all-specs fallback: {tape_offering.name}")

    if not tape_offering:
        logger.warning(f"validate_tape: No offering found for cct={sel.get('cct')}, output_level={sel.get('output_level')}")
        return {
            "success": False,
            "is_valid": False,
            "error": (
                f"No tape offering found for CCT='{sel.get('cct')}' and Output Level='{sel.get('output_level')}'. "
                "Check that a matching ilL-Rel-Tape Offering record exists and is active."
            ),
        }
    logger.info(f"validate_tape: found offering = {tape_offering.name}")

    # Resolve the correct tape spec from the offering
    tape_spec = next(s for s in all_matching_specs if s.name == tape_offering.tape_spec)
    logger.info(f"validate_tape: resolved tape spec = {tape_spec.name} from offering")

    # ── Compute manufacturable length ─────────────────────────────────
    is_free_cutting = tape_spec.is_free_cutting
    cut_increment_mm = tape_spec.cut_increment_mm or 0

    if requested_length_mm <= 0:
        # Length not specified — skip cut-increment math and emit zero.
        manufacturable_length_mm = 0
    elif is_free_cutting or cut_increment_mm <= 0:
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

    # ── Run splitting ─────────────────────────────────────────────────
    watts_per_ft = float(tape_spec.watts_per_foot or 0)
    voltage_drop_max_run_ft = float(tape_spec.voltage_drop_max_run_length_ft or 0)

    run_split = _compute_run_split(
        tape_length_mm=manufacturable_length_mm,
        watts_per_ft=watts_per_ft,
        voltage_drop_max_run_ft=voltage_drop_max_run_ft,
        cut_increment_mm=cut_increment_mm if not is_free_cutting else 0,
        is_free_cutting=bool(is_free_cutting),
        override_max_run_ft=override_max_run_ft,
    )

    if run_split.get("override_max_run_ft_active"):
        messages.append({
            "severity": "warning",
            "text": (
                f"⚠ Max run length overridden to {override_max_run_ft:g} ft. "
                "Verify compliance with applicable electrical codes."
            ),
            "field": "override_max_run_ft",
        })

    if run_split["runs_count"] > 1:
        messages.append({
            "severity": "info",
            "text": (
                f"Requested length exceeds the maximum run of "
                f"{run_split['max_run_ft_effective']:.1f} ft. "
                f"Splitting into {run_split['runs_count']} equal segments."
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

    return_result = {
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
            "watts_per_foot": watts_per_ft,
            "total_watts": round((mfg_length_ft) * watts_per_ft, 2),
            # Run splitting outputs
            "runs_count": run_split["runs_count"],
            "runs": run_split["runs"],
            "leader_qty": run_split["runs_count"],
            "max_run_ft_by_watts": run_split["max_run_ft_by_watts"],
            "max_run_ft_by_voltage_drop": run_split["max_run_ft_by_voltage_drop"],
            "max_run_ft_effective": run_split["max_run_ft_effective"],
            "override_max_run_ft_active": run_split.get("override_max_run_ft_active", False),
            "override_max_run_ft": override_max_run_ft if run_split.get("override_max_run_ft_active") else None,
        },
        "resolved_items": {
            "tape_spec": tape_spec.name,
            "tape_offering": tape_offering.name,
            "tape_item": tape_item,
            "leader_cable_item": leader_cable_item,
        },
        "selections": sel,
    }

    # ── Create or reuse ilL-Configured-Tape-Neon record ───────────────
    if not _skip_record_creation:
        try:
            template_for_record = None
            if tape_neon_template:
                template_for_record = frappe.get_doc(
                    "ilL-Tape-Neon-Template", tape_neon_template
                )
            configured_name = _create_or_reuse_configured_tape_neon(
                template_for_record, return_result, is_neon=False,
                parent_configured_tape_neon=parent_configured_tape_neon,
                variant_origin=variant_origin,
            )
            return_result["configured_tape_neon"] = configured_name
        except Exception as e:
            # Validation continues even if record creation fails
            return_result["configured_tape_neon"] = None
            return_result.setdefault("messages", []).append({
                "severity": "warning",
                "text": f"Could not create configured record: {str(e)}",
            })

    # ── Surface driver plan when an enabling template is supplied ─────
    if tape_neon_template and include_power_supply:
        try:
            driver_plan, dp_messages = select_driver_plan_for_tape_neon(
                tape_neon_template,
                runs_count=return_result["computed"].get("runs_count", 1),
                total_watts=return_result["computed"].get("total_watts", 0),
                tape_offering_doc=tape_offering,
                dimming_protocol_code=dimming_protocol_code,
            )
            return_result["resolved_items"]["driver_plan"] = driver_plan
            if dp_messages:
                return_result.setdefault("messages", []).extend(dp_messages)
        except Exception as e:
            return_result.setdefault("messages", []).append({
                "severity": "warning",
                "text": f"Driver plan selection failed: {str(e)}",
            })

    return return_result


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

    # Neon-specific: PCB finish options
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
    _skip_record_creation: bool = False,
    parent_configured_tape_neon: str | None = None,
    include_power_supply: bool = True,
    dimming_protocol_code: str | None = None,
    variant_origin: str | None = None,
    tape_neon_template: str | None = None,
    override_max_run_ft: float | None = None,
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

    # Normalise stringy booleans
    if isinstance(_skip_record_creation, str):
        _skip_record_creation = _skip_record_creation.lower() not in ("0", "false", "no", "")
    if isinstance(include_power_supply, str):
        include_power_supply = include_power_supply.lower() not in ("0", "false", "no", "")

    # Normalise the optional max run length override (Frappe sends strings).
    # Fall back to a value embedded in the selections payload when present.
    if override_max_run_ft in (None, ""):
        override_max_run_ft = sel.get("override_max_run_ft")
    if override_max_run_ft in (None, ""):
        override_max_run_ft = None
    else:
        try:
            override_max_run_ft = float(override_max_run_ft)
            if override_max_run_ft <= 0:
                override_max_run_ft = None
        except (ValueError, TypeError):
            override_max_run_ft = None

    logger.info(f"validate_neon_configuration called with selections: {sel}, segments: {segments}")

    messages = []

    # ── Required top-level fields ─────────────────────────────────────
    required = ["cct", "output_level"]
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

    # ── Find matching tape offering ───────────────────────────────────
    # Search priority:
    #   1. Template's allowed tape specs + finish filter  (when template provided)
    #   2. Template's allowed tape specs, no finish filter (when template provided)
    #   3. All LED Neon specs + finish filter (global fallback)
    #   4. All LED Neon specs, no finish filter (global fallback, no finish)
    # Using the template's allowed specs first ensures we find offerings even
    # when the linked tape spec's product_category differs from "LED Neon".

    tape_offering = None
    all_matching_specs = []

    # ── Step 1 & 2: Template-scoped search ───────────────────────────
    if tape_neon_template:
        logger.info(f"validate_neon: fetching allowed tape specs from template '{tape_neon_template}'")
        _tpl_spec_rows = frappe.get_all(
            "ilL-Child-Tape-Neon-Allowed-Spec",
            filters={"parent": tape_neon_template, "parenttype": "ilL-Tape-Neon-Template"},
            fields=["tape_spec"],
            order_by="idx asc",
            ignore_permissions=True,
        )
        _tpl_spec_names = [r.tape_spec for r in _tpl_spec_rows if r.tape_spec]
        if _tpl_spec_names:
            _tpl_specs = frappe.get_all(
                "ilL-Spec-LED Tape",
                filters={"name": ["in", _tpl_spec_names]},
                fields=[
                    "name", "item", "led_package", "input_voltage",
                    "watts_per_foot", "cut_increment_mm", "is_free_cutting",
                    "pcb_mounting", "pcb_finish", "lumens_per_foot",
                    "leader_cable_item", "voltage_drop_max_run_length_ft",
                ],
                ignore_permissions=True,
            )
            _tpl_fetched_names = [s.name for s in _tpl_specs]
            logger.info(
                f"validate_neon: template has {len(_tpl_specs)} allowed tape specs: {_tpl_fetched_names}"
            )

            # Step 1: template specs + finish filter
            _finish = sel.get("finish")
            _finish_filtered = (
                [s for s in _tpl_specs if s.pcb_finish == _finish]
                if _finish else _tpl_specs
            )
            if _finish_filtered:
                tape_offering = _find_matching_tape_offering(
                    tape_spec_name=[s.name for s in _finish_filtered],
                    cct=sel.get("cct"),
                    output_level=sel.get("output_level"),
                )
                if tape_offering:
                    all_matching_specs = _finish_filtered
                    logger.info(
                        f"validate_neon: found offering via template specs (finish={_finish}): {tape_offering.name}"
                    )

            # Step 2: all template specs, no finish filter
            if not tape_offering and _finish:
                tape_offering = _find_matching_tape_offering(
                    tape_spec_name=_tpl_fetched_names,
                    cct=sel.get("cct"),
                    output_level=sel.get("output_level"),
                )
                if tape_offering:
                    all_matching_specs = _tpl_specs
                    logger.info(
                        f"validate_neon: found offering via template specs (no finish filter): {tape_offering.name}"
                    )

    # ── Step 3: Global LED Neon specs + finish filter ─────────────────
    if not tape_offering:
        logger.info(
            f"validate_neon: looking for tape specs with category=LED Neon, pcb_finish={sel.get('finish')}"
        )
        all_matching_specs = _find_all_matching_tape_specs(
            product_category="LED Neon",
            pcb_finish=sel.get("finish"),
        )
        spec_names = [s.name for s in all_matching_specs]
        logger.info(
            f"validate_neon: found {len(all_matching_specs)} matching tape specs with finish filter: {spec_names}"
        )
        if spec_names:
            tape_offering = _find_matching_tape_offering(
                tape_spec_name=spec_names,
                cct=sel.get("cct"),
                output_level=sel.get("output_level"),
            )

    # ── Step 4: All LED Neon specs, no finish filter ──────────────────
    if not tape_offering:
        logger.info("validate_neon: no offering found with finish filter – falling back to all LED Neon specs")
        all_neon_specs = _find_all_matching_tape_specs(product_category="LED Neon")
        all_spec_names = [s.name for s in all_neon_specs]
        tape_offering = _find_matching_tape_offering(
            tape_spec_name=all_spec_names,
            cct=sel.get("cct"),
            output_level=sel.get("output_level"),
        )
        if tape_offering:
            all_matching_specs = all_neon_specs
            logger.info(f"validate_neon: found offering via all LED Neon specs fallback: {tape_offering.name}")

    if not tape_offering:
        logger.warning(f"validate_neon: No offering found for cct={sel.get('cct')}, output_level={sel.get('output_level')}")
        return {
            "success": False,
            "is_valid": False,
            "error": (
                f"No neon offering found for CCT='{sel.get('cct')}' and Output Level='{sel.get('output_level')}'. "
                "Check that a matching ilL-Rel-Tape Offering record exists and is active."
            ),
        }
    logger.info(f"validate_neon: found offering = {tape_offering.name}")

    # Resolve the correct tape spec from the offering
    tape_spec = next(s for s in all_matching_specs if s.name == tape_offering.tape_spec)
    logger.info(f"validate_neon: resolved tape spec = {tape_spec.name} from offering")

    # ── Process each segment ──────────────────────────────────────────
    is_free_cutting = tape_spec.is_free_cutting
    cut_increment_mm = tape_spec.cut_increment_mm or 0
    watts_per_ft = float(tape_spec.watts_per_foot or 0)
    voltage_drop_max_run_ft = float(tape_spec.voltage_drop_max_run_length_ft or 0)

    computed_segments = []
    total_requested_mm = 0
    total_mfg_mm = 0

    for idx, seg in enumerate(segments):
        seg_num = idx + 1

        # Validate required segment fields.
        # Only ip_rating is required per segment.  Feed start/end direction,
        # lead lengths, and fixture length are all optional — the part number
        # falls back to "xx" for length and omits the feed segment when those
        # fields are not supplied.
        seg_required = ["ip_rating"]
        seg_missing = [f for f in seg_required if not seg.get(f) and seg.get(f) != 0]
        if seg_missing:
            return {
                "success": False,
                "is_valid": False,
                "error": f"Segment {seg_num}: Missing fields: {', '.join(seg_missing)}",
            }

        # Parse fixture length (optional)
        fixture_length_mm = _parse_neon_fixture_length(seg)
        if fixture_length_mm is None or fixture_length_mm <= 0:
            fixture_length_mm = 0

        # Compute manufacturable length
        if fixture_length_mm <= 0:
            mfg_length_mm = 0
        elif is_free_cutting or cut_increment_mm <= 0:
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

        # Run-split this segment if it exceeds max run length
        seg_run_split = _compute_run_split(
            tape_length_mm=mfg_length_mm,
            watts_per_ft=watts_per_ft,
            voltage_drop_max_run_ft=voltage_drop_max_run_ft,
            cut_increment_mm=cut_increment_mm if not is_free_cutting else 0,
            is_free_cutting=bool(is_free_cutting),
            override_max_run_ft=override_max_run_ft,
        )

        if seg_run_split["runs_count"] > 1:
            messages.append({
                "severity": "info",
                "text": (
                    f"Segment {seg_num}: Length exceeds the maximum run of "
                    f"{seg_run_split['max_run_ft_effective']:.1f} ft. "
                    f"Splitting into {seg_run_split['runs_count']} equal segments."
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
            # Run splitting for this segment
            "runs_count": seg_run_split["runs_count"],
            "runs": seg_run_split["runs"],
            "leader_qty": seg_run_split["runs_count"],
        })

    # ── Aggregate run-split data across all segments ──────────────────
    total_runs_count = sum(s["runs_count"] for s in computed_segments)
    all_runs = []
    run_offset = 0
    for seg in computed_segments:
        for run in seg["runs"]:
            run_offset += 1
            all_runs.append({
                "run_index": run_offset,
                "segment_index": seg["segment_index"],
                "run_len_mm": run["run_len_mm"],
                "run_len_in": run["run_len_in"],
                "run_len_ft": run["run_len_ft"],
                "run_watts": run["run_watts"],
            })

    # Compute overall run-split metadata (for top-level display)
    overall_run_split = _compute_run_split(
        tape_length_mm=total_mfg_mm,
        watts_per_ft=watts_per_ft,
        voltage_drop_max_run_ft=voltage_drop_max_run_ft,
        cut_increment_mm=cut_increment_mm if not is_free_cutting else 0,
        is_free_cutting=bool(is_free_cutting),
        override_max_run_ft=override_max_run_ft,
    )

    if overall_run_split.get("override_max_run_ft_active"):
        messages.append({
            "severity": "warning",
            "text": (
                f"⚠ Max run length overridden to {override_max_run_ft:g} ft. "
                "Verify compliance with applicable electrical codes."
            ),
            "field": "override_max_run_ft",
        })

    # ── Build part number & description ───────────────────────────────
    part_number = _build_neon_part_number(sel, tape_spec, tape_offering, computed_segments)
    build_description = _build_neon_description(sel, tape_spec, tape_offering, computed_segments)

    # ── Resolved items ────────────────────────────────────────────────
    tape_item = tape_spec.item
    leader_cable_item = tape_spec.leader_cable_item

    mfg_length_ft = total_mfg_mm / MM_PER_FOOT

    return_result = {
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
            "watts_per_foot": watts_per_ft,
            "total_watts": round(mfg_length_ft * watts_per_ft, 2),
            # Run splitting outputs (aggregate across all segments)
            "runs_count": total_runs_count,
            "runs": all_runs,
            "leader_qty": total_runs_count,
            "max_run_ft_by_watts": overall_run_split["max_run_ft_by_watts"],
            "max_run_ft_by_voltage_drop": overall_run_split["max_run_ft_by_voltage_drop"],
            "max_run_ft_effective": overall_run_split["max_run_ft_effective"],
            "override_max_run_ft_active": overall_run_split.get("override_max_run_ft_active", False),
            "override_max_run_ft": override_max_run_ft if overall_run_split.get("override_max_run_ft_active") else None,
        },
        "resolved_items": {
            "tape_spec": tape_spec.name,
            "tape_offering": tape_offering.name,
            "tape_item": tape_item,
            "leader_cable_item": leader_cable_item,
        },
        "selections": sel,
    }

    # ── Create or reuse ilL-Configured-Tape-Neon record ───────────────
    if not _skip_record_creation:
        try:
            # Resolve the tape_neon_template name to a doc when provided so
            # _create_or_reuse_configured_tape_neon can populate the
            # required tape_neon_template link field on the configured record.
            template_for_record = None
            if tape_neon_template:
                template_for_record = frappe.get_doc(
                    "ilL-Tape-Neon-Template", tape_neon_template
                )
            configured_name = _create_or_reuse_configured_tape_neon(
                template_for_record, return_result, is_neon=True,
                parent_configured_tape_neon=parent_configured_tape_neon,
                variant_origin=variant_origin,
            )
            return_result["configured_tape_neon"] = configured_name
        except Exception as e:
            # Validation continues even if record creation fails
            return_result["configured_tape_neon"] = None
            return_result.setdefault("messages", []).append({
                "severity": "warning",
                "text": f"Could not create configured record: {str(e)}",
            })

    # ── Surface driver plan when an enabling template is supplied ─────
    if tape_neon_template and include_power_supply:
        try:
            driver_plan, dp_messages = select_driver_plan_for_tape_neon(
                tape_neon_template,
                runs_count=return_result["computed"].get("total_runs", len(segments)),
                total_watts=return_result["computed"].get("total_watts", 0),
                tape_offering_doc=tape_offering,
                dimming_protocol_code=dimming_protocol_code,
            )
            return_result["resolved_items"]["driver_plan"] = driver_plan
            if dp_messages:
                return_result.setdefault("messages", []).extend(dp_messages)
        except Exception as e:
            return_result.setdefault("messages", []).append({
                "severity": "warning",
                "text": f"Driver plan selection failed: {str(e)}",
            })

    return return_result


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

    # Compute pricing from Standard Selling Item Prices
    tape_item = resolved.get("tape_item")
    leader_cable_item = resolved.get("leader_cable_item")
    lead_length_inches = computed.get("lead_length_inches", 0)
    pricing = _compute_tape_neon_pricing(tape_item, leader_cable_item, mfg_length_mm, lead_length_inches)
    computed["total_price_msrp"] = pricing.get("total_price_msrp", 0)

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

        # Persist configured tape/neon link if the validation created a record
        if result.get("configured_tape_neon"):
            line.configured_tape_neon = result.get("configured_tape_neon")

        # Persist tape_neon_template link from selections or resolved data
        if not getattr(line, "tape_neon_template", None):
            tn_template = result.get("tape_neon_template") or result.get("selections", {}).get("tape_neon_template")
            if tn_template:
                line.tape_neon_template = tn_template

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

    # ── Mounting accessory SO line (Phase 7b) ─────────────────────────
    mounting_item = config_data.get("selections", {}).get("mounting_accessory_item")
    mounting_qty = int(config_data.get("selections", {}).get("mounting_accessory_qty", 0))
    mounting_unit_msrp = float(config_data.get("selections", {}).get("mounting_accessory_unit_msrp", 0))
    if mounting_item and mounting_qty > 0:
        so_item = so.append("items", {})
        so_item.item_code = mounting_item
        so_item.qty = mounting_qty
        if mounting_unit_msrp > 0:
            so_item.rate = mounting_unit_msrp
        so_item.description = (
            f"Mounting Accessory for {part_number} – "
            f"{mounting_qty} pcs"
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
      environment_ratings, ccts, output_levels, feed_types

    For LED Neon returns:
      ccts, output_levels, ip_ratings, feed_directions, finishes,
      endcap_styles
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
        options["feed_types"] = _get_feed_types()
        options["feed_directions"] = _get_feed_directions()
        pcb_fin_set = sorted({s.pcb_finish for s in tape_specs if s.pcb_finish})
        options["pcb_finishes"] = [{"value": f, "label": f} for f in pcb_fin_set]
    else:
        # LED Neon specific
        options["ip_ratings"] = _get_ip_ratings()
        all_dirs = _get_feed_directions()
        options["feed_directions"] = all_dirs
        options["start_feed_directions"] = all_dirs
        options["end_feed_directions"] = all_dirs
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

    pcb_mounting / pcb_finish are accepted for API compatibility but are NOT used
    to narrow the spec/offering lookup here.  Restricting by those attributes
    would incorrectly exclude tape types (e.g. Tunable White) whose specs carry
    different or no pcb_mounting / pcb_finish values.  The physical spec is
    resolved at validation time from the offering itself.
    """
    if product_category not in ("LED Tape", "LED Neon"):
        return {"success": False, "error": f"Invalid product category: {product_category}"}

    matching_specs = frappe.get_all(
        "ilL-Spec-LED Tape",
        filters={"product_category": product_category},
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
        result = validate_neon_configuration(selections, segments_json, _skip_record_creation=True)
    else:
        logger.info("validate_tape_neon_template_config: Delegating to validate_tape_configuration")
        # Extract include_power_supply from the selections dict so it can be
        # forwarded as a proper parameter (validate_tape_configuration treats
        # it as a keyword argument, not a selections key).
        sel_dict = json.loads(selections) if isinstance(selections, str) else dict(selections or {})
        _include_ps = sel_dict.pop("include_power_supply", True)
        if isinstance(_include_ps, str):
            _include_ps = _include_ps.lower() not in ("0", "false", "no", "")
        result = validate_tape_configuration(
            sel_dict,
            _skip_record_creation=True,
            tape_neon_template=template.name,
            include_power_supply=bool(_include_ps),
        )

    if not result.get("is_valid"):
        logger.warning(f"validate_tape_neon_template_config: Validation failed: {result.get('error')}")
        return result

    # ── Augment result with template info ─────────────────────────────
    result["template_code"] = template.template_code
    result["template_name"] = template.template_name

    # ── Create or reuse ilL-Configured-Tape-Neon record ───────────────
    # Capture message_log length so we can roll back any messages added
    # by frappe.throw() inside doc.insert() if an exception occurs.
    _msg_log_len = len(getattr(frappe.local, "message_log", []))
    try:
        # Mute messages so that frappe.throw() inside doc.insert() does not
        # pollute the response message_log with an error popup on the client.
        frappe.flags.mute_messages = True
        try:
            configured_name = _create_or_reuse_configured_tape_neon(
                template, result, is_neon
            )
        finally:
            frappe.flags.mute_messages = False
        result["configured_tape_neon"] = configured_name
    except Exception as e:
        # Don't fail validation just because record creation failed
        result["configured_tape_neon"] = None
        # Truncate message_log back to pre-call length to remove any
        # entries added by frappe.throw() before the mute flag took effect.
        if hasattr(frappe.local, "message_log"):
            frappe.local.message_log = frappe.local.message_log[:_msg_log_len]
        logger.warning(
            f"Could not create configured record for template "
            f"'{template.name}' ({template.template_code}): {e}\n"
            f"Template dict: {dict(template)}\n"
            f"Traceback:\n{traceback.format_exc()}"
        )
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

    # Compute template-based pricing (mirrors save_tape_to_schedule pattern)
    is_neon = product_category == "LED Neon"
    if template_name and not computed.get("total_price_msrp"):
        lead_length_inches = computed.get("lead_length_inches", 0)
        pricing_sel = dict(result.get("selections", {}))
        pricing_sel["_leader_cable_item"] = resolved.get("leader_cable_item")
        pricing = _compute_template_tape_neon_pricing(
            template_name, pricing_sel, mfg_length_mm, lead_length_inches, is_neon
        )
        computed["total_price_msrp"] = pricing.get("total_price_msrp", 0)

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
            "pricing": {"total_price_msrp": computed.get("total_price_msrp", 0)},
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
        # Mark defaults and attach msrp_adder from allowed option rows
        default_ccts = {r.cct for r in cct_rows if r.is_default}
        cct_adder_map = {r.cct: (r.msrp_adder or 0) for r in cct_rows if r.cct}
        for o in options["ccts"]:
            o["is_default"] = o["value"] in default_ccts
            o["msrp_adder"] = cct_adder_map.get(o["value"], 0)
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
        ol_adder_map = {r.output_level: (r.msrp_adder or 0) for r in ol_rows if r.output_level}
        for o in options["output_levels"]:
            o["is_default"] = o["value"] in default_ols
            o["msrp_adder"] = ol_adder_map.get(o["value"], 0)
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
            env_adder_map = {r.environment_rating: (r.msrp_adder or 0) for r in env_rows if r.environment_rating}
            for o in options["environment_ratings"]:
                o["is_default"] = o["value"] in default_envs
                o["msrp_adder"] = env_adder_map.get(o["value"], 0)
        else:
            options["environment_ratings"] = _get_environment_ratings_for_tape_offerings(
                tape_offerings, [s.name for s in tape_specs]
            )

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

        # PCB Finish
        pcb_fin_rows = grouped.get("PCB Finish", [])
        if pcb_fin_rows:
            options["pcb_finishes"] = [
                {
                    "value": r.pcb_finish,
                    "label": r.pcb_finish,
                    "is_default": bool(r.is_default),
                    "msrp_adder": r.msrp_adder or 0,
                }
                for r in pcb_fin_rows if r.pcb_finish
            ]
        else:
            pcb_fin_set = sorted({s.pcb_finish for s in tape_specs if s.pcb_finish})
            options["pcb_finishes"] = [{"value": f, "label": f} for f in pcb_fin_set]

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


def _resolve_root_configured_tape_neon(name: str | None) -> str | None:
    """Walk the ``parent_configured_tape_neon`` chain (max 16 hops) to return
    the root ancestor.  Defends against accidental cycles.
    """
    if not name:
        return None
    current = name
    visited: set[str] = set()
    for _ in range(16):
        if current in visited:
            break
        visited.add(current)
        parent = frappe.db.get_value(
            "ilL-Configured-Tape-Neon", current, "parent_configured_tape_neon"
        )
        if not parent:
            return current
        current = parent
    return current


@frappe.whitelist()
def select_driver_plan_for_tape_neon(
    tape_neon_template: str,
    runs_count: int,
    total_watts: float,
    tape_offering_doc=None,
    dimming_protocol_code: str | None = None,
) -> tuple:
    """Select a driver plan for a configured tape/neon record.

    Mirrors the linear-fixture engine's ``_select_driver_plan`` shape so
    callers (Quotation tool, Sales Order tool, Builder CLI) can render a
    consistent driver-line selection UI.

    Driver Eligibility filters:
        - ``template_type = 'ilL-Tape-Neon-Template'``
        - ``fixture_template = tape_neon_template``
        - ``is_allowed = 1`` and ``is_active = 1``
        - drivers whose ``output_protocol`` is compatible with the tape's
          ``input_protocol`` and whose voltage matches the tape voltage.
        - if ``dimming_protocol_code`` is given, drivers must support it.

    Selection policy:
        - Lowest ``cost_msrp`` first; ties broken by smallest ``max_wattage``
          that still meets ``total_watts / runs_count``.

    Returns ``(driver_plan_dict, messages_list)`` where the dict has keys
    ``status`` (one of ``selected``/``not_required``/``no_eligible_drivers``/
    ``no_matching_drivers``/``no_suitable_driver``/``none``), ``drivers``
    (list of ``{driver_item, qty, max_wattage, cost_msrp}``), and
    ``per_run_watts``.
    """
    messages: list[dict] = []

    if not tape_neon_template:
        return {"status": "none", "drivers": [], "per_run_watts": 0.0}, messages

    if not total_watts or total_watts <= 0 or not runs_count or runs_count <= 0:
        return {"status": "not_required", "drivers": [], "per_run_watts": 0.0}, messages

    eligibility_rows = frappe.get_all(
        "ilL-Rel-Driver-Eligibility",
        filters={
            "template_type": "ilL-Tape-Neon-Template",
            "fixture_template": tape_neon_template,
            "is_allowed": 1,
            "is_active": 1,
        },
        fields=["driver"],
    )
    if not eligibility_rows:
        messages.append({
            "severity": "warning",
            "text": f"No eligible drivers configured for template {tape_neon_template}.",
        })
        return {"status": "no_eligible_drivers", "drivers": [], "per_run_watts": 0.0}, messages

    eligible_driver_codes = [row.driver for row in eligibility_rows if row.driver]

    # Resolve the tape's input protocol & voltage from the tape offering doc
    tape_voltage = None
    tape_input_protocol = None
    if tape_offering_doc is not None:
        tape_voltage = getattr(tape_offering_doc, "voltage", None)
        tape_input_protocol = getattr(tape_offering_doc, "input_protocol", None)

    driver_filters = {"name": ["in", eligible_driver_codes]}
    drivers = frappe.get_all(
        "ilL-Spec-Driver",
        filters=driver_filters,
        fields=[
            "name",
            "output_protocol",
            "voltage",
            "max_wattage",
            "cost_msrp",
            "supported_dimming_protocols",
            "item",
        ],
    )

    if tape_voltage:
        drivers = [d for d in drivers if not d.get("voltage") or str(d.get("voltage")) == str(tape_voltage)]
    if tape_input_protocol:
        drivers = [d for d in drivers if not d.get("output_protocol") or d.get("output_protocol") == tape_input_protocol]
    if dimming_protocol_code:
        drivers = [
            d for d in drivers
            if not d.get("supported_dimming_protocols")
            or dimming_protocol_code in (d.get("supported_dimming_protocols") or "")
        ]

    if not drivers:
        return {"status": "no_matching_drivers", "drivers": [], "per_run_watts": 0.0}, messages

    per_run_watts = float(total_watts) / float(runs_count)
    suitable = [d for d in drivers if (d.get("max_wattage") or 0) >= per_run_watts]
    if not suitable:
        return {
            "status": "no_suitable_driver",
            "drivers": [],
            "per_run_watts": per_run_watts,
        }, messages

    suitable.sort(key=lambda d: (float(d.get("cost_msrp") or 0), float(d.get("max_wattage") or 0)))
    chosen = suitable[0]

    return {
        "status": "selected",
        "drivers": [{
            "driver_code": chosen.get("name"),
            "driver_item": chosen.get("item"),
            "qty": int(runs_count),
            "max_wattage": float(chosen.get("max_wattage") or 0),
            "cost_msrp": float(chosen.get("cost_msrp") or 0),
            "output_protocol": chosen.get("output_protocol"),
            "voltage": chosen.get("voltage"),
        }],
        "per_run_watts": per_run_watts,
    }, messages


def _create_or_reuse_configured_tape_neon(
    template,
    validation_result,
    is_neon: bool,
    parent_configured_tape_neon: str | None = None,
    variant_origin: str | None = None,
) -> str:
    """
    Create an ilL-Configured-Tape-Neon record (or reuse an existing one
    with the same config_hash).

    Args:
        template: Template dict (from frappe.get_all), or None for non-template path
        validation_result: The validated configuration result dict
        is_neon: True if LED Neon, False if LED Tape

    Returns:
        The name of the ilL-Configured-Tape-Neon record
    """
    import hashlib

    sel = validation_result.get("selections", {})
    computed = validation_result.get("computed", {})
    resolved = validation_result.get("resolved_items", {})

    product_category = validation_result.get("product_category", "LED Neon" if is_neon else "LED Tape")
    template_code = template.template_code if template else "__direct__"

    # Build a deterministic hash of the configuration
    hash_parts = [
        template_code,
        product_category,
        resolved.get("tape_spec", ""),
        resolved.get("tape_offering", ""),
        sel.get("cct", ""),
        sel.get("output_level", ""),
    ]

    # Include any active max run length override so configurations that differ
    # only by the override resolve to distinct records.
    if computed.get("override_max_run_ft_active") and computed.get("override_max_run_ft") is not None:
        hash_parts.append(f"override:{float(computed.get('override_max_run_ft'))}")

    if is_neon:
        hash_parts.extend([
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
            sel.get("feed_type", ""),
            str(sel.get("lead_length_inches", "")),
            str(computed.get("manufacturable_length_mm", "")),
        ])

    config_hash = hashlib.sha256("|".join(hash_parts).encode()).hexdigest()[:32]

    # Variant branch: caller is creating a modified-of-existing record.  Skip
    # the existing-by-hash reuse so historical orders pinned to the parent
    # stay untouched, append a -V(XXXX) suffix to the part number, and link
    # to the root ancestor.
    is_variant = bool(parent_configured_tape_neon)
    variant_suffix = ""
    root_parent = None
    if is_variant:
        variant_suffix = hashlib.sha256("|".join(hash_parts).encode()).hexdigest()[:4].upper()
        root_parent = _resolve_root_configured_tape_neon(parent_configured_tape_neon)
    else:
        # Check for existing record with same hash
        existing = frappe.db.get_value(
            "ilL-Configured-Tape-Neon",
            {"config_hash": config_hash},
            "name",
        )
        if existing:
            return existing

    # Create new configured record
    base_part_number = validation_result.get("part_number", "")
    final_part_number = (
        f"{base_part_number}-V({variant_suffix})" if is_variant and variant_suffix else base_part_number
    )
    doc_data = {
        "doctype": "ilL-Configured-Tape-Neon",
        "config_hash": config_hash,
        "part_number": final_part_number,
        "product_category": product_category,
        "tape_neon_template": template.name if template else None,
        "engine_version": "2.0",
        "tape_spec": resolved.get("tape_spec"),
        "tape_offering": resolved.get("tape_offering"),
        "cct": sel.get("cct"),
        "output_level": sel.get("output_level"),
        "build_description": validation_result.get("build_description", ""),
    }
    if is_variant:
        doc_data["parent_configured_tape_neon"] = root_parent
        doc_data["variant_suffix"] = variant_suffix
        if variant_origin:
            doc_data["variant_origin"] = variant_origin
    elif variant_origin:
        doc_data["variant_origin"] = variant_origin

    if is_neon:
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

    # Persist max run length override when supplied
    if computed.get("override_max_run_ft_active") and computed.get("override_max_run_ft") is not None:
        doc_data["override_max_run_ft_enabled"] = 1
        doc_data["override_max_run_ft"] = float(computed.get("override_max_run_ft"))
    else:
        doc_data["override_max_run_ft_enabled"] = 0
        doc_data["override_max_run_ft"] = 0

    # Resolved items
    doc_data["tape_item"] = resolved.get("tape_item")
    doc_data["leader_cable_item"] = resolved.get("leader_cable_item")

    # Compute pricing using template-based pricing
    if not computed.get("total_price_msrp") and template:
        if is_neon:
            mfg_length_mm = computed.get("total_manufacturable_length_mm", 0)
        else:
            mfg_length_mm = computed.get("manufacturable_length_mm", 0)
        lead_length_inches = computed.get("lead_length_inches", 0)
        # Pass leader cable item through selections for the pricing function
        pricing_sel = dict(sel)
        pricing_sel["_leader_cable_item"] = resolved.get("leader_cable_item")
        pricing = _compute_template_tape_neon_pricing(
            template.name, pricing_sel, mfg_length_mm, lead_length_inches, is_neon
        )
        computed["total_price_msrp"] = pricing.get("total_price_msrp", 0)
    else:
        pricing = {"adder_breakdown": []}

    # Store pricing snapshot as child table rows
    import datetime
    doc_data["pricing_snapshot"] = [{
        "msrp_unit": computed.get("total_price_msrp", 0),
        "tier_unit": computed.get("total_price_tier", 0),
        "adder_breakdown_json": json.dumps(pricing.get("adder_breakdown", [])),
        "timestamp": datetime.datetime.now().isoformat(),
    }]

    # ── Mounting accessory fields (Phase 5c) ──────────────────────────
    if sel.get("mounting_accessory_item"):
        doc_data["include_mounting_accessory"] = 1
        doc_data["mounting_accessory_item"] = sel["mounting_accessory_item"]
        doc_data["mounting_accessory_qty"] = int(sel.get("mounting_accessory_qty", 0))
        doc_data["mounting_accessory_unit_msrp"] = float(sel.get("mounting_accessory_unit_msrp", 0))
        doc_data["mounting_accessory_total_msrp"] = float(sel.get("mounting_accessory_total_msrp", 0))

    logger = frappe.logger("tape_neon_configurator", allow_site=True)
    logger.info(
        f"_create_or_reuse_configured_tape_neon: About to insert doc. "
        f"tape_neon_template={doc_data.get('tape_neon_template')!r}, "
        f"template.name={template.name if template else None!r}, "
        f"config_hash={config_hash}"
    )

    doc = frappe.get_doc(doc_data)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return doc.name


# ═══════════════════════════════════════════════════════════════════════
# PRIVATE HELPERS
# ═══════════════════════════════════════════════════════════════════════


def _compute_run_split(
    tape_length_mm: float,
    watts_per_ft: float,
    voltage_drop_max_run_ft: float,
    cut_increment_mm: float,
    is_free_cutting: bool = False,
    override_max_run_ft: float | None = None,
) -> dict:
    """
    Compute run-splitting plan for a tape length that may exceed the max run.

    Mirrors the linear fixture engine's Task 3.3 logic but distributes length
    as equally as possible across runs (instead of full-runs-then-remainder).

    Max run is the lesser of:
      - Power supply limit: MAX_WATTS_PER_RUN / watts_per_ft  (converted to mm)
      - Voltage drop limit: voltage_drop_max_run_length_ft     (converted to mm)

    When the tape length exceeds max run, the tape is split into
    ceil(tape_length / max_run) equal-length segments.  Each segment is
    snapped to the tape's cut increment so the total still equals the
    manufacturable tape length.

    Returns dict with:
        runs_count, runs[], max_run_ft_by_watts, max_run_ft_by_voltage_drop,
        max_run_ft_effective
    """
    # -- Compute max run limits (same formulas as configurator_engine) --
    if watts_per_ft > 0:
        max_run_ft_by_watts = MAX_WATTS_PER_RUN / watts_per_ft
    else:
        max_run_ft_by_watts = float("inf")

    max_run_ft_by_voltage_drop_val = None
    if voltage_drop_max_run_ft and voltage_drop_max_run_ft > 0:
        max_run_ft_by_voltage_drop_val = voltage_drop_max_run_ft
        max_run_ft_effective = min(max_run_ft_by_watts, voltage_drop_max_run_ft)
    else:
        max_run_ft_effective = max_run_ft_by_watts

    # User override: replaces both the watts and voltage-drop limits entirely.
    override_max_run_ft_active = False
    if override_max_run_ft is not None and override_max_run_ft > 0:
        max_run_ft_effective = float(override_max_run_ft)
        override_max_run_ft_active = True

    max_run_mm = (
        max_run_ft_effective * MM_PER_FOOT
        if max_run_ft_effective != float("inf")
        else float("inf")
    )

    # -- Determine how many runs are needed --
    if tape_length_mm <= 0:
        return {
            "runs_count": 0,
            "runs": [],
            "max_run_ft_by_watts": (
                round(max_run_ft_by_watts, 2)
                if max_run_ft_by_watts != float("inf") else None
            ),
            "max_run_ft_by_voltage_drop": (
                round(max_run_ft_by_voltage_drop_val, 2)
                if max_run_ft_by_voltage_drop_val else None
            ),
            "max_run_ft_effective": (
                round(max_run_ft_effective, 2)
                if max_run_ft_effective != float("inf") else None
            ),
            "override_max_run_ft_active": override_max_run_ft_active,
        }

    if max_run_mm != float("inf") and max_run_mm > 0 and tape_length_mm > max_run_mm:
        runs_count = math.ceil(tape_length_mm / max_run_mm)
    else:
        runs_count = 1

    # -- Distribute tape equally across runs, snapping to cut increment --
    runs = []
    if runs_count == 1:
        run_watts = (tape_length_mm / MM_PER_FOOT) * watts_per_ft
        runs.append({
            "run_index": 1,
            "run_len_mm": round(tape_length_mm, 1),
            "run_len_in": round(tape_length_mm / MM_PER_INCH, 2),
            "run_len_ft": round(tape_length_mm / MM_PER_FOOT, 2),
            "run_watts": round(run_watts, 2),
        })
    else:
        effective_increment = cut_increment_mm if (not is_free_cutting and cut_increment_mm > 0) else 0

        if effective_increment > 0:
            # Snap each run to cut increment, distribute remainder evenly
            total_increments = round(tape_length_mm / effective_increment)
            base_increments_per_run = total_increments // runs_count
            extra_increment_runs = total_increments % runs_count
            # First `extra_increment_runs` runs get one extra increment
            for i in range(runs_count):
                if i < extra_increment_runs:
                    run_len = (base_increments_per_run + 1) * effective_increment
                else:
                    run_len = base_increments_per_run * effective_increment
                run_watts = (run_len / MM_PER_FOOT) * watts_per_ft
                runs.append({
                    "run_index": i + 1,
                    "run_len_mm": round(run_len, 1),
                    "run_len_in": round(run_len / MM_PER_INCH, 2),
                    "run_len_ft": round(run_len / MM_PER_FOOT, 2),
                    "run_watts": round(run_watts, 2),
                })
        else:
            # Free-cutting: simple equal division (no snap needed)
            run_len = tape_length_mm / runs_count
            for i in range(runs_count):
                run_watts = (run_len / MM_PER_FOOT) * watts_per_ft
                runs.append({
                    "run_index": i + 1,
                    "run_len_mm": round(run_len, 1),
                    "run_len_in": round(run_len / MM_PER_INCH, 2),
                    "run_len_ft": round(run_len / MM_PER_FOOT, 2),
                    "run_watts": round(run_watts, 2),
                })

    return {
        "runs_count": runs_count,
        "runs": runs,
        "max_run_ft_by_watts": (
            round(max_run_ft_by_watts, 2)
            if max_run_ft_by_watts != float("inf") else None
        ),
        "max_run_ft_by_voltage_drop": (
            round(max_run_ft_by_voltage_drop_val, 2)
            if max_run_ft_by_voltage_drop_val else None
        ),
        "max_run_ft_effective": (
            round(max_run_ft_effective, 2)
            if max_run_ft_effective != float("inf") else None
        ),
        "override_max_run_ft_active": override_max_run_ft_active,
    }


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

    Format: {tape_spec_name}-{length_inches_or_xx}[-{feed_type_code}{leader_cable_ft}]-C

    Uses the tape spec ID as the base, then appends the total manufacturable
    length in inches (or "xx" when the length is not yet specified), followed
    by an optional feed segment (feed-type code + leader cable length in feet)
    and "C" for endcapped (tape is always single-segment/endcapped).

    The feed segment is omitted entirely when neither a feed_type nor a
    non-zero lead_length_inches is supplied.
    """
    parts = [tape_spec.name]

    # Total length in inches (manufacturable) — "xx" when not specified.
    if manufacturable_length_mm:
        length_in = manufacturable_length_mm / MM_PER_INCH
    else:
        tape_len_mm = _parse_tape_length(sel)
        length_in = (tape_len_mm / MM_PER_INCH) if tape_len_mm else 0
    if length_in and length_in > 0:
        # Format: remove .0 if whole number, otherwise 1 decimal
        if length_in == int(length_in):
            length_str = str(int(length_in))
        else:
            length_str = f"{length_in:.1f}"
    else:
        length_str = "xx"
    parts.append(length_str)

    # Feed direction code + leader cable length in feet (optional segment).
    feed_type = sel.get("feed_type", "")
    try:
        lead_length_in = float(sel.get("lead_length_inches") or 0)
    except (TypeError, ValueError):
        lead_length_in = 0.0

    if feed_type or lead_length_in > 0:
        feed_type_code = ""
        if feed_type:
            feed_type_code = _get_code("ilL-Attribute-Power Feed Type", feed_type)

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

    # Total manufacturable length in inches (sum of all segments).
    # When no length has been provided yet, fall back to "xx".
    total_mfg_in = sum(s.get("manufacturable_length_in", 0) for s in segments)
    if total_mfg_in and total_mfg_in > 0:
        if total_mfg_in == int(total_mfg_in):
            length_str = str(int(total_mfg_in))
        else:
            length_str = f"{total_mfg_in:.1f}"
    else:
        length_str = "xx"
    parts.append(length_str)

    if len(segments) == 1:
        # Single segment → endcapped.  Feed segment is optional: omit it
        # entirely when neither feed direction nor a non-zero leader length
        # has been supplied.
        seg = segments[0]
        feed_dir = seg.get("start_feed_direction", "")
        try:
            lead_in = float(seg.get("start_lead_length_inches") or 0)
        except (TypeError, ValueError):
            lead_in = 0.0

        if feed_dir or lead_in > 0:
            feed_dir_code = ""
            if feed_dir:
                feed_dir_code = _get_feed_direction_code(feed_dir)

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


# ═══════════════════════════════════════════════════════════════════════
# MOUNTING ACCESSORY API
# ═══════════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=True)
def get_mounting_accessories(
    template_code: str,
    product_category: str = None,
    length_mm: float = 0,
    environment_rating: str = None,
    segments: int = 1,
) -> dict:
    """
    Return eligible mounting accessories for a tape/neon template.

    Queries ``ilL-Rel-Mounting-Accessory-Map`` where
    ``fixture_template = template_code`` and
    ``template_type = 'ilL-Tape-Neon-Template'``.

    For each row, calculates the recommended quantity based on the length
    and the accessory's qty rule, then looks up the unit MSRP from
    ``Item Price`` (Standard Selling).

    Args:
        template_code: The ilL-Tape-Neon-Template template_code (or name)
        product_category: Optional filter — "LED Tape" or "LED Neon"
        length_mm: Total tape/neon length in mm (for qty calculation)
        environment_rating: Optional environment rating filter
        segments: Number of neon segments (for PER_SEGMENT rule)

    Returns:
        dict with ``accessories`` list, each containing:
        ``accessory_item``, ``item_name``, ``mounting_method``,
        ``qty_recommended``, ``unit_msrp``, ``total_msrp``,
        ``qty_rule_description``
    """
    if not template_code:
        return {"success": False, "error": "template_code is required"}

    length_mm = float(length_mm or 0)
    segments = int(segments or 1)

    # Resolve template name from template_code
    template_name = frappe.db.get_value(
        "ilL-Tape-Neon-Template",
        {"template_code": template_code, "is_active": 1},
        "name",
    )
    if not template_name:
        # Try using template_code as a name directly
        if frappe.db.exists("ilL-Tape-Neon-Template", template_code):
            template_name = template_code
        else:
            return {"success": False, "error": f"Template '{template_code}' not found"}

    # Query mounting accessory map
    map_filters = {
        "fixture_template": template_name,
        "template_type": "ilL-Tape-Neon-Template",
        "is_active": 1,
    }
    if environment_rating:
        map_filters["environment_rating"] = environment_rating

    accessory_rows = frappe.get_all(
        "ilL-Rel-Mounting-Accessory-Map",
        filters=map_filters,
        fields=[
            "name", "mounting_method", "accessory_item",
            "qty_rule_type", "qty_rule_value", "min_qty", "rounding",
            "environment_rating",
        ],
        order_by="mounting_method asc",
        ignore_permissions=True,
    )

    if not accessory_rows:
        # Also try with environment_rating unfiltered if nothing found
        if environment_rating:
            map_filters.pop("environment_rating", None)
            accessory_rows = frappe.get_all(
                "ilL-Rel-Mounting-Accessory-Map",
                filters=map_filters,
                fields=[
                    "name", "mounting_method", "accessory_item",
                    "qty_rule_type", "qty_rule_value", "min_qty", "rounding",
                    "environment_rating",
                ],
                order_by="mounting_method asc",
                ignore_permissions=True,
            )

    accessories = []
    for row in accessory_rows:
        item_code = row.accessory_item
        if not item_code:
            continue

        # Look up item name
        item_name = frappe.db.get_value("Item", item_code, "item_name") or item_code

        # Look up unit MSRP from Item Price (Standard Selling)
        unit_msrp = _get_item_msrp(item_code)

        # Calculate recommended qty
        qty_recommended = _calculate_accessory_qty(
            qty_rule_type=row.qty_rule_type or "PER_X_MM",
            qty_rule_value=float(row.qty_rule_value or 304.8),
            min_qty=int(row.min_qty or 0),
            rounding=row.rounding or "CEIL",
            length_mm=length_mm,
            segments=segments,
        )

        total_msrp = round(unit_msrp * qty_recommended, 2)

        # Build human-readable qty rule description
        qty_rule_desc = _describe_qty_rule(
            row.qty_rule_type or "PER_X_MM",
            float(row.qty_rule_value or 304.8),
        )

        accessories.append({
            "accessory_item": item_code,
            "item_name": item_name,
            "mounting_method": row.mounting_method,
            "qty_recommended": qty_recommended,
            "unit_msrp": unit_msrp,
            "total_msrp": total_msrp,
            "qty_rule_description": qty_rule_desc,
            "environment_rating": row.environment_rating or "",
        })

    return {
        "success": True,
        "accessories": accessories,
        "can_skip": True,
    }


def _get_item_msrp(item_code: str) -> float:
    """Look up the Standard Selling price for an item."""
    price = frappe.db.get_value(
        "Item Price",
        {
            "item_code": item_code,
            "price_list": "Standard Selling",
            "selling": 1,
        },
        "price_list_rate",
    )
    return float(price or 0)


def _calculate_accessory_qty(
    qty_rule_type: str,
    qty_rule_value: float,
    min_qty: int,
    rounding: str,
    length_mm: float,
    segments: int = 1,
) -> int:
    """Calculate the recommended quantity for a mounting accessory."""
    if qty_rule_type == "PER_FIXTURE":
        qty = 1
    elif qty_rule_type == "PER_SEGMENT":
        qty = segments
    elif qty_rule_type == "PER_RUN":
        # TODO: determine actual run count from run-splitting logic.
        # Currently assumes 1 run; will need the run_split result when available.
        qty = 1
    elif qty_rule_type == "PER_X_MM":
        if qty_rule_value > 0 and length_mm > 0:
            qty = length_mm / qty_rule_value
        else:
            qty = 0
    else:
        qty = 1

    # Apply rounding
    if rounding == "CEIL":
        qty = math.ceil(qty)
    elif rounding == "FLOOR":
        qty = math.floor(qty)
    else:
        qty = round(qty)

    # Apply minimum
    if min_qty and qty < min_qty:
        qty = min_qty

    return max(qty, 0)


def _describe_qty_rule(qty_rule_type: str, qty_rule_value: float) -> str:
    """Return a human-readable description of the qty rule."""
    if qty_rule_type == "PER_FIXTURE":
        return "1 per fixture"
    elif qty_rule_type == "PER_SEGMENT":
        return "1 per segment"
    elif qty_rule_type == "PER_RUN":
        return "1 per run"
    elif qty_rule_type == "PER_X_MM":
        if qty_rule_value > 0:
            per_ft = MM_PER_FOOT / qty_rule_value
            if abs(per_ft - round(per_ft)) < 0.01:
                return f"{int(round(per_ft))} per foot"
            return f"1 per {qty_rule_value:.0f} mm"
        return "Per length"
    return qty_rule_type
