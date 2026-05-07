# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Add a ``webflow_sync_targets`` Table custom field (option=ilL-Child-Webflow-Sync-State)
to all 24 ilL-Attribute-* DocTypes, and backfill a per-brand row for the
``illumenate`` brand from the existing scalar fields.

Existing scalar fields (webflow_item_id, webflow_sync_status,
webflow_last_synced, webflow_sync_error) are kept but marked ``hidden`` so
the per-brand table becomes the authoritative UI surface.

Idempotent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


ATTRIBUTE_DOCTYPES = [
    "ilL-Attribute-CCT",
    "ilL-Attribute-CRI",
    "ilL-Attribute-Certification",
    "ilL-Attribute-Dimming Protocol",
    "ilL-Attribute-Endcap Color",
    "ilL-Attribute-Endcap Style",
    "ilL-Attribute-Environment Rating",
    "ilL-Attribute-Feed-Direction",
    "ilL-Attribute-Finish",
    "ilL-Attribute-IP Rating",
    "ilL-Attribute-Joiner Angle",
    "ilL-Attribute-Joiner System",
    "ilL-Attribute-Lead Time Class",
    "ilL-Attribute-Leader Cable",
    "ilL-Attribute-LED Package",
    "ilL-Attribute-Lens Appearance",
    "ilL-Attribute-Lens Interface Type",
    "ilL-Attribute-Mounting Method",
    "ilL-Attribute-Output Level",
    "ilL-Attribute-Output Voltage",
    "ilL-Attribute-Power Feed Type",
    "ilL-Attribute-Pricing Class",
    "ilL-Attribute-SDCM",
    "ilL-Attribute-Series",
]


def _add_table_field():
    """Create webflow_sync_targets Table custom field on every attribute doctype."""
    if not frappe.db.exists("DocType", "ilL-Child-Webflow-Sync-State"):
        return

    custom_fields = {}
    for dt in ATTRIBUTE_DOCTYPES:
        if not frappe.db.exists("DocType", dt):
            continue
        custom_fields[dt] = [
            {
                "fieldname": "webflow_sync_targets_sb",
                "fieldtype": "Section Break",
                "label": "Per-Brand Webflow Sync",
                "collapsible": 1,
                "insert_after": "webflow_sync_error",
            },
            {
                "fieldname": "webflow_sync_targets",
                "fieldtype": "Table",
                "label": "Webflow Sync Targets",
                "options": "ilL-Child-Webflow-Sync-State",
                "insert_after": "webflow_sync_targets_sb",
                "description": "Per-brand Webflow CMS sync state (authoritative).",
            },
        ]
    if custom_fields:
        create_custom_fields(custom_fields, ignore_validate=True, update=True)


def _hide_legacy_scalars():
    """Mark legacy scalar custom fields hidden=1 (they remain for back-compat)."""
    legacy_fields = [
        "webflow_sync_sb",
        "webflow_item_id",
        "webflow_sync_status",
        "webflow_last_synced",
        "webflow_sync_error",
    ]
    for dt in ATTRIBUTE_DOCTYPES:
        for fieldname in legacy_fields:
            cf = frappe.db.get_value(
                "Custom Field",
                {"dt": dt, "fieldname": fieldname},
                "name",
            )
            if cf:
                frappe.db.set_value("Custom Field", cf, "hidden", 1)


def _backfill_per_brand_rows(default_brand: str):
    """Copy legacy scalar fields into a per-brand sync row."""
    for dt in ATTRIBUTE_DOCTYPES:
        if not frappe.db.exists("DocType", dt):
            continue
        meta = frappe.get_meta(dt)
        if not meta.has_field("webflow_sync_targets"):
            continue

        names = frappe.get_all(dt, pluck="name")
        for name in names:
            existing = frappe.db.exists(
                "ilL-Child-Webflow-Sync-State",
                {"parenttype": dt, "parent": name, "brand": default_brand},
            )
            if existing:
                continue

            doc_data = frappe.db.get_value(
                dt, name,
                ["webflow_item_id", "webflow_sync_status", "webflow_last_synced", "webflow_sync_error"],
                as_dict=True,
            )
            if not doc_data:
                continue

            # Only backfill if there is something meaningful to copy.
            if not (doc_data.get("webflow_item_id") or
                    (doc_data.get("webflow_sync_status") and doc_data["webflow_sync_status"] != "Never Synced")):
                continue

            doc = frappe.get_doc(dt, name)
            doc.append("webflow_sync_targets", {
                "brand": default_brand,
                "sync_status": doc_data.get("webflow_sync_status") or "Never Synced",
                "webflow_item_id": doc_data.get("webflow_item_id"),
                "last_synced_at": doc_data.get("webflow_last_synced"),
                "sync_error_message": doc_data.get("webflow_sync_error"),
            })
            doc.flags._skip_webflow_sync = True
            doc.flags.ignore_permissions = True
            doc.save()


def execute():
    _add_table_field()
    if frappe.db.exists("ilL-Webflow-Brand", {"brand_code": "illumenate"}):
        _backfill_per_brand_rows("illumenate")
    _hide_legacy_scalars()
    frappe.db.commit()
