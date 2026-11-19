# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""RFQ emails ask suppliers to reply by email instead of linking to the portal.

Updates the "ilL - Request for Quotation - Request" Email Template and every draft RFQ
whose message was copied from it (ERPNext copies the template into the RFQ's message
when it is first saved). Only the two shipped lines change, so other edits stay.
A message without them is left alone: the RFQ class override (email_templates/rfq.py)
already renders any portal link as nothing.
"""

import frappe

TEMPLATE = "ilL - Request for Quotation - Request"

REPLACEMENTS = (
	(
		"<p>Please include unit price, MOQ, lead time from order, and freight terms for each item.</p>",
		"<p>Please reply to this email with your quotation, including unit price, lead time from order, "
		"MOQ, and payment terms for each item, plus your freight terms. You're welcome to attach your "
		"quotation as a PDF if you prefer.</p>",
	),
	("{% if portal_link is defined and portal_link %}<p>{{ portal_link }}</p>{% endif %}\n", ""),
	(
		"supplier_name, contact, portal_link and user_fullname come from ERPNext. #}",
		"supplier_name, contact and user_fullname come from ERPNext. Suppliers reply by email: "
		"no portal link, no portal sign-up (email_templates/rfq.py). #}",
	),
)


def reply_by_email(message):
	for old, new in REPLACEMENTS:
		message = message.replace(old, new)
	return message


def execute():
	updated = {"template": False, "drafts": []}
	template = (
		frappe.db.get_value("Email Template", TEMPLATE, "response_html")
		if frappe.db.exists("Email Template", TEMPLATE)
		else None
	)
	if template and reply_by_email(template) != template:
		frappe.db.set_value("Email Template", TEMPLATE, "response_html", reply_by_email(template))
		updated["template"] = True

	for rfq in frappe.get_all(
		"Request for Quotation",
		filters={"docstatus": 0, "email_template": TEMPLATE},
		fields=["name", "mfs_html"],
	):
		message = rfq.mfs_html or ""
		if reply_by_email(message) != message:
			frappe.db.set_value(
				"Request for Quotation", rfq.name, "mfs_html", reply_by_email(message), update_modified=False
			)
			updated["drafts"].append(rfq.name)

	frappe.db.commit()
	return updated
