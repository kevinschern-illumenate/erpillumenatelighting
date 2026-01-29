# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Patch to add Webflow sync fields to all ilL-Attribute doctypes.

This patch adds the following fields to each attribute doctype:
- webflow_item_id: The Webflow CMS item ID after sync
- webflow_sync_status: Sync status (Never Synced, Pending, Synced, Error)
- webflow_last_synced: Timestamp of last successful sync
- webflow_sync_error: Error message if sync failed
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Add Webflow sync fields to all attribute doctypes."""
    
    # List of all attribute doctypes that need sync fields
    attribute_doctypes = [
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
    ]
    
    # Define the custom fields to add
    custom_fields = {}
    
    for doctype in attribute_doctypes:
        # Check if doctype exists
        if not frappe.db.exists("DocType", doctype):
            continue
        
        custom_fields[doctype] = [
            {
                "fieldname": "webflow_sync_sb",
                "fieldtype": "Section Break",
                "label": "Webflow Sync",
                "collapsible": 1,
                "insert_after": ""  # Will be inserted at end
            },
            {
                "fieldname": "webflow_item_id",
                "fieldtype": "Data",
                "label": "Webflow Item ID",
                "read_only": 1,
                "insert_after": "webflow_sync_sb",
                "description": "The Webflow CMS item ID (populated after sync)"
            },
            {
                "fieldname": "webflow_sync_status",
                "fieldtype": "Select",
                "label": "Sync Status",
                "options": "Never Synced\nPending\nSynced\nError",
                "default": "Never Synced",
                "read_only": 1,
                "insert_after": "webflow_item_id",
                "in_list_view": 0,
                "in_standard_filter": 1
            },
            {
                "fieldname": "webflow_sync_cb",
                "fieldtype": "Column Break",
                "insert_after": "webflow_sync_status"
            },
            {
                "fieldname": "webflow_last_synced",
                "fieldtype": "Datetime",
                "label": "Last Synced",
                "read_only": 1,
                "insert_after": "webflow_sync_cb"
            },
            {
                "fieldname": "webflow_sync_error",
                "fieldtype": "Small Text",
                "label": "Sync Error",
                "read_only": 1,
                "insert_after": "webflow_last_synced",
                "depends_on": "eval:doc.webflow_sync_status=='Error'"
            }
        ]
    
    # Create the custom fields
    create_custom_fields(custom_fields, update=True)
    
    frappe.db.commit()
    
    print(f"Added Webflow sync fields to {len(custom_fields)} doctypes")
