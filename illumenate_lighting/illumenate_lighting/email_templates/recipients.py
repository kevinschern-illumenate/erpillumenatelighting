# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Default supplier email addresses to Supplier "Purchasing Email" (``ill_purchasing_email``).

ERPNext addresses RFQ emails to each supplier row's ``email_id`` and Purchase Order
emails (composer and Notifications) to ``contact_email``. Both come from the supplier's
Contact when one is picked. When that leaves them blank, the Supplier's purchasing email
fills in. A value already there, typed or from a Contact, is never replaced.
"""

import frappe

FIELD = "ill_purchasing_email"


def _purchasing_email(supplier):
	if not supplier or not frappe.get_meta("Supplier").has_field(FIELD):
		return None
	return (frappe.db.get_value("Supplier", supplier, FIELD) or "").strip() or None


def fill_rfq_supplier_emails(doc, method=None):
	"""Request for Quotation validate: blank supplier rows get the purchasing email."""
	try:
		for row in doc.get("suppliers") or []:
			if not row.get("email_id"):
				email = _purchasing_email(row.get("supplier"))
				if email:
					row.email_id = email
	except Exception:
		frappe.log_error(title="ilL email: RFQ supplier email default")


def fill_purchase_order_email(doc, method=None):
	"""Purchase Order validate: a blank contact_email gets the purchasing email."""
	try:
		if doc.docstatus == 0 and not doc.get("contact_email"):
			email = _purchasing_email(doc.get("supplier"))
			if email:
				doc.contact_email = email
	except Exception:
		frappe.log_error(title="ilL email: Purchase Order email default")
