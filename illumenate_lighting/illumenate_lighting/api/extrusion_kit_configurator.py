# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Extrusion Kit Configurator Engine API

Provides the configuration, validation, and variant-matching flow for
Extrusion Kit products — bundles consisting of:
  - 1 × 2m profile piece
  - 1 × 2m lens piece
  - 6 × mounting accessories
  - 2 × solid endcaps
  - 2 × feed-through endcaps

Users select attribute values (Finish, Lens Appearance, Mounting Method,
Endcap Style, Endcap Color) through the fixture schedule UI.  The engine
resolves each selection to specific Items via the relationship/mapping
doctypes and pulls linked spec information for every component.

Flow:
  1. get_kit_configurator_init()  → returns available options for a kit template
  2. get_kit_cascading_options()  → narrows options as selections are made
  3. validate_kit_configuration() → validates all selections, resolves Items,
                                     builds part number, collects spec data
  4. save_kit_to_schedule()       → saves the result to a fixture schedule line
"""

import hashlib
import json
from typing import Any, Optional

import frappe
from frappe import _


# ═══════════════════════════════════════════════════════════════════════
# INITIALISATION
# ═══════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_kit_configurator_init(kit_template_name: str = None) -> dict:
    """
    Initialise the Extrusion Kit configurator.

    If *kit_template_name* is given, load that template's allowed options.
    Otherwise return all active kit templates for the user to pick one.

    Returns everything the front-end needs to render the step-by-step UI:
      - Kit templates (if no template specified)
      - Allowed finishes, lens appearances, mounting methods, endcap styles/colors
      - Kit composition details (profile length, lens length, quantities)
      - Default selections (if any)
    """
    if kit_template_name:
        if not frappe.db.exists("ilL-Extrusion-Kit-Template", kit_template_name):
            return {"success": False, "error": f"Kit template '{kit_template_name}' not found"}

        template = frappe.get_doc("ilL-Extrusion-Kit-Template", kit_template_name)
        if not template.is_active:
            return {"success": False, "error": "Kit template is not active"}

        return _build_init_response(template)

    # No template specified — return list of available templates
    templates = frappe.get_all(
        "ilL-Extrusion-Kit-Template",
        filters={"is_active": 1},
        fields=["name", "template_code", "template_name", "series",
                "profile_stock_length_mm", "lens_stock_length_mm",
                "solid_endcap_qty", "feed_through_endcap_qty",
                "mounting_accessory_qty"],
        order_by="template_name asc",
    )

    return {
        "success": True,
        "templates": templates,
        "message": "Select a kit template to begin configuration",
    }


def _build_init_response(template) -> dict:
    """Build the full init response for a given kit template."""
    # Collect allowed options by type
    options = {}
    defaults = {}

    option_types = {
        "Finish": ("finish", "ilL-Attribute-Finish", ["name", "code"]),
        "Lens Appearance": ("lens_appearance", "ilL-Attribute-Lens Appearance", ["name", "code"]),
        "Mounting Method": ("mounting_method", "ilL-Attribute-Mounting Method", ["name", "code"]),
        "Endcap Style": ("endcap_style", "ilL-Attribute-Endcap Style", ["name", "code"]),
        "Endcap Color": ("endcap_color", "ilL-Attribute-Endcap Color", ["name", "code"]),
    }

    for opt_type, (field_name, doctype, fields) in option_types.items():
        allowed_values = template.get_allowed_values(opt_type)
        default_value = template.get_default_value(opt_type)

        if allowed_values:
            option_details = []
            for val in allowed_values:
                data = frappe.db.get_value(doctype, val, fields, as_dict=True)
                if data:
                    option_details.append({
                        "value": data.name,
                        "label": data.name,
                        "code": data.get("code", ""),
                    })
            options[field_name] = sorted(option_details, key=lambda x: x["label"])
        else:
            # If no allowed options defined, get all active from the attribute doctype
            all_vals = frappe.get_all(doctype, fields=fields, order_by="name asc")
            options[field_name] = [
                {"value": v.name, "label": v.name, "code": v.get("code", "")}
                for v in all_vals
            ]

        if default_value:
            defaults[field_name] = default_value

    return {
        "success": True,
        "kit_template": {
            "name": template.name,
            "template_code": template.template_code,
            "template_name": template.template_name,
            "series": template.series,
            "profile_stock_length_mm": template.profile_stock_length_mm,
            "lens_stock_length_mm": template.lens_stock_length_mm,
            "solid_endcap_qty": template.solid_endcap_qty,
            "feed_through_endcap_qty": template.feed_through_endcap_qty,
            "mounting_accessory_qty": template.mounting_accessory_qty,
            "base_price_msrp": template.base_price_msrp,
            "default_profile_spec": template.default_profile_spec,
            "default_lens_spec": template.default_lens_spec,
            "spec_sheet": template.spec_sheet,
        },
        "options": options,
        "defaults": defaults,
    }


# ═══════════════════════════════════════════════════════════════════════
# CASCADING OPTIONS
# ═══════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_kit_cascading_options(
    kit_template_name: str,
    finish: str = None,
    lens_appearance: str = None,
    mounting_method: str = None,
    endcap_style: str = None,
) -> dict:
    """
    Return filtered options based on prior selections.

    Cascading logic:
      - Finish → filters which lens appearances have compatible profile/lens combos
      - Endcap Style → filters which endcap colors are available
      - Mounting Method → validates mounting map exists

    This allows the UI to disable/hide options that won't lead to a valid configuration.
    """
    if not frappe.db.exists("ilL-Extrusion-Kit-Template", kit_template_name):
        return {"success": False, "error": "Kit template not found"}

    template = frappe.get_doc("ilL-Extrusion-Kit-Template", kit_template_name)
    result = {"success": True}

    # ── If finish is selected, show which lens appearances have valid mappings ──
    if finish:
        # Check which profile maps exist for this template + finish
        profile_maps = frappe.get_all(
            "ilL-Rel-Kit-Profile-Map",
            filters={"kit_template": kit_template_name, "finish": finish, "is_active": 1},
            fields=["name", "profile_spec", "profile_item"],
        )
        result["profile_available"] = len(profile_maps) > 0
        if profile_maps:
            result["resolved_profile"] = {
                "profile_spec": profile_maps[0].profile_spec,
                "profile_item": profile_maps[0].profile_item,
            }

        # Filter lens appearances that have valid lens maps
        allowed_lenses = template.get_allowed_values("Lens Appearance")
        available_lenses = []
        for la in allowed_lenses:
            lens_maps = frappe.get_all(
                "ilL-Rel-Kit-Lens-Map",
                filters={"kit_template": kit_template_name, "lens_appearance": la, "is_active": 1},
                fields=["name"],
                limit=1,
            )
            if lens_maps:
                data = frappe.db.get_value(
                    "ilL-Attribute-Lens Appearance", la,
                    ["name", "code"], as_dict=True,
                )
                if data:
                    available_lenses.append({
                        "value": data.name,
                        "label": data.name,
                        "code": data.get("code", ""),
                    })
        result["available_lens_appearances"] = available_lenses

    # ── If endcap style is selected, show which colors are available ──
    if endcap_style:
        endcap_maps = frappe.get_all(
            "ilL-Rel-Kit-Endcap-Map",
            filters={
                "kit_template": kit_template_name,
                "endcap_style": endcap_style,
                "is_active": 1,
            },
            fields=["endcap_color"],
            group_by="endcap_color",
        )
        available_colors = []
        for em in endcap_maps:
            data = frappe.db.get_value(
                "ilL-Attribute-Endcap Color", em.endcap_color,
                ["name", "code"], as_dict=True,
            )
            if data:
                available_colors.append({
                    "value": data.name,
                    "label": data.name,
                    "code": data.get("code", ""),
                })
        result["available_endcap_colors"] = sorted(available_colors, key=lambda x: x["label"])

    # ── If mounting method is selected, validate map exists ──
    if mounting_method:
        mounting_maps = frappe.get_all(
            "ilL-Rel-Kit-Mounting-Map",
            filters={
                "kit_template": kit_template_name,
                "mounting_method": mounting_method,
                "is_active": 1,
            },
            fields=["name", "accessory_spec", "accessory_item"],
        )
        result["mounting_available"] = len(mounting_maps) > 0
        if mounting_maps:
            result["resolved_mounting"] = {
                "accessory_spec": mounting_maps[0].accessory_spec,
                "accessory_item": mounting_maps[0].accessory_item,
            }

    return result


# ═══════════════════════════════════════════════════════════════════════
# VALIDATE & RESOLVE
# ═══════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def validate_kit_configuration(selections: str) -> dict:
    """
    Validate a complete Extrusion Kit configuration and resolve all component Items.

    Selections dict keys:
      - kit_template       (str) – kit template name
      - finish             (str) – selected finish attribute
      - lens_appearance    (str) – selected lens appearance attribute
      - mounting_method    (str) – selected mounting method attribute
      - endcap_style       (str) – selected endcap style attribute
      - endcap_color       (str) – selected endcap color attribute

    Returns:
      - is_valid           (bool)
      - part_number        (str) – built from attribute codes
      - build_description  (str) – human-readable description
      - kit_composition    (dict) – profile/lens/endcap/mounting items + quantities
      - spec_data          (dict) – pulled spec info from all linked spec doctypes
      - resolved_items     (dict) – all resolved Item codes
      - messages           (list) – warnings/info
    """
    try:
        sel = json.loads(selections) if isinstance(selections, str) else selections
    except json.JSONDecodeError:
        return {"success": False, "is_valid": False, "error": "Invalid selections JSON"}

    messages = []

    # ── Validate required fields ──────────────────────────────────────
    required = ["kit_template", "finish", "lens_appearance", "mounting_method",
                "endcap_style", "endcap_color"]
    missing = [f for f in required if not sel.get(f)]
    if missing:
        return {
            "success": False,
            "is_valid": False,
            "error": f"Missing required fields: {', '.join(missing)}",
            "missing_fields": missing,
        }

    kit_template_name = sel["kit_template"]
    if not frappe.db.exists("ilL-Extrusion-Kit-Template", kit_template_name):
        return {"success": False, "is_valid": False, "error": "Kit template not found"}

    template = frappe.get_doc("ilL-Extrusion-Kit-Template", kit_template_name)

    # ── Validate selections against allowed options ───────────────────
    validation_checks = {
        "Finish": sel["finish"],
        "Lens Appearance": sel["lens_appearance"],
        "Mounting Method": sel["mounting_method"],
        "Endcap Style": sel["endcap_style"],
        "Endcap Color": sel["endcap_color"],
    }

    for opt_type, selected_value in validation_checks.items():
        allowed = template.get_allowed_values(opt_type)
        if allowed and selected_value not in allowed:
            return {
                "success": False,
                "is_valid": False,
                "error": f"'{selected_value}' is not an allowed {opt_type} for this kit template",
            }

    # ── Resolve Profile ───────────────────────────────────────────────
    profile_map = _resolve_kit_profile(kit_template_name, sel["finish"])
    if not profile_map:
        return {
            "success": False,
            "is_valid": False,
            "error": f"No profile mapping found for kit '{kit_template_name}' with finish '{sel['finish']}'",
        }

    # ── Resolve Lens ──────────────────────────────────────────────────
    lens_map = _resolve_kit_lens(kit_template_name, sel["lens_appearance"])
    if not lens_map:
        return {
            "success": False,
            "is_valid": False,
            "error": f"No lens mapping found for kit '{kit_template_name}' with lens '{sel['lens_appearance']}'",
        }

    # ── Resolve Endcaps (Solid + Feed-Through) ────────────────────────
    solid_endcap = _resolve_kit_endcap(
        kit_template_name, sel["endcap_style"], sel["endcap_color"], "Solid"
    )
    feed_through_endcap = _resolve_kit_endcap(
        kit_template_name, sel["endcap_style"], sel["endcap_color"], "Feed-Through"
    )

    if not solid_endcap:
        return {
            "success": False,
            "is_valid": False,
            "error": (
                f"No solid endcap mapping found for kit '{kit_template_name}' "
                f"with style '{sel['endcap_style']}' and color '{sel['endcap_color']}'"
            ),
        }

    if not feed_through_endcap:
        return {
            "success": False,
            "is_valid": False,
            "error": (
                f"No feed-through endcap mapping found for kit '{kit_template_name}' "
                f"with style '{sel['endcap_style']}' and color '{sel['endcap_color']}'"
            ),
        }

    # ── Resolve Mounting ──────────────────────────────────────────────
    mounting_map = _resolve_kit_mounting(kit_template_name, sel["mounting_method"])
    if not mounting_map:
        return {
            "success": False,
            "is_valid": False,
            "error": f"No mounting mapping found for kit '{kit_template_name}' with method '{sel['mounting_method']}'",
        }

    # ── Collect spec data from all linked spec doctypes ───────────────
    spec_data = _collect_spec_data(profile_map, lens_map, solid_endcap,
                                   feed_through_endcap, mounting_map)

    # ── Build part number ─────────────────────────────────────────────
    part_number = _build_kit_part_number(sel, template)

    # ── Build description ─────────────────────────────────────────────
    build_description = _build_kit_description(sel, template, profile_map, lens_map,
                                                solid_endcap, feed_through_endcap,
                                                mounting_map)

    # ── Build kit composition ─────────────────────────────────────────
    kit_composition = {
        "profile": {
            "item": profile_map.profile_item,
            "spec": profile_map.profile_spec,
            "spec_doctype": "ilL-Spec-Profile",
            "qty": 1,
            "length_mm": template.profile_stock_length_mm,
        },
        "lens": {
            "item": lens_map.lens_item,
            "spec": lens_map.lens_spec,
            "spec_doctype": "ilL-Spec-Lens",
            "qty": 1,
            "length_mm": template.lens_stock_length_mm,
        },
        "solid_endcap": {
            "item": solid_endcap.endcap_item,
            "spec": solid_endcap.endcap_spec,
            "spec_doctype": "ilL-Spec-Accessory",
            "qty": template.solid_endcap_qty,
        },
        "feed_through_endcap": {
            "item": feed_through_endcap.endcap_item,
            "spec": feed_through_endcap.endcap_spec,
            "spec_doctype": "ilL-Spec-Accessory",
            "qty": template.feed_through_endcap_qty,
        },
        "mounting": {
            "item": mounting_map.accessory_item,
            "spec": mounting_map.accessory_spec,
            "spec_doctype": "ilL-Spec-Accessory",
            "qty": template.mounting_accessory_qty,
        },
    }

    # ── Build resolved items summary ──────────────────────────────────
    resolved_items = {
        "profile_item": profile_map.profile_item,
        "profile_spec": profile_map.profile_spec,
        "lens_item": lens_map.lens_item,
        "lens_spec": lens_map.lens_spec,
        "solid_endcap_item": solid_endcap.endcap_item,
        "solid_endcap_spec": solid_endcap.endcap_spec,
        "feed_through_endcap_item": feed_through_endcap.endcap_item,
        "feed_through_endcap_spec": feed_through_endcap.endcap_spec,
        "mounting_item": mounting_map.accessory_item,
        "mounting_spec": mounting_map.accessory_spec,
    }

    # ── Compute config hash for deduplication ─────────────────────────
    config_hash = _compute_config_hash(sel)

    # ── Stock availability (component-level) ──────────────────────────
    stock_availability = None
    try:
        stock_result = get_kit_component_stock(
            kit_template=kit_template_name,
            finish=sel["finish"],
            lens_appearance=sel["lens_appearance"],
            mounting_method=sel["mounting_method"],
            endcap_style=sel["endcap_style"],
            endcap_color=sel["endcap_color"],
        )
        if stock_result.get("success"):
            components = stock_result.get("components", [])
            all_in_stock = all(c.get("in_stock", False) for c in components)
            items = []
            for c in components:
                items.append({
                    "item_code": c.get("item_code") or "",
                    "item_name": c.get("item_name") or "",
                    "component_type": c.get("component", ""),
                    "is_sufficient": c.get("in_stock", False),
                    "qty_required": c.get("qty_per_kit", 0),
                    "qty_available": c.get("stock_qty", 0),
                    "lead_time_class": c.get("lead_time_class", ""),
                })
            stock_availability = {
                "all_in_stock": all_in_stock,
                "items": items,
                "total_kits_fulfillable": stock_result.get("total_kits_fulfillable", 0),
                "limiting_component": stock_result.get("limiting_component"),
            }
    except Exception:
        pass  # Non-critical; omit from response on failure

    result = {
        "success": True,
        "is_valid": True,
        "messages": messages,
        "product_category": "Extrusion Kit",
        "part_number": part_number,
        "build_description": build_description,
        "config_hash": config_hash,
        "kit_composition": kit_composition,
        "spec_data": spec_data,
        "resolved_items": resolved_items,
        "selections": sel,
        "kit_template": {
            "name": template.name,
            "template_code": template.template_code,
            "template_name": template.template_name,
            "profile_stock_length_mm": template.profile_stock_length_mm,
            "lens_stock_length_mm": template.lens_stock_length_mm,
            "solid_endcap_qty": template.solid_endcap_qty,
            "feed_through_endcap_qty": template.feed_through_endcap_qty,
            "mounting_accessory_qty": template.mounting_accessory_qty,
            "base_price_msrp": template.base_price_msrp,
            "spec_sheet": template.spec_sheet,
        },
    }
    if stock_availability is not None:
        result["stock_availability"] = stock_availability
    return result


# ═══════════════════════════════════════════════════════════════════════
# SAVE TO SCHEDULE
# ═══════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def save_kit_to_schedule(
    schedule_name: str,
    line_idx: int = None,
    configuration_result: str = None,
) -> dict:
    """
    Save a validated Extrusion Kit configuration to a fixture schedule line.

    Stores:
      - product_type = "Extrusion Kit"
      - part number as the item_code
      - build description in notes
      - full config as JSON in variant_selections

    Args:
        schedule_name: ilL-Project-Fixture-Schedule name
        line_idx: existing line index to overwrite, or None for new line
        configuration_result: JSON string of the validate_kit_configuration result
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

    part_number = result.get("part_number", "")
    build_desc = result.get("build_description", "")
    resolved = result.get("resolved_items", {})
    kit_comp = result.get("kit_composition", {})
    spec_data = result.get("spec_data", {})
    kit_template_info = result.get("kit_template", {})

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
        line.product_type = "Extrusion Kit"
        line.configuration_status = "Configured"
        line.ill_item_code = part_number
        line.notes = build_desc
        line.kit_template = kit_template_info.get("name", "")

        # Store full configuration as JSON for later SO conversion
        line.variant_selections = json.dumps({
            "product_category": "Extrusion Kit",
            "part_number": part_number,
            "build_description": build_desc,
            "kit_composition": kit_comp,
            "spec_data": spec_data,
            "resolved_items": resolved,
            "selections": result.get("selections", {}),
            "kit_template": kit_template_info,
        })

        schedule.save()

        return {
            "success": True,
            "message": "Extrusion Kit configuration saved to schedule",
            "line_idx": line.idx - 1 if hasattr(line, "idx") else len(schedule.lines) - 1,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_kit_so_lines(so, line, config_data: dict) -> dict:
    """
    Called during Sales Order creation to add Extrusion Kit item lines.

    Creates SO lines for each component in the kit:
      - Profile item (qty=1)
      - Lens item (qty=1)
      - Solid endcaps (qty from template, typically 2)
      - Feed-through endcaps (qty from template, typically 2)
      - Mounting accessories (qty from template, typically 6)

    Args:
        so: The Sales Order document being built
        line: The schedule line
        config_data: Parsed JSON from line.variant_selections

    Returns:
        dict with items_added count and messages
    """
    kit_comp = config_data.get("kit_composition", {})
    part_number = config_data.get("part_number", "")
    build_desc = config_data.get("build_description", "")
    kit_template = config_data.get("kit_template", {})

    items_added = 0
    messages = []

    component_order = [
        ("profile", "Profile"),
        ("lens", "Lens"),
        ("solid_endcap", "Solid Endcap"),
        ("feed_through_endcap", "Feed-Through Endcap"),
        ("mounting", "Mounting Accessory"),
    ]

    for comp_key, comp_label in component_order:
        comp = kit_comp.get(comp_key, {})
        item_code = comp.get("item")
        qty = comp.get("qty", 1)

        if not item_code:
            messages.append(f"Warning: No {comp_label} item defined in kit composition")
            continue

        so_item = so.append("items", {})
        so_item.item_code = item_code
        so_item.qty = qty

        length_info = ""
        if comp.get("length_mm"):
            length_info = f" – {comp['length_mm']}mm"

        so_item.description = (
            f"{part_number} – {comp_label}{length_info}\n{build_desc}"
        )
        items_added += 1

    return {"items_added": items_added, "messages": messages}


# ═══════════════════════════════════════════════════════════════════════
# GET SPEC DATA
# ═══════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_kit_spec_data(kit_template_name: str, selections: str = None) -> dict:
    """
    Get the full spec information for a kit configuration.

    This pulls all linked spec data from the profile, lens, accessory, and
    endcap spec doctypes so that spec sheets and submittals can reference it.

    Can be called with just a kit_template_name (returns default specs)
    or with full selections (returns resolved specs for the selected variant).
    """
    if selections:
        # Full resolution with selections
        result = validate_kit_configuration(selections)
        if not result.get("is_valid"):
            return result
        return {
            "success": True,
            "spec_data": result.get("spec_data", {}),
            "kit_composition": result.get("kit_composition", {}),
        }

    # Default specs from template
    if not frappe.db.exists("ilL-Extrusion-Kit-Template", kit_template_name):
        return {"success": False, "error": "Kit template not found"}

    template = frappe.get_doc("ilL-Extrusion-Kit-Template", kit_template_name)
    spec_data = {}

    if template.default_profile_spec:
        spec_data["profile"] = _get_profile_spec_data(template.default_profile_spec)
    if template.default_lens_spec:
        spec_data["lens"] = _get_lens_spec_data(template.default_lens_spec)

    return {
        "success": True,
        "spec_data": spec_data,
        "kit_template": template.name,
    }


# ═══════════════════════════════════════════════════════════════════════
# KIT COMPONENT STOCK LEVELS
# ═══════════════════════════════════════════════════════════════════════


@frappe.whitelist(allow_guest=False)
def get_kit_component_stock(
	kit_template: str,
	finish: str,
	lens_appearance: str,
	mounting_method: str,
	endcap_style: str,
	endcap_color: str,
) -> dict:
	"""
	Resolve extrusion kit component items and return per-component stock levels.

	Uses the existing 4 mapping doctypes to resolve each component Item, then
	queries ``tabBin`` for aggregate stock and computes how many complete kits
	are fulfillable.

	Args:
		kit_template: Name of ilL-Extrusion-Kit-Template
		finish: Selected finish attribute value
		lens_appearance: Selected lens appearance attribute value
		mounting_method: Selected mounting method attribute value
		endcap_style: Selected endcap style attribute value
		endcap_color: Selected endcap color attribute value

	Returns:
		dict: {
			"success": True/False,
			"components": [
				{
					"component": str,
					"item_code": str,
					"qty_per_kit": int/float,
					"stock_qty": float,
					"kits_fulfillable": int,
					"in_stock": bool,
					"lead_time_class": str,
				}, ...
			],
			"total_kits_fulfillable": int,
			"limiting_component": str or None,
		}
	"""
	if not kit_template:
		return {"success": False, "error": "kit_template is required"}

	if not frappe.db.exists("ilL-Extrusion-Kit-Template", kit_template):
		return {"success": False, "error": "Kit template not found"}

	template = frappe.get_doc("ilL-Extrusion-Kit-Template", kit_template)

	# ── Resolve all 5 components via existing map helpers ─────────────
	profile_map = _resolve_kit_profile(kit_template, finish)
	lens_map = _resolve_kit_lens(kit_template, lens_appearance)
	solid_endcap = _resolve_kit_endcap(kit_template, endcap_style, endcap_color, "Solid")
	feed_through_endcap = _resolve_kit_endcap(kit_template, endcap_style, endcap_color, "Feed-Through")
	mounting_map = _resolve_kit_mounting(kit_template, mounting_method)

	# Build component list: (label, item_code, qty_per_kit)
	component_defs = [
		("Profile", profile_map.profile_item if profile_map else None, 1),
		("Lens", lens_map.lens_item if lens_map else None, 1),
		("Solid Endcap", solid_endcap.endcap_item if solid_endcap else None, template.solid_endcap_qty or 0),
		("Feed-Through Endcap", feed_through_endcap.endcap_item if feed_through_endcap else None, template.feed_through_endcap_qty or 0),
		("Mounting Accessory", mounting_map.accessory_item if mounting_map else None, template.mounting_accessory_qty or 0),
	]

	return _build_kit_stock_result(component_defs)


def _build_kit_stock_result(component_defs: list) -> dict:
	"""
	Given a list of (label, item_code, qty_per_kit) tuples, query stock and
	compute per-component fulfillability and overall kit fulfillability.

	Returns the structured stock result dict.
	"""
	import math

	from frappe.utils import flt

	# Batch-fetch stock for all distinct item codes in one query
	item_codes = [c[1] for c in component_defs if c[1]]
	stock_map: dict[str, float] = {}
	if item_codes:
		bins = frappe.db.sql(
			"""SELECT item_code, IFNULL(SUM(actual_qty), 0) AS total_qty
			   FROM `tabBin`
			   WHERE item_code IN %s
			   GROUP BY item_code""",
			[item_codes],
			as_dict=True,
		)
		stock_map = {row.item_code: flt(row.total_qty) for row in bins}

	# Batch-fetch lead_time_days and item_name for all item codes
	lead_time_map: dict[str, int] = {}
	item_name_map: dict[str, str] = {}
	if item_codes:
		lead_rows = frappe.db.sql(
			"""SELECT name, IFNULL(lead_time_days, 0) AS lead_time_days,
			          item_name
			   FROM `tabItem`
			   WHERE name IN %s""",
			[item_codes],
			as_dict=True,
		)
		lead_time_map = {row.name: int(row.lead_time_days) for row in lead_rows}
		item_name_map = {row.name: row.item_name or row.name for row in lead_rows}

	components = []
	min_kits = None
	limiting = None

	for label, item_code, qty_per_kit in component_defs:
		if not item_code:
			components.append({
				"component": label,
				"item_code": None,
				"item_name": None,
				"qty_per_kit": qty_per_kit,
				"stock_qty": 0,
				"kits_fulfillable": 0,
				"in_stock": False,
				"lead_time_class": "special-order",
			})
			if min_kits is None or 0 < min_kits:
				min_kits = 0
				limiting = label
			continue

		stock_qty = stock_map.get(item_code, 0.0)
		in_stock = stock_qty > 0

		# Lead-time classification (matches get_stock_status pattern)
		if in_stock:
			lead_time_class = "in-stock"
		else:
			lead_days = lead_time_map.get(item_code, 0)
			lead_time_class = "made-to-order" if lead_days > 0 else "special-order"

		kits_fulfillable = math.floor(stock_qty / qty_per_kit) if qty_per_kit > 0 else 0

		components.append({
			"component": label,
			"item_code": item_code,
			"item_name": item_name_map.get(item_code, item_code),
			"qty_per_kit": qty_per_kit,
			"stock_qty": stock_qty,
			"kits_fulfillable": kits_fulfillable,
			"in_stock": in_stock,
			"lead_time_class": lead_time_class,
		})

		if min_kits is None or kits_fulfillable < min_kits:
			min_kits = kits_fulfillable
			limiting = label

	total_kits = min_kits if min_kits is not None else 0

	return {
		"success": True,
		"components": components,
		"total_kits_fulfillable": total_kits,
		"limiting_component": limiting,
	}


# ═══════════════════════════════════════════════════════════════════════
# PRIVATE HELPERS – Resolution
# ═══════════════════════════════════════════════════════════════════════

def _resolve_kit_profile(kit_template_name: str, finish: str) -> Optional[Any]:
    """Resolve the profile Item via ilL-Rel-Kit-Profile-Map."""
    maps = frappe.get_all(
        "ilL-Rel-Kit-Profile-Map",
        filters={
            "kit_template": kit_template_name,
            "finish": finish,
            "is_active": 1,
        },
        fields=["name", "profile_spec", "profile_item"],
        limit=1,
    )
    return maps[0] if maps else None


def _resolve_kit_lens(kit_template_name: str, lens_appearance: str) -> Optional[Any]:
    """Resolve the lens Item via ilL-Rel-Kit-Lens-Map."""
    maps = frappe.get_all(
        "ilL-Rel-Kit-Lens-Map",
        filters={
            "kit_template": kit_template_name,
            "lens_appearance": lens_appearance,
            "is_active": 1,
        },
        fields=["name", "lens_spec", "lens_item"],
        limit=1,
    )
    return maps[0] if maps else None


def _resolve_kit_endcap(
    kit_template_name: str,
    endcap_style: str,
    endcap_color: str,
    endcap_type: str,
) -> Optional[Any]:
    """Resolve an endcap Item via ilL-Rel-Kit-Endcap-Map."""
    maps = frappe.get_all(
        "ilL-Rel-Kit-Endcap-Map",
        filters={
            "kit_template": kit_template_name,
            "endcap_style": endcap_style,
            "endcap_color": endcap_color,
            "endcap_type": endcap_type,
            "is_active": 1,
        },
        fields=["name", "endcap_spec", "endcap_item"],
        limit=1,
    )
    return maps[0] if maps else None


def _resolve_kit_mounting(kit_template_name: str, mounting_method: str) -> Optional[Any]:
    """Resolve the mounting accessory Item via ilL-Rel-Kit-Mounting-Map."""
    maps = frappe.get_all(
        "ilL-Rel-Kit-Mounting-Map",
        filters={
            "kit_template": kit_template_name,
            "mounting_method": mounting_method,
            "is_active": 1,
        },
        fields=["name", "accessory_spec", "accessory_item"],
        limit=1,
    )
    return maps[0] if maps else None


# ═══════════════════════════════════════════════════════════════════════
# PRIVATE HELPERS – Spec Data Collection
# ═══════════════════════════════════════════════════════════════════════

def _collect_spec_data(profile_map, lens_map, solid_endcap,
                       feed_through_endcap, mounting_map) -> dict:
    """Pull spec data from all linked spec doctypes for the resolved items."""
    spec_data = {}

    # Profile spec data
    if profile_map.profile_spec:
        spec_data["profile"] = _get_profile_spec_data(profile_map.profile_spec)

    # Lens spec data
    if lens_map.lens_spec:
        spec_data["lens"] = _get_lens_spec_data(lens_map.lens_spec)

    # Endcap spec data
    if solid_endcap.endcap_spec:
        spec_data["solid_endcap"] = _get_accessory_spec_data(solid_endcap.endcap_spec)
    if feed_through_endcap.endcap_spec:
        spec_data["feed_through_endcap"] = _get_accessory_spec_data(feed_through_endcap.endcap_spec)

    # Mounting spec data
    if mounting_map.accessory_spec:
        spec_data["mounting"] = _get_accessory_spec_data(mounting_map.accessory_spec)

    return spec_data


def _get_profile_spec_data(spec_name: str) -> dict:
    """Get full spec data from an ilL-Spec-Profile doc."""
    try:
        spec = frappe.get_doc("ilL-Spec-Profile", spec_name)
        data = {
            "spec_name": spec.name,
            "item": spec.item,
            "family": spec.family,
            "variant_code": spec.variant_code,
            "series": spec.series,
            "width_mm": spec.width_mm,
            "height_mm": spec.height_mm,
            "dimensions": spec.dimensions,
            "weight_per_meter_grams": spec.weight_per_meter_grams,
            "stock_length_mm": spec.stock_length_mm,
            "max_assembled_length_mm": spec.max_assembled_length_mm,
            "is_cuttable": spec.is_cuttable,
            "supports_joiners": spec.supports_joiners,
            "joiner_system": spec.joiner_system,
            "lens_interface": spec.lens_interface,
        }

        # Include supported environment ratings
        if hasattr(spec, "supported_environment_ratings"):
            data["environment_ratings"] = [
                row.environment_rating
                for row in spec.supported_environment_ratings
                if hasattr(row, "environment_rating")
            ]

        return data
    except Exception:
        return {"spec_name": spec_name, "error": "Could not load spec"}


def _get_lens_spec_data(spec_name: str) -> dict:
    """Get full spec data from an ilL-Spec-Lens doc."""
    try:
        spec = frappe.get_doc("ilL-Spec-Lens", spec_name)
        data = {
            "spec_name": spec.name,
            "item": spec.item,
            "family": spec.family,
            "lens_appearance": spec.lens_appearance,
            "series": spec.series,
            "stock_type": spec.stock_type,
            "stock_length_mm": spec.stock_length_mm,
            "continuous_max_length_mm": spec.continuous_max_length_mm,
        }

        # Include supported environment ratings
        if hasattr(spec, "supported_environment_ratings"):
            data["environment_ratings"] = [
                row.environment_rating
                for row in spec.supported_environment_ratings
                if hasattr(row, "environment_rating")
            ]

        return data
    except Exception:
        return {"spec_name": spec_name, "error": "Could not load spec"}


def _get_accessory_spec_data(spec_name: str) -> dict:
    """Get full spec data from an ilL-Spec-Accessory doc."""
    try:
        spec = frappe.get_doc("ilL-Spec-Accessory", spec_name)
        return {
            "spec_name": spec.name,
            "item": spec.item,
            "type": spec.type,
            "profile_family": spec.profile_family,
            "environment_rating": spec.environment_rating,
            "mounting_method": spec.mounting_method,
            "endcap_style": spec.endcap_style,
            "joiner_system": spec.joiner_system,
            "feed_type": spec.feed_type,
            "qty_rule_type": spec.qty_rule_type,
            "qty_rule_value": spec.qty_rule_value,
        }
    except Exception:
        return {"spec_name": spec_name, "error": "Could not load spec"}


# ═══════════════════════════════════════════════════════════════════════
# PRIVATE HELPERS – Part Number & Description
# ═══════════════════════════════════════════════════════════════════════

def _get_code(doctype: str, name: str, code_field: str = "code") -> str:
    """Look up an attribute code, returning 'xx' on miss."""
    if not name:
        return "xx"
    code = frappe.db.get_value(doctype, name, code_field)
    return code or "xx"


def _build_kit_part_number(sel: dict, template) -> str:
    """
    Build Extrusion Kit part number from attribute codes.

    Format: ILL-KIT-{SERIES}-{FINISH}-{LENS}-{MOUNT}-{ENDCAP_STYLE}-{ENDCAP_COLOR}
    """
    parts = ["ILL", "KIT"]

    # Series code from template
    if template.series:
        parts.append(_get_code("ilL-Attribute-Series", template.series))
    else:
        parts.append(template.template_code[:6].upper())

    # Finish
    parts.append(_get_code("ilL-Attribute-Finish", sel.get("finish")))

    # Lens appearance
    parts.append(_get_code("ilL-Attribute-Lens Appearance", sel.get("lens_appearance")))

    # Mounting method
    parts.append(_get_code("ilL-Attribute-Mounting Method", sel.get("mounting_method")))

    # Endcap style
    parts.append(_get_code("ilL-Attribute-Endcap Style", sel.get("endcap_style")))

    # Endcap color
    parts.append(_get_code("ilL-Attribute-Endcap Color", sel.get("endcap_color")))

    return "-".join(parts)


def _build_kit_description(sel, template, profile_map, lens_map,
                           solid_endcap, feed_through_endcap, mounting_map) -> str:
    """Build a human-readable description for the Extrusion Kit configuration."""
    lines = []
    lines.append(f"Extrusion Kit: {template.template_name}")
    lines.append(f"Finish: {sel.get('finish', '-')}")
    lines.append(f"Lens: {sel.get('lens_appearance', '-')}")
    lines.append(f"Mounting: {sel.get('mounting_method', '-')}")
    lines.append(f"Endcap Style: {sel.get('endcap_style', '-')}")
    lines.append(f"Endcap Color: {sel.get('endcap_color', '-')}")
    lines.append(f"Profile: {profile_map.profile_item} ({template.profile_stock_length_mm}mm)")
    lines.append(f"Lens: {lens_map.lens_item} ({template.lens_stock_length_mm}mm)")
    lines.append(
        f"Solid Endcaps: {solid_endcap.endcap_item} ×{template.solid_endcap_qty}"
    )
    lines.append(
        f"Feed-Through Endcaps: {feed_through_endcap.endcap_item} ×{template.feed_through_endcap_qty}"
    )
    lines.append(
        f"Mounting: {mounting_map.accessory_item} ×{template.mounting_accessory_qty}"
    )

    return " | ".join(lines)


def _compute_config_hash(sel: dict) -> str:
    """Compute a SHA-256 hash of the configuration for dedup."""
    # Sort keys for deterministic hashing
    canonical = json.dumps(sel, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
