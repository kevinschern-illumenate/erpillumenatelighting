# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""BOM construction helpers for configured LED Sheet products."""

from typing import Any

import frappe
from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import DEFAULT_UOM


def build_led_sheet_bom_items(configured) -> list[dict[str, Any]]:
    items = []
    spec = frappe.get_doc("ilL-Spec-LED-Sheet", configured.sheet_spec) if configured.sheet_spec else None
    if spec and spec.item and int(configured.sheets_needed or 0) > 0:
        uom = frappe.db.get_value("Item", spec.item, "stock_uom") or DEFAULT_UOM
        items.append({"item_code": spec.item, "qty": int(configured.sheets_needed or 0), "uom": uom, "stock_uom": uom})
    if configured.leader_cable_item and int(configured.leader_cable_qty or 0) > 0:
        uom = frappe.db.get_value("Item", configured.leader_cable_item, "stock_uom") or DEFAULT_UOM
        items.append({"item_code": configured.leader_cable_item, "qty": int(configured.leader_cable_qty or 0), "uom": uom, "stock_uom": uom})
    if configured.jumper_cable_item and int(configured.jumper_cables_extra or 0) > 0:
        uom = frappe.db.get_value("Item", configured.jumper_cable_item, "stock_uom") or DEFAULT_UOM
        items.append({"item_code": configured.jumper_cable_item, "qty": int(configured.jumper_cables_extra or 0), "uom": uom, "stock_uom": uom})
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
