# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Server Script: Auto-enroll Newsletter Leads in Email Campaign

This script runs after a CRM Lead is inserted and automatically enrolls
leads from the Webflow newsletter form into the Newsletter Welcome email campaign.

Trigger: After Insert on CRM Lead
Condition: doc.source == "Webflow" and doc.webflow_form_name in ["Newsletter", "Newsletter Signup", "newsletter-signup"]
"""

import frappe
from frappe.utils import today


def auto_enroll_lead_in_newsletter_campaign(doc, method=None):
	"""
	Automatically enroll a new lead in the Newsletter Welcome email campaign.
	
	Args:
		doc: The CRM Lead document that was just created
		method: The hook method name (after_insert)
	"""
	# Only process Webflow leads from newsletter forms
	newsletter_form_names = [
		"Newsletter",
		"Newsletter Signup",
		"newsletter-signup",
		"newsletter_signup",
		"Newsletter Form",
	]
	
	# Check if this is a newsletter signup
	is_newsletter_signup = (
		doc.source == "Webflow" and
		doc.get("webflow_form_name") and
		doc.webflow_form_name.lower().replace("-", " ").replace("_", " ") in [f.lower().replace("-", " ").replace("_", " ") for f in newsletter_form_names]
	)
	
	if not is_newsletter_signup:
		return
	
	# Check if lead has an email (required for email campaigns)
	if not doc.email:
		frappe.log_error(
			title="Newsletter Auto-Enrollment Failed",
			message=f"Lead {doc.name} has no email address. Cannot enroll in email campaign."
		)
		return
	
	# Check if campaign exists
	if not frappe.db.exists("Campaign", "Newsletter Welcome"):
		frappe.log_error(
			title="Newsletter Auto-Enrollment Failed",
			message="Campaign 'Newsletter Welcome' does not exist. Please create it first."
		)
		return
	
	# Check if Email Campaign already exists for this lead (avoid duplicates)
	existing_campaign = frappe.db.exists(
		"Email Campaign",
		{
			"campaign_name": "Newsletter Welcome",
			"email_campaign_for": "Lead",
			"recipient": doc.name,
		}
	)
	
	if existing_campaign:
		return  # Already enrolled
	
	try:
		# Create Email Campaign for this lead
		email_campaign = frappe.new_doc("Email Campaign")
		email_campaign.campaign_name = "Newsletter Welcome"
		email_campaign.email_campaign_for = "Lead"
		email_campaign.recipient = doc.name
		email_campaign.status = "Scheduled"
		email_campaign.start_date = today()
		email_campaign.insert(ignore_permissions=True)
		
		frappe.db.commit()
		
	except Exception as e:
		frappe.log_error(
			title="Newsletter Auto-Enrollment Error",
			message=f"Failed to enroll lead {doc.name} in newsletter campaign: {str(e)}"
		)
