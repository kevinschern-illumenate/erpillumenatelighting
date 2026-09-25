# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Portal/desk APIs for configuring LED Sheet products."""

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from illumenate_lighting.illumenate_lighting.api import led_sheet_bundle
from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
    fingerprint,
    finite_number,
    parse_bool,
)
from illumenate_lighting.illumenate_lighting.api.led_sheet_math import (
    aggregate_power_supplies,
    build_accessory_lines,
    build_groups,
    compute_panel_layout,
    generated_accessory_marker,
    is_generated_accessory_line,
    jumper_cable_qty,
    leader_cable_qty,
    normalize_dimension,
)

OPTION_FIELD_BY_TYPE = {
    "CCT": "selected_cct",
    "Output Level": "selected_output_level",
    "Environment Rating": "selected_environment_rating",
    "Mounting": "selected_mounting",
    "Finish": "selected_finish",
}
SKU_FIELD_BY_TYPE = {
    "CCT": "sku_cct_code",
    "Output Level": "sku_output_code",
    "Environment Rating": "sku_environment_code",
    "Mounting": "sku_mounting_code",
    "Finish": "sku_finish_code",
}


def _coerce_options(options: str | dict | None) -> dict[str, Any]:
    if isinstance(options, str):
        options = json.loads(options)
    if options is not None and not isinstance(options, dict):
        frappe.throw(_("LED Sheet options must be an object"))
    return options or {}


def _coerce_bool(value: Any) -> bool:
    return parse_bool(value)


def _norm_option_key(key: str) -> str:
    lookup = {
        "cct": "CCT",
        "selected_cct": "CCT",
        "output": "Output Level",
        "output_level": "Output Level",
        "selected_output_level": "Output Level",
        "environment": "Environment Rating",
        "environment_rating": "Environment Rating",
        "selected_environment_rating": "Environment Rating",
        "mounting": "Mounting",
        "mounting_method": "Mounting",
        "selected_mounting": "Mounting",
        "finish": "Finish",
        "selected_finish": "Finish",
    }
    return lookup.get((key or "").strip(), key)


def _allowed_option_map(template_doc) -> dict[str, dict[str, Any]]:
    allowed = {}
    for row in template_doc.allowed_options or []:
        if not row.is_active:
            continue
        allowed.setdefault(row.option_type, {})[row.attribute_link] = row
    return allowed


def _resolve_options(template_doc, options: dict[str, Any]) -> dict[str, Any]:
    options = {_norm_option_key(k): v for k, v in (options or {}).items() if v not in (None, "")}
    allowed = _allowed_option_map(template_doc)
    resolved = {}
    for option_type in OPTION_FIELD_BY_TYPE:
        selected = options.get(option_type)
        if not selected:
            # Use default option if supplied by template.
            defaults = [r for r in (template_doc.allowed_options or []) if r.is_active and r.option_type == option_type and r.is_default]
            selected = defaults[0].attribute_link if defaults else None
        if not selected:
            frappe.throw(_("Missing LED Sheet option: {0}").format(option_type))
        if selected not in allowed.get(option_type, {}):
            frappe.throw(_("Option {0} is not allowed for {1}").format(selected, option_type))
        row = allowed[option_type][selected]
        resolved[option_type] = {"value": selected, "code": row.option_code, "msrp_adder": flt(row.msrp_adder)}
    return resolved


def _get_eligible_drivers(template_name: str) -> list[dict[str, Any]]:
    rows = frappe.get_all(
        "ilL-Rel-Driver-Eligibility",
        filters={"template_type": "ilL-LED-Sheet-Template", "fixture_template": template_name, "is_allowed": 1, "is_active": 1},
        fields=["driver_spec", "priority"],
        order_by="priority asc, modified asc",
    )
    drivers = []
    for row in rows:
        spec = frappe.get_doc("ilL-Spec-Driver", row.driver_spec)
        max_wattage = flt(spec.max_wattage)
        if max_wattage <= 0:
            continue
        drivers.append({"driver_spec": row.driver_spec, "driver_item": spec.item, "max_wattage": max_wattage, "priority": row.priority or 0})
    return sorted(drivers, key=lambda d: (d["max_wattage"], d["priority"]))


