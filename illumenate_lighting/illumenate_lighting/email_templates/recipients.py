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


def fill_supplier_purchasing_email(doc, method=None):
	"""Supplier validate: a blank Purchasing Email takes the primary contact's email."""
	try:
		if doc.meta.has_field(FIELD) and not (doc.get(FIELD) or "").strip():
			email = (doc.get("email_id") or "").strip()
			if email:
				doc.set(FIELD, email)
	except Exception:
		frappe.log_error(title="ilL email: Supplier purchasing email default")


def pick_purchasing_email(supplier_email, primary_contact, contact_emails):
	"""The address a supplier's Purchasing Email should start as, or None.

	``contact_emails`` maps each Contact linked to the supplier to its [(email, is_primary)].
	Order: the Supplier's own email (from its primary contact), the primary contact's
	primary email, then the one address all its contacts share between them. Two
	different addresses and no primary contact is a guess, so it stays blank.
	"""
	email = (supplier_email or "").strip()
	if email:
		return email
	rows = (contact_emails.get(primary_contact) or []) if primary_contact else []
	for address, _is_primary in sorted(rows, key=lambda row: not row[1]):
		if (address or "").strip():
			return address.strip()
	distinct = {}
	for rows in contact_emails.values():
		for address, _primary in rows:
			address = (address or "").strip()
			if address:
				distinct.setdefault(address.lower(), address)
	return next(iter(distinct.values())) if len(distinct) == 1 else None


def backfill_purchasing_emails():
	"""Fill every blank Supplier Purchasing Email it can. Returns {supplier: email} it filled."""
	if not frappe.get_meta("Supplier").has_field(FIELD):
		return {}
	suppliers = frappe.get_all(
		"Supplier",
		fields=["name", "email_id", "supplier_primary_contact", FIELD],
		limit_page_length=0,
	)
	blank = [s for s in suppliers if not (s.get(FIELD) or "").strip()]
	if not blank:
		return {}
	links = frappe.get_all(
		"Dynamic Link",
		filters={
			"parenttype": "Contact",
			"link_doctype": "Supplier",
			"link_name": ["in", [s.name for s in blank]],
		},
		fields=["parent", "link_name"],
		limit_page_length=0,
	)
	contacts = sorted({link.parent for link in links})
	emails = {}
	if contacts:
		for row in frappe.get_all(
			"Contact Email",
			filters={"parenttype": "Contact", "parent": ["in", contacts]},
			fields=["parent", "email_id", "is_primary"],
			limit_page_length=0,
		):
			emails.setdefault(row.parent, []).append((row.email_id, int(row.is_primary or 0)))
	by_supplier = {}
	for link in links:
		by_supplier.setdefault(link.link_name, {})[link.parent] = emails.get(link.parent, [])
	filled = {}
	for supplier in blank:
		email = pick_purchasing_email(
			supplier.get("email_id"),
			supplier.get("supplier_primary_contact"),
			by_supplier.get(supplier.name, {}),
		)
		if email:
			frappe.db.set_value("Supplier", supplier.name, FIELD, email, update_modified=False)
			filled[supplier.name] = email
	return filled
