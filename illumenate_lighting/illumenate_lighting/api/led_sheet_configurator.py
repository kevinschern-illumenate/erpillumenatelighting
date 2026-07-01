# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Portal/desk APIs for configuring LED Sheet products."""

import hashlib
import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from illumenate_lighting.illumenate_lighting.api.led_sheet_math import (
    aggregate_power_supplies,
    build_groups,
    compute_panel_layout,
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
        try:
            options = json.loads(options)
        except Exception:
            options = {}
    return options or {}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


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
    price = frappe.db.get_value("Item Price", {"item_code": item_code, "selling": 1}, "price_list_rate", order_by="valid_from desc, modified desc")
    return flt(price)


def _item_name(item_code: str | None) -> str | None:
    if not item_code:
        return None
    return frappe.db.get_value("Item", item_code, "item_name") or item_code


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


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
        "include_power_supply": bool(include_power_supply),
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
        width_ft = flt(coverage_width_ft)
        height_ft = flt(coverage_height_ft)
    return width_ft, height_ft


@frappe.whitelist()
def validate_sheet_configuration(
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
):
    template_doc = frappe.get_doc("ilL-LED-Sheet-Template", template)
    spec_doc = frappe.get_doc("ilL-Spec-LED-Sheet", spec)
    if template_doc.allowed_specs and spec not in {r.spec for r in template_doc.allowed_specs if r.is_active}:
        frappe.throw(_("LED Sheet spec {0} is not allowed for template {1}").format(spec, template))

    include_ps = _coerce_bool(include_power_supply)
    resolved = _resolve_options(template_doc, _coerce_options(options))
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
    groups = _build_groups(panels_needed, watts_per_panel, _get_eligible_drivers(template))

    leader_qty = leader_cable_qty(len(groups))
    jumper_qty = jumper_cable_qty(panels_needed)
    power_supplies = aggregate_power_supplies(groups)
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

    # Pricing: the panel line carries panel + option MSRP.  Cables and power
    # supplies become their own accessory schedule lines priced from Item Price.
    panels_base_msrp = panels_needed * flt(template_doc.price_per_sheet_msrp)
    option_msrp = panels_needed * sum(flt(v.get("msrp_adder")) for v in resolved.values())
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
    payload = _config_hash_payload(template, spec, options_payload, width, height, include_ps)

    return {
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
            "msrp": panels_msrp,
        },
        # Stored on the panel line / configured doc.
        "msrp": panels_msrp,
        "total_msrp": total_msrp,
        "config_hash": _hash_payload(payload),
    }


def _generated_accessory_marker(configured_name: str) -> str:
    return f"for LED Sheet {configured_name}"


def _append_accessory_line(schedule, item_code, qty, notes):
    line = schedule.append("lines", {})
    line.manufacturer_type = "ACCESSORY"
    line.accessory_item = item_code
    line.accessory_item_name = _item_name(item_code)
    line.qty = int(qty)
    line.configuration_status = "Configured"
    line.notes = notes
    return line


def _apply_multi_line_schedule(schedule, panel_line_idx: int, template, doc, result: dict[str, Any]):
    """Update the pending LED Sheet line as the panel line and (re)generate the
    jumper / leader / power supply accessory lines."""
    configured_name = doc.name
    marker = _generated_accessory_marker(configured_name)

    # Remove any previously generated accessory lines for this configured sheet
    # so re-saving does not duplicate them.
    remaining = [
        l
        for l in schedule.lines
        if not (l.manufacturer_type == "ACCESSORY" and marker in (l.notes or ""))
    ]
    schedule.set("lines", remaining)

    if panel_line_idx < 0 or panel_line_idx >= len(schedule.lines):
        frappe.throw(_("Line index {0} was not found on schedule {1}").format(panel_line_idx, schedule.name))

    panel_line = schedule.lines[panel_line_idx]
    panel_line.manufacturer_type = "ILLUMENATE"
    panel_line.product_type = "LED Sheet"
    panel_line.led_sheet_template = template
    panel_line.configured_led_sheet = configured_name
    panel_line.configuration_status = "Configured"
    panel_line.qty = int(result["panels_needed"])
    panel_line.notes = (
        f"Configured LED Sheet {configured_name} | {result.get('part_number', '')} | "
        f"{result['panels_wide']}x{result['panels_tall']} panels, "
        f"{result['total_groups']} group(s)"
    )

    jumper_item = result.get("jumper_cable_item")
    if jumper_item and result.get("jumper_cable_qty"):
        _append_accessory_line(schedule, jumper_item, result["jumper_cable_qty"], f"Jumpers {marker}")

    leader_item = result.get("leader_cable_item")
    if leader_item and result.get("leader_cable_qty"):
        _append_accessory_line(schedule, leader_item, result["leader_cable_qty"], f"Leaders {marker}")

    if result.get("include_power_supply"):
        for ps in result.get("power_supplies", []):
            if ps.get("driver_item") and ps.get("qty"):
                _append_accessory_line(schedule, ps["driver_item"], ps["qty"], f"Power supplies {marker}")

    schedule.save(ignore_permissions=True)


@frappe.whitelist()
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
):
    schedule = None
    if schedule_name:
        schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)
        from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
            has_permission,
        )
        if not has_permission(schedule, "write", frappe.session.user):
            frappe.throw(_("No write permission on this schedule"))

    result = validate_sheet_configuration(
        template,
        spec,
        options,
        coverage_width_ft,
        coverage_height_ft,
        schedule_name,
        line_idx,
        coverage_width_value,
        coverage_width_unit,
        coverage_height_value,
        coverage_height_unit,
        include_power_supply,
    )
    include_ps = bool(result["include_power_supply"])
    existing = frappe.db.get_value("ilL-Configured-LED-Sheet", {"config_hash": result["config_hash"]}, "name")
    if existing:
        doc = frappe.get_doc("ilL-Configured-LED-Sheet", existing)
        if flt(doc.msrp) != flt(result["msrp"]):
            doc.msrp = result["msrp"]
            doc.save(ignore_permissions=True)
    else:
        opts = result["options"]
        doc = frappe.get_doc({
            "doctype": "ilL-Configured-LED-Sheet",
            "sheet_template": template,
            "sheet_spec": spec,
            "selected_cct": opts.get("CCT"),
            "selected_output_level": opts.get("Output Level"),
            "selected_environment_rating": opts.get("Environment Rating"),
            "selected_mounting": opts.get("Mounting"),
            "selected_finish": opts.get("Finish"),
            "include_power_supply": 1 if include_ps else 0,
            "coverage_width_ft": result["coverage_width_ft"],
            "coverage_height_ft": result["coverage_height_ft"],
            "total_coverage_sqft": result["total_coverage_sqft"],
            "sheets_needed": result["panels_needed"],
            "total_system_watts": result["total_system_watts"],
            "total_groups": result["total_groups"],
            "msrp": result["msrp"],
            "status": "Configured",
            "groups": result["groups"],
        })
        doc.insert(ignore_permissions=True)

    if schedule_name and line_idx not in (None, ""):
        idx = cint(line_idx)
        _apply_multi_line_schedule(schedule, idx, template, doc, result)

    return {
        "success": True,
        "configured_led_sheet": doc.name,
        "name": doc.name,
        "config_hash": doc.config_hash,
        "reused": bool(existing),
        "total_msrp": result.get("total_msrp"),
    }
