# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Idempotent safety net: ensure every active ``ilL-Webflow-Product`` and
``ilL-Webflow-Category`` has at least one row in ``target_brands`` pointing
at the ``is_default=1`` brand.

Runs *after* ``add_brand_sync_state_to_webflow_records`` to catch any docs
that were created between the initial backfill and the dual-write cutover
without picking up a default ``target_brands`` row from the
``on_product_update`` / ``on_category_update`` hooks.
"""

import frappe


def _default_brand_code() -> str | None:
    rows = frappe.get_all(
        "ilL-Webflow-Brand",
        filters={"is_default": 1},
        fields=["brand_code"],
        limit=1,
    )
    if rows:
        return rows[0].get("brand_code")
    rows = frappe.get_all(
        "ilL-Webflow-Brand",
        filters={"is_active": 1},
        fields=["brand_code"],
        limit=1,
    )
    return rows[0].get("brand_code") if rows else None


def _ensure_default_target(doctype: str, default_brand: str) -> int:
    if not frappe.db.exists("DocType", doctype):
        return 0
    meta = frappe.get_meta(doctype)
    if not meta.has_field("target_brands"):
        return 0

    filters = {"is_active": 1} if meta.has_field("is_active") else {}
    names = frappe.get_all(doctype, filters=filters, pluck="name")

    already_targeted = set(
        frappe.get_all(
            "ilL-Child-Webflow-Brand-Target",
            filters={
                "parenttype": doctype,
                "brand": default_brand,
            },
            pluck="parent",
        )
    )

    updated = 0
    for name in names:
        if name in already_targeted:
            continue
        try:
            doc = frappe.get_doc(doctype, name)
            doc.append("target_brands", {"brand": default_brand, "enabled": 1})
            doc.flags._skip_webflow_sync = True
            doc.flags.ignore_permissions = True
            doc.flags.ignore_validate_update_after_submit = True
            doc.save()
            updated += 1
        except Exception as exc:
            frappe.log_error(
                message=f"backfill_default_brand_targets: {doctype} {name} failed: {exc}",
                title="Backfill Default Brand Targets",
            )
    return updated


def execute():
    if not frappe.db.exists("DocType", "ilL-Webflow-Brand"):
        return
    default_brand = _default_brand_code()
    if not default_brand:
        return
    p = _ensure_default_target("ilL-Webflow-Product", default_brand)
    c = _ensure_default_target("ilL-Webflow-Category", default_brand)
    print(f"[backfill_default_brand_targets] {p} products / {c} categories updated")
    frappe.db.commit()
