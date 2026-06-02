# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Backfill the ``ilLumenate Lighting`` brand onto already-created configured
Items.

Configured Fixture / LED Tape / LED Neon Items created before brand wiring was
added have no ``brand`` set, so customer-group Pricing Rules keyed on
``Brand = ilLumenate Lighting`` cannot match them. This patch ensures the Brand
master exists and stamps it on the configured Items that lack it.
"""

import frappe

from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
    CONFIGURED_ITEM_GROUP,
    CONFIGURED_NEON_ITEM_GROUP,
    CONFIGURED_TAPE_ITEM_GROUP,
    ILLUMENATE_BRAND,
    _ensure_brand_exists,
)


def execute():
    """Set brand on configured Items that are missing it."""
    _ensure_brand_exists(ILLUMENATE_BRAND)

    item_groups = [
        CONFIGURED_ITEM_GROUP,
        CONFIGURED_TAPE_ITEM_GROUP,
        CONFIGURED_NEON_ITEM_GROUP,
    ]

    items = frappe.get_all(
        "Item",
        filters={"item_group": ["in", item_groups]},
        fields=["name", "brand"],
    )

    updated = 0
    for item in items:
        if item.get("brand"):
            continue
        item_code = item["name"]
        try:
            frappe.db.set_value(
                "Item", item_code, "brand", ILLUMENATE_BRAND, update_modified=False
            )
            updated += 1
        except Exception as e:  # noqa: BLE001
            frappe.log_error(
                title=f"Brand backfill failed for {item_code}",
                message=str(e),
            )

    if updated:
        frappe.db.commit()
