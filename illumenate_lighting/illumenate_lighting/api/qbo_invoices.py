# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
ERPNext -> QuickBooks Online sales invoices: QuickBooks id write-back.

The n8n invoice workflow creates the QuickBooks Invoice for a submitted Sales
Invoice and calls ``receive_invoice_link`` to store the Invoice id (and the
Customer id when n8n had to find or create the customer). A plain REST update
can't do this: ``custom_qbo_id`` can't change on a submitted invoice. Payment
sync (``qbo_sync.receive_payment_event``) matches invoices on this id.

n8n can also send the Invoice's shareable pay-now link (QuickBooks returns it
as ``InvoiceLink`` when the Invoice is read with ``include=invoiceLink``). It is
stored in ``custom_qbo_payment_link`` for email templates. Unlike the id, the
link may be replaced: QuickBooks can issue a new one for the same Invoice.
"""

import json
from urllib.parse import urlparse

import frappe
from frappe.rate_limiter import rate_limit

from illumenate_lighting.illumenate_lighting.api.qbo_bills import _set_qbo_id
from illumenate_lighting.illumenate_lighting.api.qbo_sync import (
	QBOSyncError,
	_commit,
	_record_auth_failure,
	_verify_signature,
)

# Matches the field's column length (see patches/add_qbo_invoice_payment_link.py):
# QuickBooks links run past Data's default 140 characters.
PAYMENT_LINK_LENGTH = 500


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=120, seconds=60)
def receive_invoice_link():
	"""Body: ``{"sales_invoice", "qbo_invoice_id", "customer_qbo_id"?, "qbo_payment_link"?}``, signed like the payment events."""
	raw_body = frappe.request.get_data() or b""
	if not _verify_signature(raw_body):
		_record_auth_failure(raw_body)
		frappe.local.response["http_status_code"] = 401
		return {"success": False, "error": "unauthorized"}
	try:
		payload = json.loads(raw_body.decode("utf-8") or "{}")
		if not isinstance(payload, dict):
			raise ValueError("payload must be a JSON object")
	except (ValueError, UnicodeDecodeError) as e:
		frappe.local.response["http_status_code"] = 400
		return {"success": False, "error": "invalid_json", "message": str(e)}

	frappe.set_user("Administrator")
	try:
		result = link_invoice(payload)
	except QBOSyncError as e:
		frappe.local.response["http_status_code"] = 409 if e.code == "qbo_id_conflict" else 400
		return {"success": False, "error": e.code, "message": e.message}
	_commit()
	result["success"] = True
	return result


def link_invoice(payload):
	sales_invoice = str(payload.get("sales_invoice") or "").strip()
	invoice_id = str(payload.get("qbo_invoice_id") or "").strip()
	if not sales_invoice or not invoice_id:
		raise QBOSyncError("missing_fields", "sales_invoice and qbo_invoice_id are required")
	payment_link = _clean_payment_link(payload.get("qbo_payment_link"))
	_set_qbo_id("Sales Invoice", sales_invoice, invoice_id)
	result = {"sales_invoice": sales_invoice, "qbo_invoice_id": invoice_id}

	customer_id = str(payload.get("customer_qbo_id") or "").strip()
	if customer_id:
		# The Customer comes from the invoice, never from the request.
		customer = frappe.db.get_value("Sales Invoice", sales_invoice, "customer")
		_set_qbo_id("Customer", customer, customer_id)
		result.update(customer=customer, customer_qbo_id=customer_id)

	if payment_link:
		if frappe.db.get_value("Sales Invoice", sales_invoice, "custom_qbo_payment_link") != payment_link:
			frappe.db.set_value(
				"Sales Invoice", sales_invoice, "custom_qbo_payment_link", payment_link, update_modified=False
			)
		result["qbo_payment_link"] = payment_link
	return result


def _clean_payment_link(value):
	"""The link goes into customer emails, so accept only an https link on an Intuit host."""
	link = str(value or "").strip()
	if not link:
		return None
	parsed = urlparse(link)
	host = (parsed.hostname or "").lower()
	if parsed.scheme != "https" or not (host == "intuit.com" or host.endswith(".intuit.com")):
		raise QBOSyncError("invalid_payment_link", "qbo_payment_link must be an https link on intuit.com")
	if len(link) > PAYMENT_LINK_LENGTH:
		raise QBOSyncError(
			"invalid_payment_link", f"qbo_payment_link is longer than {PAYMENT_LINK_LENGTH} characters"
		)
	return link
