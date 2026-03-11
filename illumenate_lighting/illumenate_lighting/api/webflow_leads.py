# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Webflow Lead Integration API

This module provides API endpoints for creating Frappe CRM v16 leads from
Webflow form submissions via n8n webhooks.

Architecture:
- Frappe CRM v16: Manages Leads and Deals (Marketing responsibility)
- ERPNext: Manages Customers, Sales Orders, Manufacturing (Sales responsibility)

Workflow:
1. Webflow form → n8n webhook → This API → CRM Lead (Frappe CRM)
2. Marketing nurtures Lead → converts to Deal (Frappe CRM)
3. Deal closed-won → converts to Customer (ERPNext)
4. Sales takes over for orders, manufacturing, fulfillment

Field Mapping (Webflow → Frappe CRM Lead):
- First Name → first_name
- Last Name → last_name
- Email → email
- Campaign ID → webflow_campaign_id
- UTM Source → webflow_utm_source
- UTM Medium → webflow_utm_medium
- UTM Campaign Tag → webflow_utm_campaign
- Submitted At → webflow_submitted_at
- Subject → webflow_contact_form_subject
- Message → webflow_contact_form_message
- File URL → webflow_contact_form_file_url
- Project Name → webflow_project_name
- Products Interested → webflow_products_interested
"""

from typing import Optional, Dict, Any
from datetime import datetime
import json

import frappe
from frappe import _


@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_lead_from_webflow(
    first_name: str,
    last_name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    company_name: Optional[str] = None,
    job_title: Optional[str] = None,
    website: Optional[str] = None,
    source: Optional[str] = "Webflow",
    campaign_id: Optional[str] = None,
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    form_name: Optional[str] = None,
    form_data: Optional[str] = None,
    webflow_form_id: Optional[str] = None,
    webflow_submission_id: Optional[str] = None,
    submitted_at: Optional[str] = None,
    contact_form_subject: Optional[str] = None,
    contact_form_message: Optional[str] = None,
    contact_form_file_url: Optional[str] = None,
    project_name: Optional[str] = None,
    products_interested: Optional[str] = None,
) -> dict:
    """
    Create a CRM Lead from Webflow form submission data.
    
    This endpoint is called by n8n when a Webflow form is submitted.
    The lead is created in Frappe CRM v16 with all relevant tracking data.
    
    Args:
        first_name: Lead's first name (required)
        last_name: Lead's last name
        email: Lead's email address
        phone: Lead's phone number
        company_name: Company/Organization name
        job_title: Lead's job title
        website: Company website
        source: Lead source (defaults to "Webflow")
        campaign_id: Marketing campaign identifier
        utm_source: UTM source parameter
        utm_medium: UTM medium parameter
        utm_campaign: UTM campaign parameter
        form_name: Name of the Webflow form submitted
        form_data: JSON string of additional form fields
        webflow_form_id: Webflow form ID for tracking
        webflow_submission_id: Webflow submission ID for deduplication
        submitted_at: Timestamp when the form was submitted
        contact_form_subject: Subject of the contact form
        contact_form_message: Message from the contact form
        contact_form_file_url: URL of any uploaded file
        project_name: Name of the project
        products_interested: Products the lead is interested in
        
    Returns:
        dict: {
            "success": True/False,
            "lead_name": str (document name if created),
            "message": str,
            "error": str (if error)
        }
    """
    try:
        # Validate required fields
        if not first_name:
            return {
                "success": False,
                "error": "first_name is required",
                "lead_name": None,
            }
        
        # Check for duplicate submission by webflow_submission_id
        if webflow_submission_id:
            existing_lead = frappe.db.get_value(
                "CRM Lead",
                {"webflow_submission_id": webflow_submission_id},
                "name"
            )
            if existing_lead:
                return {
                    "success": True,
                    "lead_name": existing_lead,
                    "message": "Lead already exists for this submission",
                    "duplicate": True,
                }
        
        # Check for duplicate by email (within last 24 hours to avoid spam)
        if email:
            recent_duplicate = frappe.db.sql("""
                SELECT name FROM `tabCRM Lead`
                WHERE email = %(email)s
                AND creation >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                LIMIT 1
            """, {"email": email}, as_dict=True)
            
            if recent_duplicate:
                return {
                    "success": True,
                    "lead_name": recent_duplicate[0].name,
                    "message": "Lead with this email was created recently",
                    "duplicate": True,
                }
        
        # Build lead document data
        lead_data = {
            "doctype": "CRM Lead",
            "first_name": first_name,
            "last_name": last_name or "",
            "email": email,
            "mobile_no": phone,
            "organization": company_name,
            "job_title": job_title,
            "website": website,
            "source": source or "Webflow",
            "status": "New",
        }
        
        # Add UTM tracking fields (webflow_ prefixed custom fields in CRM Lead)
        if campaign_id:
            lead_data["webflow_campaign_id"] = campaign_id
        if utm_source:
            lead_data["webflow_utm_source"] = utm_source
        if utm_medium:
            lead_data["webflow_utm_medium"] = utm_medium
        if utm_campaign:
            lead_data["webflow_utm_campaign"] = utm_campaign
        
        # Add Webflow form tracking fields
        if form_name:
            lead_data["webflow_form_name"] = form_name
        if webflow_form_id:
            lead_data["webflow_form_id"] = webflow_form_id
        if webflow_submission_id:
            lead_data["webflow_submission_id"] = webflow_submission_id
        
        # Add Webflow Form Details fields (new custom fields)
        if submitted_at:
            lead_data["webflow_submitted_at"] = submitted_at
        if contact_form_subject:
            lead_data["webflow_contact_form_subject"] = contact_form_subject
        if contact_form_message:
            lead_data["webflow_contact_form_message"] = contact_form_message
        if contact_form_file_url:
            lead_data["webflow_contact_form_file_url"] = contact_form_file_url
        if project_name:
            lead_data["webflow_project_name"] = project_name
        if products_interested:
            lead_data["webflow_products_interested"] = products_interested
        
        # Parse and store additional form data
        if form_data:
            try:
                additional_data = json.loads(form_data) if isinstance(form_data, str) else form_data
                lead_data["webflow_form_data"] = json.dumps(additional_data, indent=2)
            except (json.JSONDecodeError, TypeError):
                lead_data["webflow_form_data"] = str(form_data)
        
        # Create the lead
        lead_doc = frappe.get_doc(lead_data)
        lead_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        return {
            "success": True,
            "lead_name": lead_doc.name,
            "message": f"Lead created successfully: {lead_doc.name}",
            "duplicate": False,
        }
        
    except frappe.exceptions.DuplicateEntryError as e:
        frappe.db.rollback()
        return {
            "success": False,
            "error": f"Duplicate entry: {str(e)}",
            "lead_name": None,
        }
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            title="Webflow Lead Creation Error",
            message=f"Error creating lead from Webflow: {str(e)}\n\nData: {json.dumps(locals(), default=str)}"
        )
        return {
            "success": False,
            "error": str(e),
            "lead_name": None,
        }


@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_lead_from_webflow_webhook(data: Optional[str] = None) -> dict:
    """
    Alternative endpoint that accepts a JSON payload directly.
    
    This is useful when n8n sends the entire form data as a JSON body.
    
    Args:
        data: JSON string containing all lead fields
        
    Returns:
        dict: Same as create_lead_from_webflow
    """
    try:
        # Get data from request body if not passed as parameter
        if not data:
            data = frappe.request.get_data(as_text=True)
        
        if not data:
            return {
                "success": False,
                "error": "No data provided",
                "lead_name": None,
            }
        
        # Parse JSON data
        if isinstance(data, str):
            lead_info = json.loads(data)
        else:
            lead_info = data
        
        # Map Webflow field names to our API parameters
        mapped_data = _map_webflow_fields(lead_info)
        
        # Call the main creation function
        return create_lead_from_webflow(**mapped_data)
        
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Invalid JSON: {str(e)}",
            "lead_name": None,
        }
    except Exception as e:
        frappe.log_error(
            title="Webflow Webhook Lead Error",
            message=f"Error processing webhook: {str(e)}"
        )
        return {
            "success": False,
            "error": str(e),
            "lead_name": None,
        }


def _map_webflow_fields(webflow_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map Webflow form field names to our API parameters.
    
    Webflow forms can have various field naming conventions.
    This function normalizes them to our expected format.
    
    Args:
        webflow_data: Raw data from Webflow form submission
        
    Returns:
        dict: Mapped data ready for create_lead_from_webflow
    """
    # Common Webflow field name variations → our field names
    field_mapping = {
        # First Name variations
        "first_name": "first_name",
        "firstName": "first_name",
        "First Name": "first_name",
        "first-name": "first_name",
        "fname": "first_name",
        "name": "first_name",  # Fallback if only "name" is provided
        
        # Last Name variations
        "last_name": "last_name",
        "lastName": "last_name",
        "Last Name": "last_name",
        "last-name": "last_name",
        "lname": "last_name",
        "surname": "last_name",
        
        # Email variations
        "email": "email",
        "Email": "email",
        "email_id": "email",
        "emailAddress": "email",
        "email-address": "email",
        
        # Phone variations
        "phone": "phone",
        "Phone": "phone",
        "phone_number": "phone",
        "phoneNumber": "phone",
        "mobile": "phone",
        "telephone": "phone",
        
        # Company variations
        "company": "company_name",
        "Company": "company_name",
        "company_name": "company_name",
        "companyName": "company_name",
        "organization": "company_name",
        "Organisation": "company_name",
        
        # Job Title variations
        "job_title": "job_title",
        "jobTitle": "job_title",
        "title": "job_title",
        "position": "job_title",
        "role": "job_title",
        
        # Website variations
        "website": "website",
        "Website": "website",
        "company_website": "website",
        "url": "website",
        
        # UTM tracking
        "custom_campaign": "campaign_id",
        "campaign_id": "campaign_id",
        "campaignId": "campaign_id",
        "campaign": "campaign_id",
        
        "utm_source": "utm_source",
        "utmSource": "utm_source",
        "source": "utm_source",
        
        "utm_medium": "utm_medium",
        "utmMedium": "utm_medium",
        "medium": "utm_medium",
        
        "utm_campaign": "utm_campaign",
        "utmCampaign": "utm_campaign",
        
        # Webflow metadata
        "_wf_form_id": "webflow_form_id",
        "formId": "webflow_form_id",
        "form_id": "webflow_form_id",
        
        "_wf_submission_id": "webflow_submission_id",
        "submissionId": "webflow_submission_id",
        "submission_id": "webflow_submission_id",
        
        "formName": "form_name",
        "form_name": "form_name",
        
        # Webflow Form Details fields (contact form fields)
        "submitted_at": "submitted_at",
        "submittedAt": "submitted_at",
        "Submitted At": "submitted_at",
        "_wf_submitted_at": "submitted_at",
        
        "subject": "contact_form_subject",
        "Subject": "contact_form_subject",
        "contact_form_subject": "contact_form_subject",
        "contact-subject": "contact_form_subject",
        "form_subject": "contact_form_subject",
        
        "message": "contact_form_message",
        "Message": "contact_form_message",
        "contact_form_message": "contact_form_message",
        "contact-message": "contact_form_message",
        "form_message": "contact_form_message",
        "comments": "contact_form_message",
        "inquiry": "contact_form_message",
        
        "file_url": "contact_form_file_url",
        "file": "contact_form_file_url",
        "attachment": "contact_form_file_url",
        "contact_form_file_url": "contact_form_file_url",
        "file-url": "contact_form_file_url",
        
        "project_name": "project_name",
        "projectName": "project_name",
        "Project Name": "project_name",
        "project-name": "project_name",
        "project": "project_name",
        
        "products_interested": "products_interested",
        "productsInterested": "products_interested",
        "Products Interested": "products_interested",
        "products-interested": "products_interested",
        "interested_in": "products_interested",
        "product_interest": "products_interested",
    }
    
    mapped = {}
    processed_keys = set()
    
    # Map known fields
    for webflow_key, our_key in field_mapping.items():
        if webflow_key in webflow_data and webflow_data[webflow_key]:
            # Don't overwrite if we already have a value for this key
            if our_key not in mapped:
                mapped[our_key] = webflow_data[webflow_key]
            processed_keys.add(webflow_key)
    
    # Collect unmapped fields as additional form data
    additional_data = {}
    for key, value in webflow_data.items():
        if key not in processed_keys and value:
            # Skip internal Webflow fields
            if not key.startswith("_wf_") and key not in ["accept", "g-recaptcha-response"]:
                additional_data[key] = value
    
    if additional_data:
        mapped["form_data"] = json.dumps(additional_data)
    
    return mapped


@frappe.whitelist(allow_guest=True, methods=["GET"])
def health_check() -> dict:
    """
    Health check endpoint for n8n to verify connectivity.
    
    Returns:
        dict: {"status": "ok", "timestamp": ISO timestamp}
    """
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "service": "webflow_leads",
    }


@frappe.whitelist(methods=["GET"])
def get_lead_sources() -> dict:
    """
    Get available lead sources for dropdown configuration.
    
    Requires authentication.
    
    Returns:
        dict: {"success": True, "sources": [...]}
    """
    try:
        # Get sources from CRM Lead Source doctype if it exists
        if frappe.db.exists("DocType", "CRM Lead Source"):
            sources = frappe.get_all(
                "CRM Lead Source",
                fields=["name", "source_name"],
                order_by="source_name asc"
            )
            return {
                "success": True,
                "sources": [s.source_name or s.name for s in sources],
            }
        
        # Fallback to common sources
        return {
            "success": True,
            "sources": [
                "Webflow",
                "Website",
                "Referral",
                "Trade Show",
                "LinkedIn",
                "Cold Call",
                "Email Campaign",
            ],
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "sources": [],
        }