def _build_groups(panels_needed: int, watts_per_panel: float, drivers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Thin wrapper translating :class:`ValueError` into ``frappe.throw``."""
    try:
        return build_groups(panels_needed, watts_per_panel, drivers)
    except ValueError as exc:
        frappe.throw(_(str(exc)))


def _item_price(item_code: str | None) -> float:
    if not item_code:
        return 0.0
    from illumenate_lighting.illumenate_lighting.api.tape_neon_pricing import selling_amount
    return selling_amount(item_code, 1)



def _item_name(item_code: str | None) -> str | None:
    if not item_code:
        return None
    return frappe.db.get_value("Item", item_code, "item_name") or item_code


def _hash_payload(payload: dict[str, Any]) -> str:
    return fingerprint(payload)


def _config_hash_payload(template, spec, options: dict[str, Any], coverage_width_ft, coverage_height_ft, include_power_supply: bool) -> dict[str, Any]:
    """Return the canonical configured LED Sheet hash payload used by the DocType controller."""
    return {
        "sheet_template": template,
        "sheet_spec": spec,
        "selected_cct": options.get("CCT"),
        "selected_output_level": options.get("Output Level"),
        "selected_environment_rating": options.get("Environment Rating"),
        "selected_mounting": options.get("Mounting"),
        "selected_finish": options.get("Finish"),
        "coverage_width_ft": coverage_width_ft,
        "coverage_height_ft": coverage_height_ft,
        "include_power_supply": parse_bool(include_power_supply),
    }


def _resolve_dimensions(
    coverage_width_ft,
    coverage_height_ft,
    coverage_width_value,
    coverage_width_unit,
    coverage_height_value,
    coverage_height_unit,
) -> tuple[float, float]:
    """Return coverage (width_ft, height_ft) supporting both the new value/unit
    inputs and the legacy pre-normalized ``coverage_*_ft`` inputs."""
    has_value_inputs = (coverage_width_value not in (None, "")) or (coverage_height_value not in (None, ""))
    if has_value_inputs:
        width_ft = normalize_dimension(coverage_width_value, coverage_width_unit or "ft")
        height_ft = normalize_dimension(coverage_height_value, coverage_height_unit or "ft")
    else:
        width_ft = finite_number(coverage_width_ft, minimum=0, field="coverage width")
        height_ft = finite_number(coverage_height_ft, minimum=0, field="coverage height")
    return width_ft, height_ft


@frappe.whitelist()
def validate_sheet_configuration(template, spec, options=None, coverage_width_ft=0,
    coverage_height_ft=0, schedule_name=None, line_idx=None, coverage_width_value=None,
    coverage_width_unit="ft", coverage_height_value=None, coverage_height_unit="ft",
    include_power_supply=1, dimming_protocol_code=None):
    from illumenate_lighting.illumenate_lighting.portal.rollout import require_configuration

    require_configuration("LED Sheet")
    return _calculate_sheet(template, spec, options, coverage_width_ft, coverage_height_ft,
        schedule_name, line_idx, coverage_width_value, coverage_width_unit,
        coverage_height_value, coverage_height_unit, include_power_supply, dimming_protocol_code)


def _calculate_sheet(
    template,
    spec,
    options=None,
    coverage_width_ft=0,
    coverage_height_ft=0,
    schedule_name=None,
    line_idx=None,
    coverage_width_value=None,
    coverage_width_unit="ft",
    coverage_height_value=None,
    coverage_height_unit="ft",
    include_power_supply=1,
    dimming_protocol_code=None,
    *, commercial=True,
):
    template_doc = frappe.get_doc("ilL-LED-Sheet-Template", template)
    spec_doc = frappe.get_doc("ilL-Spec-LED-Sheet", spec)
    if not template_doc.is_active or not spec_doc.is_active:
        frappe.throw(_("Choose an active LED Sheet template and specification"))
    if spec not in {r.spec for r in template_doc.allowed_specs if r.is_active}:
        frappe.throw(_("LED Sheet spec {0} is not allowed for template {1}").format(spec, template))

    include_ps = _coerce_bool(include_power_supply)
    resolved = _resolve_options(template_doc, _coerce_options(options))
    if spec_doc.cct and resolved["CCT"]["value"] != spec_doc.cct:
        frappe.throw(_("Selected CCT does not match the physical Sheet specification"))
    width, height = _resolve_dimensions(
        coverage_width_ft,
        coverage_height_ft,
        coverage_width_value,
        coverage_width_unit,
        coverage_height_value,
        coverage_height_unit,
    )
    if width <= 0 or height <= 0:
        frappe.throw(_("Coverage width and height must be greater than zero."))

    sheet_width_ft = flt(spec_doc.sheet_width_ft)
    sheet_height_ft = flt(spec_doc.sheet_height_ft)
    if sheet_width_ft <= 0 or sheet_height_ft <= 0:
        frappe.throw(_("LED Sheet spec must have positive sheet width and height."))
    sheet_area = flt(spec_doc.sheet_area_sqft) or (sheet_width_ft * sheet_height_ft)

    try:
        layout = compute_panel_layout(width, height, sheet_width_ft, sheet_height_ft)
    except ValueError as exc:
        frappe.throw(_(str(exc)))
    panels_wide = layout["panels_wide"]
    panels_tall = layout["panels_tall"]
    panels_needed = layout["panels_needed"]

    total_coverage_sqft = width * height
    watts_per_panel = flt(spec_doc.total_sheet_watts) or flt(spec_doc.watts_per_sqft) * sheet_area
    total_system_watts = panels_needed * watts_per_panel
    physical = led_sheet_bundle.resolve({
        "panels_needed": panels_needed, "watts_per_panel": watts_per_panel,
        "include_power_supply": include_ps, "dimming_protocol_code": dimming_protocol_code,
    }, template_doc, spec_doc)
    groups = physical["groups"]

    leader_qty = leader_cable_qty(len(groups))
    jumper_qty = jumper_cable_qty(panels_needed)
    power_supplies = [dict(row) for row in physical["power_supplies"]]
    for ps in power_supplies:
        ps["item_name"] = _item_name(ps.get("driver_item"))

    sku = {SKU_FIELD_BY_TYPE[k]: v["code"] for k, v in resolved.items()}
    sku["sku_series_code"] = template_doc.sku_series_code
    part_number = "-".join([
        part for part in [
            sku.get("sku_series_code") or "",
            sku.get("sku_environment_code") or "",
            sku.get("sku_cct_code") or "",
            sku.get("sku_output_code") or "",
            sku.get("sku_mounting_code") or "",
            sku.get("sku_finish_code") or "",
        ] if part
    ])

    panels_base_msrp = option_msrp = panels_msrp = jumpers_msrp = leaders_msrp = power_supplies_msrp = total_msrp = 0
    if commercial:
        # One commercial bundle includes each physical component exactly once.
        panels_base_msrp = panels_needed * finite_number(template_doc.price_per_sheet_msrp, minimum=0, field="panel MSRP")
        option_msrp = panels_needed * sum(finite_number(v.get("msrp_adder"), minimum=0, field="option MSRP") for v in resolved.values())
        panels_msrp = panels_base_msrp + option_msrp
        jumper_item_price = _item_price(template_doc.jumper_cable_item)
        leader_item_price = _item_price(template_doc.leader_cable_item)
        jumpers_msrp = jumper_qty * jumper_item_price
        leaders_msrp = leader_qty * leader_item_price
        power_supplies_msrp = 0.0
        if include_ps:
            for ps in power_supplies:
                price = _item_price(ps.get("driver_item"))
                ps["unit_price"] = price
                ps["line_total"] = price * int(ps.get("qty") or 0)
                power_supplies_msrp += ps["line_total"]
        total_msrp = panels_msrp + jumpers_msrp + leaders_msrp + power_supplies_msrp

    options_payload = {k: v["value"] for k, v in resolved.items()}
    result = {
        **physical,
        "success": True,
        "template": template,
        "spec": spec,
        "options": options_payload,
        **sku,
        "part_number": part_number,
        "include_power_supply": include_ps,
        "coverage_width_ft": width,
        "coverage_height_ft": height,
        "total_coverage_sqft": total_coverage_sqft,
        "sheet_width_ft": sheet_width_ft,
        "sheet_height_ft": sheet_height_ft,
        "panels_wide": panels_wide,
        "panels_tall": panels_tall,
        "panels_needed": panels_needed,
        # Backward-compatible alias - historically "sheets" == panels.
        "sheets_needed": panels_needed,
        "watts_per_panel": watts_per_panel,
        "total_sheet_watts": watts_per_panel,
        "total_system_watts": total_system_watts,
        "groups": groups,
        "total_groups": len(groups),
        "panels_per_group": [g["sheet_count"] for g in groups],
        "jumper_cable_item": template_doc.jumper_cable_item,
        "jumper_cable_qty": jumper_qty,
        # Legacy field name kept for existing callers.
        "jumper_cables_included": jumper_qty,
        "leader_cable_item": template_doc.leader_cable_item,
        "leader_cable_qty": leader_qty,
        "power_supplies": power_supplies,
        "pricing": {
            "panels_msrp": panels_msrp,
            "sheets_msrp": panels_base_msrp,
            "option_msrp": option_msrp,
            "jumpers_msrp": jumpers_msrp,
            "leaders_msrp": leaders_msrp,
            "power_supplies_msrp": power_supplies_msrp,
            "total_msrp": total_msrp,
            "msrp": total_msrp,
        },
        # Stored per complete bundle; the schedule quantity multiplies it.
        "msrp": total_msrp,
        "total_msrp": total_msrp,
    }
    if not commercial:
        for key in ("pricing", "msrp", "total_msrp"):
            result.pop(key, None)
    return led_sheet_bundle.seal(result, spec_doc)


def _generated_accessory_marker(configured_name: str) -> str:
    return generated_accessory_marker(configured_name)


def _append_accessory_line(schedule, item_code, qty, notes):
    line = schedule.append("lines", {})
    line.manufacturer_type = "ACCESSORY"
    line.accessory_item = item_code
    line.accessory_item_name = _item_name(item_code)
    line.qty = int(qty)
    line.configuration_status = "Configured"
    line.notes = notes
    return line


def _remove_generated_accessory_lines(schedule, markers, keep_line=None):
    """Drop auto-generated LED Sheet accessory rows matching any marker in
    ``markers`` while preserving ``keep_line`` (the panel line) by identity."""
    remaining = [
        line
        for line in schedule.lines
        if line is keep_line
        or not is_generated_accessory_line(line.manufacturer_type, line.notes, markers)
    ]
    schedule.set("lines", remaining)


def _configured_sheet_accessory_specs(doc, bundle_qty: int) -> list[dict[str, Any]]:
    """Recompute the generated accessory line specs for an already-configured LED
    Sheet ``doc`` scaled to ``bundle_qty``, using the panel/group data stored on
    the configured record."""
    if doc.get("bundle_mode") == "Bundle":
        return []
    template_doc = frappe.get_doc("ilL-LED-Sheet-Template", doc.sheet_template)
    panels_needed = cint(doc.sheets_needed)
    groups = [
        {"compatible_driver": g.compatible_driver, "driver_max_wattage": g.driver_max_wattage}
        for g in (doc.groups or [])
    ]
    power_supplies = aggregate_power_supplies(groups)
    for ps in power_supplies:
        ps["item_name"] = _item_name(ps.get("driver_item"))
    return build_accessory_lines(
        configured_name=doc.name,
        bundle_qty=bundle_qty,
        jumper_item=template_doc.jumper_cable_item,
        jumper_qty_per_bundle=jumper_cable_qty(panels_needed),
        leader_item=template_doc.leader_cable_item,
        leader_qty_per_bundle=leader_cable_qty(len(groups)),
        power_supplies=power_supplies,
        include_power_supply=bool(doc.include_power_supply),
    )


def resync_led_sheet_line_accessories(schedule, panel_line, bundle_qty: int):
    """Remove and re-create the generated accessory rows for a single configured
    LED Sheet panel line, scaled to ``bundle_qty``.  Only touches accessory rows
    tagged for this line's configured sheet; other lines are left untouched."""
    configured_name = getattr(panel_line, "configured_led_sheet", None)
    if not configured_name:
        return
    doc = frappe.get_doc("ilL-Configured-LED-Sheet", configured_name)
    if doc.get("bundle_mode") == "Bundle":
        return
    marker = _legacy_line_marker(schedule, panel_line)
    _remove_generated_accessory_lines(schedule, [marker], keep_line=panel_line)
    for spec in _configured_sheet_accessory_specs(doc, bundle_qty):
        _append_accessory_line(schedule, spec["item_code"], spec["qty"], spec["notes"].replace(generated_accessory_marker(configured_name), marker))


def _legacy_line_marker(schedule, line):
    owned = "for LED Sheet line " + line.name
    if any(owned in (row.notes or "") for row in schedule.lines):
        return owned
    configured = line.configured_led_sheet
    marker = generated_accessory_marker(configured)
    siblings = [row for row in schedule.lines if row.get("configured_led_sheet") == configured]
    if len(siblings) > 1 and any(is_generated_accessory_line(row.manufacturer_type, row.notes, [marker]) for row in schedule.lines):
        frappe.throw(_("Legacy Sheet accessories have ambiguous line ownership. Staff must reconcile them before editing this line."))
    for row in schedule.lines:
        if is_generated_accessory_line(row.manufacturer_type, row.notes, [marker]):
            row.notes = row.notes.replace(marker, owned)
    return owned


def remove_sheet_accessories_for_line(schedule, line):
    if line.get("configured_led_sheet"):
        marker = _legacy_line_marker(schedule, line)
        _remove_generated_accessory_lines(schedule, [marker], keep_line=line)


def _apply_multi_line_schedule(schedule, panel_line_idx: int, template, doc, result: dict[str, Any]):
    """Compatibility name: v2 writes a single bundle and preserves buyer notes."""
    if panel_line_idx < 0 or panel_line_idx >= len(schedule.lines):
        frappe.throw(_("Schedule line was not found"))
    line = schedule.lines[panel_line_idx]
    remove_sheet_accessories_for_line(schedule, line)
    line.manufacturer_type = "ILLUMENATE"
    line.product_type = "LED Sheet"
    line.led_sheet_template = template
    line.configured_led_sheet = doc.name
    line.configuration_status = "Configured"
    line.ill_item_code = doc.configured_item
    for field in ("configured_fixture", "configured_tape_neon", "fixture_template", "tape_neon_template", "variant_selections", "accessory_item", "manufacturer_name", "fixture_model_number"):
        line.set(field, None)
    schedule.save(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def save_sheet_configuration(
    template,
    spec,
    options=None,
    coverage_width_ft=0,
    coverage_height_ft=0,
    schedule_name=None,
    line_idx=None,
    coverage_width_value=None,
    coverage_width_unit="ft",
    coverage_height_value=None,
    coverage_height_unit="ft",
    include_power_supply=1,
    dimming_protocol_code=None,
):
    from illumenate_lighting.illumenate_lighting.portal.access import can_edit_schedule
    if frappe.session.user == "Guest":
        frappe.throw(_("Please sign in to save a configuration"), frappe.PermissionError)
    schedule = None
    if schedule_name:
        schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)
        if not can_edit_schedule(schedule):
            frappe.throw(_("No write permission on this schedule"), frappe.PermissionError)
        frappe.db.sql("select name from `tabilL-Project-Fixture-Schedule` where name=%s for update", schedule_name)
        schedule.reload()
        if not can_edit_schedule(schedule):
            frappe.throw(_("No write permission on this schedule"), frappe.PermissionError)
        if schedule.get("is_locked") or schedule.status not in ("DRAFT", "READY"):
            frappe.throw(_("Create an editable schedule version before changing this build"))
        if line_idx in (None, "") or str(line_idx).strip() != str(cint(line_idx)) or not 0 <= cint(line_idx) < len(schedule.lines):
            frappe.throw(_("Select an existing schedule line"))
    frappe.db.savepoint("sheet_save")
    try:
        # Same template lock order serializes hash-based creation across all entry points.
        frappe.db.sql("select name from `tabilL-LED-Sheet-Template` where name=%s for update", template)
        result = validate_sheet_configuration(
            template, spec, options, coverage_width_ft, coverage_height_ft, schedule_name, line_idx,
            coverage_width_value, coverage_width_unit, coverage_height_value, coverage_height_unit, include_power_supply, dimming_protocol_code,
        )
        existing = frappe.db.get_value("ilL-Configured-LED-Sheet", {"config_hash": result["config_hash"]}, "name")
        if existing:
            doc = frappe.get_doc("ilL-Configured-LED-Sheet", existing)
            led_sheet_bundle.snapshot(doc)
        else:
            opts = result["options"]
            fields = {field: result.get(field) for field in (
                "config_hash", "part_number", "include_power_supply", "coverage_width_ft", "coverage_height_ft",
                "total_coverage_sqft", "total_system_watts", "total_groups", "msrp", "groups", "engine_version",
                "bundle_mode", "build_snapshot_json", "jumper_cable_item", "leader_cable_item", "leader_cable_qty",
                "jumper_cables_included", *SKU_FIELD_BY_TYPE.values(), "sku_series_code",
            )}
            fields.update({field: opts.get(key) for key, field in OPTION_FIELD_BY_TYPE.items()})
            doc = frappe.get_doc({"doctype": "ilL-Configured-LED-Sheet", "sheet_template": template, "sheet_spec": spec,
                                  "sheets_needed": result["panels_needed"], "status": "Configured", **fields})
            doc.flags.sheet_engine_write = True
            doc.insert(ignore_permissions=True)
        artifacts = led_sheet_bundle.ensure_artifacts(doc)
        if schedule:
            _apply_multi_line_schedule(schedule, cint(line_idx), template, doc, result)
        return {"success": True, "configured_led_sheet": doc.name, "name": doc.name,
                "config_hash": doc.config_hash, "reused": bool(existing), "total_msrp": result["total_msrp"],
                "item_code": artifacts["item_code"], "bom": artifacts["bom_name"]}
    except Exception:
        frappe.db.rollback(save_point="sheet_save")
        raise
