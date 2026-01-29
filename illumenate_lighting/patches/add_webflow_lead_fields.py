# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Patch to add custom fields to CRM Lead (Frappe CRM v16) for Webflow form integration.

Architecture:
- Frappe CRM v16: Leads + Deals (Marketing - lead nurturing)
- ERPNext: Customers + Orders (Sales - fulfillment)

This patch adds to CRM Lead:
- UTM tracking fields (source, medium, campaign)
- Campaign ID field
- Webflow form metadata fields (form name, form ID, submission ID)
- Additional form data JSON field

Run with: bench execute illumenate_lighting.patches.add_webflow_lead_fields.execute
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Add custom fields to CRM Lead for Webflow integration."""
    
    # Check if CRM Lead doctype exists (Frappe CRM v16)
    if not frappe.db.exists("DocType", "CRM Lead"):
        frappe.log_error(
            title="Webflow Lead Fields Patch",
            message="CRM Lead doctype not found. Is Frappe CRM installed?"
        )
        print("CRM Lead doctype not found. Skipping patch.")
        return
    
    custom_fields = {
        "CRM Lead": [
            # UTM Tracking Section
            {
                "fieldname": "webflow_tracking_section",
                "fieldtype": "Section Break",
                "label": "Webflow Marketing Attribution",
                "insert_after": "source",
                "collapsible": 1,
            },
            {
                "fieldname": "webflow_campaign_id",
                "fieldtype": "Data",
                "label": "Campaign ID",
                "insert_after": "webflow_tracking_section",
                "description": "Marketing campaign identifier from Webflow",
            },
            {
                "fieldname": "webflow_utm_source",
                "fieldtype": "Data",
                "label": "UTM Source",
                "insert_after": "webflow_campaign_id",
                "description": "Traffic source (e.g., google, facebook, linkedin)",
            },
            {
                "fieldname": "webflow_utm_column_break",
                "fieldtype": "Column Break",
                "insert_after": "webflow_utm_source",
            },
            {
                "fieldname": "webflow_utm_medium",
                "fieldtype": "Data",
                "label": "UTM Medium",
                "insert_after": "webflow_utm_column_break",
                "description": "Marketing medium (e.g., cpc, email, social)",
            },
            {
                "fieldname": "webflow_utm_campaign",
                "fieldtype": "Data",
                "label": "UTM Campaign",
                "insert_after": "webflow_utm_medium",
                "description": "Campaign name or tag",
            },
            # Webflow Integration Section
            {
                "fieldname": "webflow_form_section",
                "fieldtype": "Section Break",
                "label": "Webflow Form Details",
                "insert_after": "webflow_utm_campaign",
                "collapsible": 1,
            },
            {
                "fieldname": "webflow_form_name",
                "fieldtype": "Data",
                "label": "Form Name",
                "insert_after": "webflow_form_section",
                "read_only": 1,
                "description": "Name of the Webflow form submitted",
            },
            {
                "fieldname": "webflow_form_id",
                "fieldtype": "Data",
                "label": "Webflow Form ID",
                "insert_after": "webflow_form_name",
                "read_only": 1,
            },
            {
                "fieldname": "webflow_form_column_break",
                "fieldtype": "Column Break",
                "insert_after": "webflow_form_id",
            },
            {
                "fieldname": "webflow_submission_id",
                "fieldtype": "Data",
                "label": "Webflow Submission ID",
                "insert_after": "webflow_form_column_break",
                "read_only": 1,
                "unique": 1,
                "description": "Unique ID for deduplication",
            },
            {
                "fieldname": "webflow_form_data",
                "fieldtype": "Code",
                "label": "Additional Form Data",
                "insert_after": "webflow_submission_id",
                "read_only": 1,
                "options": "JSON",
                "description": "Additional fields from the form submission (JSON)",
            },
        ]
    }
    
    create_custom_fields(custom_fields, update=True)
    
    # Add "Webflow" as a lead source if CRM Lead Source doctype exists
    if frappe.db.exists("DocType", "CRM Lead Source"):
        if not frappe.db.exists("CRM Lead Source", "Webflow"):
            try:
                frappe.get_doc({
                    "doctype": "CRM Lead Source",
                    "source_name": "Webflow",
                }).insert(ignore_permissions=True)
                print("Added 'Webflow' as a CRM Lead Source")
            except Exception as e:
                print(f"Could not add Webflow lead source: {e}")
    
    frappe.db.commit()
    print("Successfully added Webflow integration fields to CRM Lead")
