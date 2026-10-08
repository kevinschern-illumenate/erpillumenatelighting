# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Add the Webflow contact-form fields that webflow_leads writes onto CRM Lead.

They were only listed in the module-level custom_field.json, which Frappe's fixture
sync never reads, so CRM Lead silently dropped the submitted-at time, subject,
message, file URL, project name and products of every Webflow lead.

Free-text fields use Small Text: a Data field rejects values over 140 characters,
which would fail the whole lead insert (Webflow file URLs are often longer).
Existing fields are left as they are, in case a site added them by hand.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	if not frappe.db.exists("DocType", "CRM Lead"):
		return
	create_custom_fields(
		{
			"CRM Lead": [
				{
					"fieldname": "webflow_form_details_section",
					"fieldtype": "Section Break",
					"label": "Webflow Contact Form",
					"insert_after": "webflow_form_data",
					"collapsible": 1,
				},
				{
					"fieldname": "webflow_submitted_at",
					"fieldtype": "Datetime",
					"label": "Webflow Submitted At",
					"insert_after": "webflow_form_details_section",
					"read_only": 1,
				},
				{
					"fieldname": "webflow_contact_form_subject",
					"fieldtype": "Small Text",
					"label": "Webflow Contact Form Subject",
					"insert_after": "webflow_submitted_at",
				},
				{
					"fieldname": "webflow_contact_form_message",
					"fieldtype": "Long Text",
					"label": "Webflow Contact Form Message",
					"insert_after": "webflow_contact_form_subject",
				},
				{
					"fieldname": "webflow_contact_form_file_url",
					"fieldtype": "Small Text",
					"label": "Webflow Contact Form File URL",
					"insert_after": "webflow_contact_form_message",
				},
				{
					"fieldname": "webflow_project_name",
					"fieldtype": "Small Text",
					"label": "Webflow Project Name",
					"insert_after": "webflow_contact_form_file_url",
				},
				{
					"fieldname": "webflow_products_interested",
					"fieldtype": "Long Text",
					"label": "Webflow Products Interested",
					"insert_after": "webflow_project_name",
				},
			],
		},
		update=False,
	)
	frappe.db.commit()
