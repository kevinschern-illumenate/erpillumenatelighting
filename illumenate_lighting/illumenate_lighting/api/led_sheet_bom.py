# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""BOM construction helpers for configured LED Sheet products."""

from typing import Any

import frappe
from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import DEFAULT_UOM


def build_led_sheet_bom_items(configured) -> list[dict[str, Any]]:
    items = []
    spec = frappe.get_doc("ilL-Spec-LED-Sheet", configured.sheet_spec) if configured.sheet_spec else None
    panels_needed = int(configured.sheets_needed or 0)
    total_groups = int(configured.total_groups or 0)

    def _uom(item_code):
        return frappe.db.get_value("Item", item_code, "stock_uom") or DEFAULT_UOM

    # Panels
    if spec and spec.item and panels_needed > 0:
        uom = _uom(spec.item)
        items.append({"item_code": spec.item, "qty": panels_needed, "uom": uom, "stock_uom": uom})
    # Jumpers: two per panel
    if configured.jumper_cable_item and panels_needed > 0:
        uom = _uom(configured.jumper_cable_item)
        items.append({"item_code": configured.jumper_cable_item, "qty": panels_needed * 2, "uom": uom, "stock_uom": uom})
    # Leaders: one per group
    if configured.leader_cable_item and total_groups > 0:
        uom = _uom(configured.leader_cable_item)
        items.append({"item_code": configured.leader_cable_item, "qty": total_groups, "uom": uom, "stock_uom": uom})
    # Power supplies: only when included, aggregated by driver item from group rows
    if int(getattr(configured, "include_power_supply", 0) or 0):
        driver_qty: dict[str, int] = {}
        for group in configured.groups or []:
            driver_item = getattr(group, "compatible_driver", None)
            if driver_item:
                driver_qty[driver_item] = driver_qty.get(driver_item, 0) + 1
        for driver_item, qty in driver_qty.items():
            uom = _uom(driver_item)
            items.append({"item_code": driver_item, "qty": qty, "uom": uom, "stock_uom": uom})
    return items


def create_or_get_led_sheet_bom(configured, item_code: str, skip_if_exists: bool = True) -> dict[str, Any]:
    result = {"success": True, "bom_name": None, "created": False, "skipped": False, "messages": []}
    if getattr(configured, "bom", None) and skip_if_exists and frappe.db.exists("BOM", configured.bom):
        result.update({"bom_name": configured.bom, "skipped": True})
        return result
    existing = frappe.db.get_value("BOM", {"item": item_code, "is_active": 1, "is_default": 1}, "name")
    if existing and skip_if_exists:
        result.update({"bom_name": existing, "skipped": True})
        return result
    bom_items = build_led_sheet_bom_items(configured)
    if not bom_items:
        result["success"] = False
        result["messages"].append({"severity": "error", "text": "No BOM items could be generated for the LED Sheet configured record."})
        return result
    try:
        bom = frappe.get_doc({"doctype": "BOM", "item": item_code, "quantity": 1, "is_active": 1, "is_default": 1, "with_operations": 0, "items": bom_items, "remarks": f"Configured LED Sheet | {configured.name} | PN {configured.part_number or ''}"})
        bom.insert(ignore_permissions=True)
        bom.submit()
        if configured.meta.has_field("bom"):
            configured.bom = bom.name
            configured.save(ignore_permissions=True)
        result.update({"bom_name": bom.name, "created": True})
    except Exception as exc:
        result["success"] = False
        result["messages"].append({"severity": "error", "text": f"Failed to create LED Sheet BOM: {exc!s}"})
    return result
