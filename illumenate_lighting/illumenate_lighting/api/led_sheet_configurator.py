# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Portal/desk APIs for configuring LED Sheet products."""

import hashlib
import json
import math
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

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


def _build_groups(sheets_needed: int, watts_per_sheet: float, drivers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if sheets_needed <= 0:
        return []
    if watts_per_sheet <= 0:
        frappe.throw(_("LED Sheet spec must have total sheet watts greater than zero."))
    if not drivers:
        frappe.throw(_("No compatible drivers are configured for this LED Sheet template."))
    smallest_sheet_driver = next((d for d in drivers if d["max_wattage"] >= watts_per_sheet), None)
    if not smallest_sheet_driver:
        largest = max(drivers, key=lambda d: d["max_wattage"])
        frappe.throw(_("One LED Sheet ({0}W) exceeds the largest compatible driver ({1}W).").format(watts_per_sheet, largest["max_wattage"]))
    group_capacity = smallest_sheet_driver["max_wattage"]

    groups = []
    current_count = 0
    current_watts = 0.0
    for _idx in range(sheets_needed):
        if current_count and current_watts + watts_per_sheet > group_capacity:
            groups.append(_finish_group(len(groups) + 1, current_count, current_watts, drivers))
            current_count = 0
            current_watts = 0.0
        current_count += 1
        current_watts += watts_per_sheet
    if current_count:
        groups.append(_finish_group(len(groups) + 1, current_count, current_watts, drivers))
    return groups


def _finish_group(group_number: int, sheet_count: int, group_watts: float, drivers: list[dict[str, Any]]) -> dict[str, Any]:
    driver = next((d for d in drivers if d["max_wattage"] >= group_watts), None)
    if not driver:
        frappe.throw(_("No compatible driver can support a {0}W LED Sheet group.").format(group_watts))
    return {
        "group_number": group_number,
        "sheet_count": sheet_count,
        "group_watts": round(group_watts, 3),
        "compatible_driver": driver["driver_item"],
        "driver_spec": driver["driver_spec"],
        "driver_max_wattage": driver["max_wattage"],
        "leader_cable_qty": 1,
    }


def _item_price(item_code: str | None) -> float:
    if not item_code:
        return 0.0
    price = frappe.db.get_value("Item Price", {"item_code": item_code, "selling": 1}, "price_list_rate", order_by="valid_from desc, modified desc")
    return flt(price)


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _config_hash_payload(template, spec, options: dict[str, Any], coverage_width_ft, coverage_height_ft) -> dict[str, Any]:
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
    }


