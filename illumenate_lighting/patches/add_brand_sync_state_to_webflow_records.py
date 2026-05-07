# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Backfill per-brand ``target_brands`` and ``sync_targets`` rows on every
existing ilL-Webflow-Product and ilL-Webflow-Category from their legacy
scalar fields.

For each record:
- Append a ``target_brands`` row (brand=illumenate, enabled=1) if missing.
- Copy legacy scalars (``webflow_item_id``, ``webflow_collection_slug``,
  ``last_synced_at``, ``sync_status``, ``sync_error_message``) into a
  ``sync_targets`` row for the ``illumenate`` brand if no row exists for
  that brand yet.

Idempotent.
"""

import frappe


SCALAR_FIELDS_PRODUCT = [
    "webflow_item_id",
    "webflow_collection_slug",
    "last_synced_at",
    "sync_status",
    "sync_error_message",
]


def _backfill_doctype(doctype: str, default_brand: str) -> int:
    if not frappe.db.exists("DocType", doctype):
        return 0

    meta = frappe.get_meta(doctype)
    if not (meta.has_field("target_brands") and meta.has_field("sync_targets")):
        return 0

    names = frappe.get_all(doctype, pluck="name")
    updated = 0
    for name in names:
        doc = frappe.get_doc(doctype, name)
        dirty = False

        # target_brands
        existing_targets = {row.brand for row in (doc.target_brands or [])}
        if default_brand not in existing_targets:
            doc.append("target_brands", {"brand": default_brand, "enabled": 1})
            dirty = True

        # sync_targets
        existing_sync_brands = {row.brand for row in (doc.sync_targets or [])}
        if default_brand not in existing_sync_brands:
            row_data = {
                "brand": default_brand,
                "sync_status": getattr(doc, "sync_status", None) or "Never Synced",
                "webflow_item_id": getattr(doc, "webflow_item_id", None),
                "webflow_collection_slug": getattr(doc, "webflow_collection_slug", None),
                "last_synced_at": getattr(doc, "last_synced_at", None),
                "sync_error_message": getattr(doc, "sync_error_message", None),
            }
            doc.append("sync_targets", row_data)
            dirty = True

        if dirty:
            doc.flags._skip_webflow_sync = True
            doc.flags.ignore_permissions = True
            doc.flags.ignore_validate_update_after_submit = True
            doc.save()
            updated += 1

    return updated


def execute():
    if not frappe.db.exists("ilL-Webflow-Brand", {"brand_code": "illumenate"}):
        return
    default_brand = "illumenate"
    p = _backfill_doctype("ilL-Webflow-Product", default_brand)
    c = _backfill_doctype("ilL-Webflow-Category", default_brand)
    print(f"[backfill_brand_targets] Updated {p} products / {c} categories")
    frappe.db.commit()
