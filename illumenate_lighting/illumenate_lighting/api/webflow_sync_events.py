# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Webflow Sync Events

Document event handlers for automatic Webflow synchronization.

Multi-brand model:
- Products / Categories: per-brand ``sync_targets`` rows. Brands are scoped
  by the parent's ``target_brands`` table. When the parent is updated, every
  targeted+enabled brand row is flipped to ``Pending``.
- Attributes (24 ilL-Attribute-* DocTypes): per-brand
  ``webflow_sync_targets`` rows are flipped to ``Pending`` for every active
  brand (attribute vocabulary is brand-agnostic).
- Legacy scalar fields (``sync_status`` / ``webflow_sync_status``) are
  dual-written during the multi-brand migration window to preserve
  back-compat with the existing single-site n8n workflows.
"""

import frappe
from frappe import _


def _set_per_brand_pending(parent_doctype: str, parent_name: str, brand_code: str,
                            child_table_field: str = "sync_targets") -> None:
    """Set sync_status='Pending' on a per-brand sync row, creating it if missing."""
    rows = frappe.get_all(
        "ilL-Child-Webflow-Sync-State",
        filters={
            "parenttype": parent_doctype,
            "parent": parent_name,
            "brand": brand_code,
        },
        fields=["name", "sync_status"],
        limit=1,
    )
    if rows:
        if rows[0]["sync_status"] != "Pending":
            frappe.db.set_value(
                "ilL-Child-Webflow-Sync-State", rows[0]["name"],
                "sync_status", "Pending", update_modified=False,
            )
        return

    try:
        parent = frappe.get_doc(parent_doctype, parent_name)
        parent.append(child_table_field, {"brand": brand_code, "sync_status": "Pending"})
        parent.flags._skip_webflow_sync = True
        parent.flags.ignore_validate_update_after_submit = True
        parent.save(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(
            message=f"Failed to create per-brand sync row for {parent_doctype} "
                    f"{parent_name} brand={brand_code}: {e}",
            title="Webflow Sync Event Error",
        )


def _list_targeted_brands(doc) -> list:
    """Return [brand_code, ...] for enabled rows in doc.target_brands.

    Falls back to the default brand when target_brands is empty (back-compat
    during migration).
    """
    rows = getattr(doc, "target_brands", None) or []
    targeted = [r.brand for r in rows if getattr(r, "enabled", 1) and r.brand]
    if targeted:
        return targeted
    try:
        from illumenate_lighting.illumenate_lighting.api.webflow_brand import get_default_brand
        default = get_default_brand()
        return [default] if default else []
    except Exception:
        return []


def on_attribute_update(doc, method):
    """Mark attribute document as needing sync for every active brand."""
    meta = frappe.get_meta(doc.doctype)
    has_legacy = meta.has_field("webflow_sync_status")
    has_per_brand = meta.has_field("webflow_sync_targets")
    if not has_legacy and not has_per_brand:
        return

    if getattr(doc, "_skip_webflow_sync", False):
        return

    if method == "on_trash":
        return

    if has_per_brand:
        try:
            from illumenate_lighting.illumenate_lighting.api.webflow_brand import list_active_brands
            for brand_code in list_active_brands():
                _set_per_brand_pending(
                    doc.doctype, doc.name, brand_code,
                    child_table_field="webflow_sync_targets",
                )
        except Exception as e:
            frappe.log_error(
                message=f"Failed per-brand pending mark for {doc.doctype} {doc.name}: {e}",
                title="Webflow Sync Event Error",
            )

    if has_legacy:
        try:
            frappe.db.set_value(
                doc.doctype, doc.name,
                "webflow_sync_status", "Pending",
                update_modified=False,
            )
        except Exception as e:
            frappe.log_error(
                message=f"Failed to mark {doc.doctype} {doc.name} for Webflow sync: {e}",
                title="Webflow Sync Event Error",
            )


def on_attribute_insert(doc, method):
    """Mark newly created attribute document for sync."""
    on_attribute_update(doc, method)


def on_product_update(doc, method):
    """Mark Webflow product as needing sync for every targeted brand."""
    if getattr(doc, "_skip_webflow_sync", False):
        return

    try:
        for brand_code in _list_targeted_brands(doc):
            _set_per_brand_pending(
                "ilL-Webflow-Product", doc.name, brand_code,
                child_table_field="sync_targets",
            )
    except Exception as e:
        frappe.log_error(
            message=f"Failed per-brand pending for Webflow product {doc.name}: {e}",
            title="Webflow Sync Event Error",
        )

    try:
        if getattr(doc, "sync_status", None) != "Pending":
            frappe.db.set_value(
                doc.doctype, doc.name,
                "sync_status", "Pending",
                update_modified=False,
            )
    except Exception as e:
        frappe.log_error(
            message=f"Failed to mark Webflow product {doc.name} for sync: {e}",
            title="Webflow Sync Event Error",
        )


def on_category_update(doc, method):
    """Mark Webflow category as needing sync for every targeted brand."""
    if getattr(doc, "_skip_webflow_sync", False):
        return

    try:
        for brand_code in _list_targeted_brands(doc):
            _set_per_brand_pending(
                "ilL-Webflow-Category", doc.name, brand_code,
                child_table_field="sync_targets",
            )
    except Exception as e:
        frappe.log_error(
            message=f"Failed per-brand pending for Webflow category {doc.name}: {e}",
            title="Webflow Sync Event Error",
        )

    try:
        if getattr(doc, "sync_status", None) != "Pending":
            frappe.db.set_value(
                doc.doctype, doc.name,
                "sync_status", "Pending",
                update_modified=False,
            )
    except Exception as e:
        frappe.log_error(
            message=f"Failed to mark Webflow category {doc.name} for sync: {e}",
            title="Webflow Sync Event Error",
        )


def on_brand_update(doc, method):
    """Invalidate the brand cache when an ilL-Webflow-Brand record changes."""
    try:
        from illumenate_lighting.illumenate_lighting.api import webflow_brand
        webflow_brand.clear_brand_cache()
    except Exception:
        pass


# Mapping of attribute doctypes to their sync functions
ATTRIBUTE_SYNC_DOCTYPES = [
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


def get_attribute_doc_events():
    """Generate doc_events configuration for all attribute doctypes."""
    events = {}
    for doctype in ATTRIBUTE_SYNC_DOCTYPES:
        events[doctype] = {
            "after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
            "on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
        }
    events["ilL-Webflow-Product"] = {
        "on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_product_update",
    }
    events["ilL-Webflow-Category"] = {
        "on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_category_update",
    }
    events["ilL-Webflow-Brand"] = {
        "on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_brand_update",
        "on_trash": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_brand_update",
    }
    return events