@frappe.whitelist()
def validate_sheet_configuration(template, spec, options=None, coverage_width_ft=0, coverage_height_ft=0, schedule_name=None, line_idx=None):
    template_doc = frappe.get_doc("ilL-LED-Sheet-Template", template)
    spec_doc = frappe.get_doc("ilL-Spec-LED-Sheet", spec)
    if template_doc.allowed_specs and spec not in {r.spec for r in template_doc.allowed_specs if r.is_active}:
        frappe.throw(_("LED Sheet spec {0} is not allowed for template {1}").format(spec, template))

    resolved = _resolve_options(template_doc, _coerce_options(options))
    width = flt(coverage_width_ft)
    height = flt(coverage_height_ft)
    if width <= 0 or height <= 0:
        frappe.throw(_("Coverage width and height must be greater than zero."))
    area = flt(spec_doc.sheet_area_sqft) or flt(spec_doc.sheet_width_ft) * flt(spec_doc.sheet_height_ft)
    if area <= 0:
        frappe.throw(_("LED Sheet spec must have sheet area greater than zero."))
    total_coverage_sqft = width * height
    sheets_needed = int(math.ceil(total_coverage_sqft / area))
    total_sheet_watts = flt(spec_doc.total_sheet_watts) or flt(spec_doc.watts_per_sqft) * area
    total_system_watts = sheets_needed * total_sheet_watts
    groups = _build_groups(sheets_needed, total_sheet_watts, _get_eligible_drivers(template))

    leader_cable_qty = len(groups)
    jumper_cables_included = sheets_needed * 2
    jumper_cables_needed = max(0, (sheets_needed - leader_cable_qty) * 2)
    jumper_cables_extra = max(0, jumper_cables_needed - jumper_cables_included)
    sku = {SKU_FIELD_BY_TYPE[k]: v["code"] for k, v in resolved.items()}
    sku["sku_series_code"] = template_doc.sku_series_code
    part_number = "-".join([sku.get("sku_series_code") or "", sku.get("sku_environment_code") or "", sku.get("sku_cct_code") or "", sku.get("sku_output_code") or "", sku.get("sku_mounting_code") or "", sku.get("sku_finish_code") or ""])

    sheets_msrp = sheets_needed * flt(template_doc.price_per_sheet_msrp)
    option_msrp = sheets_needed * sum(flt(v.get("msrp_adder")) for v in resolved.values())
    leader_cable_msrp = leader_cable_qty * _item_price(template_doc.leader_cable_item)
    extra_jumper_msrp = jumper_cables_extra * _item_price(template_doc.jumper_cable_item)
    msrp = sheets_msrp + option_msrp + leader_cable_msrp + extra_jumper_msrp
    options_payload = {k: v["value"] for k, v in resolved.items()}
    payload = _config_hash_payload(template, spec, options_payload, width, height)

    return {
        "success": True,
        "template": template,
        "spec": spec,
        "options": options_payload,
        **sku,
        "part_number": part_number,
        "coverage_width_ft": width,
        "coverage_height_ft": height,
        "total_coverage_sqft": total_coverage_sqft,
        "sheets_needed": sheets_needed,
        "total_sheet_watts": total_sheet_watts,
        "total_system_watts": total_system_watts,
        "groups": groups,
        "total_groups": len(groups),
        "jumper_cable_item": template_doc.jumper_cable_item,
        "jumper_cables_included": jumper_cables_included,
        "jumper_cables_needed": jumper_cables_needed,
        "jumper_cables_extra": jumper_cables_extra,
        "leader_cable_item": template_doc.leader_cable_item,
        "leader_cable_qty": leader_cable_qty,
        "pricing": {"sheets_msrp": sheets_msrp, "option_msrp": option_msrp, "leader_cable_msrp": leader_cable_msrp, "extra_jumper_msrp": extra_jumper_msrp, "msrp": msrp},
        "msrp": msrp,
        "config_hash": _hash_payload(payload),
    }


@frappe.whitelist()
def save_sheet_configuration(template, spec, options=None, coverage_width_ft=0, coverage_height_ft=0, schedule_name=None, line_idx=None):
    schedule = None
    if schedule_name:
        schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)
        from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
            has_permission,
        )
        if not has_permission(schedule, "write", frappe.session.user):
            frappe.throw(_("No write permission on this schedule"))

    result = validate_sheet_configuration(template, spec, options, coverage_width_ft, coverage_height_ft, schedule_name, line_idx)
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
            "coverage_width_ft": result["coverage_width_ft"],
            "coverage_height_ft": result["coverage_height_ft"],
            "total_coverage_sqft": result["total_coverage_sqft"],
            "sheets_needed": result["sheets_needed"],
            "total_system_watts": result["total_system_watts"],
            "total_groups": result["total_groups"],
            "msrp": result["msrp"],
            "status": "Configured",
            "groups": result["groups"],
        })
        doc.insert(ignore_permissions=True)
    if schedule_name and line_idx not in (None, ""):
        idx = int(line_idx)
        if idx < 1 or idx > len(schedule.lines):
            frappe.throw(_("Line index {0} was not found on schedule {1}").format(line_idx, schedule_name))
        line = schedule.lines[idx - 1]
        line.product_type = "LED Sheet"
        line.led_sheet_template = template
        line.configured_led_sheet = doc.name
        line.configuration_status = "Configured"
        schedule.save(ignore_permissions=True)
    return {"success": True, "configured_led_sheet": doc.name, "name": doc.name, "config_hash": doc.config_hash, "reused": bool(existing)}
