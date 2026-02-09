# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Webflow Sync Events

This module provides document event handlers for automatic Webflow synchronization.
When attribute documents are created or updated, they are automatically marked
for sync to Webflow via n8n workflows.
"""

import frappe
from frappe import _


def on_attribute_update(doc, method):
    """
    Mark attribute document as needing sync when updated.
    
    This is called from doc_events hooks for all attribute doctypes.
    Sets webflow_sync_status to "Pending" so the n8n workflow will pick it up.
    
    Args:
        doc: The document being saved
        method: The event method (after_insert, on_update, on_trash)
    """
    # Skip if document doesn't have webflow sync fields
    meta = frappe.get_meta(doc.doctype)
    if not meta.has_field("webflow_sync_status"):
        return
    
    # Skip if we're in a sync operation (to prevent infinite loops)
    if getattr(doc, "_skip_webflow_sync", False):
        return
    
    # Skip if document is being deleted
    if method == "on_trash":
        # Could optionally queue for deletion from Webflow here
        return
    
    # Mark as pending sync
    try:
        # Use db.set_value to avoid triggering another save event
        frappe.db.set_value(
            doc.doctype,
            doc.name,
            "webflow_sync_status",
            "Pending",
            update_modified=False
        )
    except Exception as e:
        # Log but don't fail the document save
        frappe.log_error(
            message=f"Failed to mark {doc.doctype} {doc.name} for Webflow sync: {str(e)}",
            title="Webflow Sync Event Error"
        )


def on_attribute_insert(doc, method):
    """
    Mark newly created attribute document for sync.
    
    Args:
        doc: The document being inserted
        method: The event method (after_insert)
    """
    on_attribute_update(doc, method)


def on_product_update(doc, method):
    """
    Mark Webflow product as needing sync when updated.
    
    Args:
        doc: The ilL-Webflow-Product document
        method: The event method
    """
    if doc.sync_status != "Pending":
        try:
            frappe.db.set_value(
                doc.doctype,
                doc.name,
                "sync_status",
                "Pending",
                update_modified=False
            )
        except Exception as e:
            frappe.log_error(
                message=f"Failed to mark Webflow product {doc.name} for sync: {str(e)}",
                title="Webflow Sync Event Error"
            )


def on_category_update(doc, method):
    """
    Mark Webflow category as needing sync when updated.
    
    Args:
        doc: The ilL-Webflow-Category document
        method: The event method
    """
    if doc.sync_status != "Pending":
        try:
            frappe.db.set_value(
                doc.doctype,
                doc.name,
                "sync_status",
                "Pending",
                update_modified=False
            )
        except Exception as e:
            frappe.log_error(
                message=f"Failed to mark Webflow category {doc.name} for sync: {str(e)}",
                title="Webflow Sync Event Error"
            )


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
    """
    Generate doc_events configuration for all attribute doctypes.
    
    Returns:
        dict: doc_events configuration
    """
    events = {}
    
    for doctype in ATTRIBUTE_SYNC_DOCTYPES:
        events[doctype] = {
            "after_insert": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_insert",
            "on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_attribute_update",
        }
    
    # Add Webflow-specific doctypes
    events["ilL-Webflow-Product"] = {
        "on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_product_update",
    }
    
    events["ilL-Webflow-Category"] = {
        "on_update": "illumenate_lighting.illumenate_lighting.api.webflow_sync_events.on_category_update",
    }
    
    return events
