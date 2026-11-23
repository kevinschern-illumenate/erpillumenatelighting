# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Request for Quotation emails without the supplier portal.

Suppliers reply to the RFQ email with their quotation. ERPNext's own send path
(``send_to_supplier``) would also create a Website User for every new supplier email,
which sends a "set your password" welcome email and adds that user to the Supplier's
Portal Users. It also offers ``portal_link`` ("Submit your Quotation") and
``update_password_link`` ("Set Password") to the message. This class, registered in
``override_doctype_class``, changes only those parts:

- no User is created and Supplier Portal Users are left alone; the supplier row still
  gets a Contact (an existing one for that email, else a new one without a user) so
  the greeting and the reply thread have a name;
- any ``portal_link`` / ``update_password_link`` in the message, including the copy an
  older RFQ took from its Email Template, renders as nothing;
- the RFQ no longer has to be listed in Portal Settings to be sent.

Subject, message, item table, attachments and the print PDF still come from ERPNext.
"""

import re

import frappe

# ERPNext names the controller after the DocType with spaces removed: "RequestforQuotation" (lowercase f).
from erpnext.buying.doctype.request_for_quotation.request_for_quotation import RequestforQuotation

PORTAL_VARIABLES = re.compile(r"\b(?:portal_link|update_password_link)\b")
JINJA_TAGS = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)


def strip_portal_links(message):
	"""Turn the portal-link variables into empty strings inside Jinja tags.

	``{{ portal_link }}`` prints nothing and ``{% if portal_link %}`` is false, so a
	message written for the portal still renders cleanly. Text outside tags is untouched.
	"""
	if not message:
		return message
	return JINJA_TAGS.sub(lambda tag: PORTAL_VARIABLES.sub('""', tag.group(0)), message)


def _contact_for_email(supplier, email):
	"""An existing Contact linked to the Supplier with this email address, if any."""
	parents = frappe.get_all(
		"Contact Email", filters={"parenttype": "Contact", "email_id": email}, pluck="parent"
	)
	for name in parents:
		if frappe.db.exists(
			"Dynamic Link",
			{"parenttype": "Contact", "parent": name, "link_doctype": "Supplier", "link_name": supplier},
		):
			return name
	return None


def supplier_contact(rfq_supplier):
	"""The Contact for an RFQ supplier row without one: found by email, else created without a user."""
	supplier, email = rfq_supplier.get("supplier"), rfq_supplier.get("email_id")
	if not supplier or not email:
		return None
	try:
		existing = _contact_for_email(supplier, email)
		if existing:
			return existing
		contact = frappe.new_doc("Contact")
		contact.first_name = rfq_supplier.get("supplier_name") or supplier
		contact.append("links", {"link_doctype": "Supplier", "link_name": supplier})
		contact.append("email_ids", {"email_id": email, "is_primary": 1})
		contact.insert(ignore_permissions=True)
		return contact.name
	except Exception:
		# The email still goes out; the row just has no Contact.
		frappe.log_error(title="ilL RFQ: supplier contact", message=frappe.get_traceback())
		return None


class ILLRequestForQuotation(RequestforQuotation):
	def get_link(self):
		# Suppliers reply by email; nothing links to the portal.
		return ""

	def update_supplier_contact(self, rfq_supplier, link):
		"""Returns (update_password_link, contact) like ERPNext, without creating a User."""
		if rfq_supplier.get("contact"):
			return "", None
		return "", supplier_contact(rfq_supplier)

	def supplier_rfq_mail(self, data, update_password_link, rfq_link, preview=False):
		field = "mfs_html" if self.use_html else "message_for_supplier"
		original = self.get(field)
		# Only for this render; the saved message is not changed.
		self.set(field, strip_portal_links(original))
		try:
			return super().supplier_rfq_mail(data, "", "", preview)
		finally:
			self.set(field, original)
