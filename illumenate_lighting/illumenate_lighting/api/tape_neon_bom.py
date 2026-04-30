# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""BOM construction helpers for configured LED Tape and LED Neon products.

The fixture-side equivalents live in
``illumenate_lighting.illumenate_lighting.api.manufacturing_generator``
(``build_fixture_bom_items`` / ``_create_or_get_bom``).  This module mirrors
that shape for tape & neon configured records so the Quotation/Sales-Order
"Build / Add Configured Product" tools can preview and persist BOMs without
needing the linear-fixture pipeline.
"""

from typing import Any

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
    DEFAULT_UOM,
)


MM_PER_FOOT = 304.8
MM_PER_INCH = 25.4


def build_tape_neon_bom_items(configured) -> list[dict[str, Any]]:
    """Build BOM rows for a configured tape/neon record without persisting.

    Roles included:
        1. Tape item — total manufacturable length in feet
        2. Leader cable — total leader/jumper length in inches
        3. Mounting accessory (when ``include_mounting_accessory``)

    Drivers are NOT added here: the tape/neon configured record does not yet
    persist a driver plan child table.  Power-supply attachment for tape/neon
    is handled at the Quotation/Sales-Order row level via
    ``_apply_artifact_to_row``.

    Args:
        configured: ``ilL-Configured-Tape-Neon`` document (loaded)

    Returns:
        List of dicts with keys ``item_code``, ``qty``, ``uom``, ``stock_uom``.
    """
    bom_items: list[dict[str, Any]] = []
    is_neon = (configured.product_category or "").strip() == "LED Neon"

    # ── Role 1: Tape item ─────────────────────────────────────────────
    if configured.tape_item:
        if is_neon and getattr(configured, "segments", None):
            total_mm = sum(
                float(seg.manufacturable_length_mm or 0) for seg in configured.segments
            )
        else:
            total_mm = float(configured.manufacturable_length_mm or 0)
        if total_mm > 0:
            tape_uom = (
                frappe.db.get_value("Item", configured.tape_item, "stock_uom")
                or "Foot"
            )
            uom_lower = tape_uom.lower()
            if uom_lower in ("foot", "ft"):
                qty = round(total_mm / MM_PER_FOOT, 2)
            elif uom_lower in ("meter", "metre", "m"):
                qty = round(total_mm / 1000.0, 3)
            elif uom_lower in ("inch", "in"):
                qty = round(total_mm / MM_PER_INCH, 2)
            else:
                qty = round(total_mm / MM_PER_FOOT, 2)
                tape_uom = "Foot"
            bom_items.append({
                "item_code": configured.tape_item,
                "qty": qty,
                "uom": tape_uom,
                "stock_uom": tape_uom,
            })

    # ── Role 2: Leader cable ──────────────────────────────────────────
    leader_item = configured.leader_cable_item
    if leader_item:
        if is_neon and getattr(configured, "segments", None):
            total_lead_in = 0.0
            for seg in configured.segments:
                total_lead_in += float(getattr(seg, "start_lead_length_inches", 0) or 0)
                total_lead_in += float(getattr(seg, "end_cable_length_inches", 0) or 0)
        else:
            total_lead_in = float(configured.lead_length_inches or 0)
        if total_lead_in > 0:
            leader_uom = (
                frappe.db.get_value("Item", leader_item, "stock_uom") or "Inch"
            )
            bom_items.append({
                "item_code": leader_item,
                "qty": round(total_lead_in, 2),
                "uom": leader_uom,
                "stock_uom": leader_uom,
            })

    # ── Role 3: Mounting accessory (post-config selection) ────────────
    if (
        getattr(configured, "include_mounting_accessory", 0)
        and configured.mounting_accessory_item
    ):
        macc_qty = int(configured.mounting_accessory_qty or 0)
        if macc_qty > 0:
            bom_items.append({
                "item_code": configured.mounting_accessory_item,
                "qty": macc_qty,
                "uom": DEFAULT_UOM,
                "stock_uom": DEFAULT_UOM,
            })

    return bom_items


def create_or_get_tape_neon_bom(
    configured,
    item_code: str,
    skip_if_exists: bool = True,
) -> dict[str, Any]:
    """Create or retrieve a BOM for a configured tape/neon Item.

    Mirrors ``manufacturing_generator._create_or_get_bom`` for fixtures.

    Args:
        configured: ``ilL-Configured-Tape-Neon`` document
        item_code: Configured item code (target ``BOM.item``)
        skip_if_exists: When ``True`` (default), reuse any active default BOM
            already linked to ``configured.bom`` or to ``item_code``.

    Returns:
        ``{"success", "bom_name", "created", "skipped", "messages"}``
    """
    result: dict[str, Any] = {
        "success": True,
        "bom_name": None,
        "created": False,
        "skipped": False,
        "messages": [],
    }

    if configured.bom and skip_if_exists and frappe.db.exists("BOM", configured.bom):
        result["bom_name"] = configured.bom
        result["skipped"] = True
        result["messages"].append({
            "severity": "info",
            "text": f"Using existing BOM: {configured.bom}",
        })
        return result

    existing = frappe.db.get_value(
        "BOM",
        {"item": item_code, "is_active": 1, "is_default": 1},
        "name",
    )
    if existing and skip_if_exists:
        result["bom_name"] = existing
        result["skipped"] = True
        result["messages"].append({
            "severity": "info",
            "text": f"Using existing default BOM: {existing}",
        })
        return result

    bom_items = build_tape_neon_bom_items(configured)
    if not bom_items:
        result["success"] = False
        result["messages"].append({
            "severity": "error",
            "text": "No BOM items could be generated for the tape/neon configured record.",
        })
        return result

    try:
        bom_doc = frappe.get_doc({
            "doctype": "BOM",
            "item": item_code,
            "quantity": 1,
            "is_active": 1,
            "is_default": 1,
            "with_operations": 0,
            "items": bom_items,
            "remarks": _build_tape_neon_bom_remarks(configured),
        })
        bom_doc.insert(ignore_permissions=True)
        bom_doc.submit()

        configured.bom = bom_doc.name
        configured.save(ignore_permissions=True)

        result["bom_name"] = bom_doc.name
        result["created"] = True
        result["messages"].append({
            "severity": "info",
            "text": f"Created BOM: {bom_doc.name} with {len(bom_items)} items",
        })
    except Exception as e:
        result["success"] = False
        result["messages"].append({
            "severity": "error",
            "text": f"Failed to create BOM: {e!s}",
        })

    return result


def _build_tape_neon_bom_remarks(configured) -> str:
    """Short BOM remarks line for tape/neon."""
    parts = [
        f"Configured {configured.product_category or 'LED Tape'}",
        configured.name,
    ]
    if configured.part_number:
        parts.append(f"PN {configured.part_number}")
    if configured.manufacturable_length_mm:
        length_in = (configured.manufacturable_length_mm or 0) / MM_PER_INCH
        parts.append(f'{length_in:.1f}"')
    return " | ".join(parts)
