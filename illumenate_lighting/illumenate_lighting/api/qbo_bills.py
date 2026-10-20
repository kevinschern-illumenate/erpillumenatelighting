# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
ERPNext -> QuickBooks Online supplier bills.

QuickBooks is the payables book of record. A submitted Purchase Invoice is sent,
signed like the inbound payment events, to an n8n webhook that creates the
QuickBooks Bill (matching or creating the Vendor) and calls ``receive_bill_link``
to write the Bill and Vendor ids back. Cancelling the Purchase Invoice asks n8n
to delete the Bill. Payments made against the Bill in QuickBooks come back
through ``qbo_sync.receive_bill_payment_event``.

Nothing is sent until ilL-QBO-Settings has both a Bill Webhook URL and a
"Send Bills Posted On or After" date, so bills already keyed into QuickBooks are
never duplicated. Debit notes (returns) are not sent. An hourly job resends
eligible invoices that still have no QuickBooks id; n8n finds an existing Bill
by its DocNumber (the Purchase Invoice name), so a resend never creates a second Bill.
"""

import hashlib
import hmac
import json

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import add_to_date, cint, flt, getdate, now_datetime

from illumenate_lighting.illumenate_lighting.api.qbo_sync import (
	SIGNATURE_HEADER,
	QBOSyncError,
	_commit,
	_get_settings,
	_get_webhook_secret,
	_record_auth_failure,
	_verify_signature,
)

RETRY_BATCH = 50
# The submit-time send gets this long before the hourly job resends the same invoice.
SETTLE_MINUTES = 15


def _config():
	"""``(webhook_url, first_posting_date)``, or None while bill sending is switched off."""
	settings = _get_settings()
	url = (settings.get("bill_webhook_url") or "").strip()
	from_date = settings.get("bills_from_date")
	if not url or not from_date:
		return None
	return url, getdate(from_date)


def _eligible(doc, config):
	return bool(config) and not cint(doc.get("is_return")) and getdate(doc.posting_date) >= config[1]


def queue_filters():
	"""Extra Portal Operations filters for the unsent-bills queue; None hides it."""
	config = _config()
	if not config:
		return None
	return {"posting_date": [">=", config[1]]}


# ---------------------------------------------------------------------------
# Outbound: Purchase Invoice -> n8n
# ---------------------------------------------------------------------------


def on_submit(doc, method=None):
	_queue(doc, "Submit")


def on_cancel(doc, method=None):
	_queue(doc, "Cancel")


def _queue(doc, event):
	if not _eligible(doc, _config()):
		return
	frappe.enqueue(
		f"{__name__}.send",
		queue="short",
		enqueue_after_commit=True,
		purchase_invoice=doc.name,
		bill_event=event,  # frappe.enqueue reserves the name "event"
	)


def bill_payload(doc, event="Submit"):
	lines = [
		{
			"item_code": row.item_code,
			"description": row.get("item_name") or row.get("description") or row.item_code,
			"qty": flt(row.qty),
			"amount": flt(row.net_amount, 2),
		}
		for row in doc.get("items") or []
	]
	total = flt(doc.get("rounded_total") or doc.grand_total, 2)
	return {
		"event": event,
		"purchase_invoice": doc.name,
		"company": doc.company,
		"qbo_bill_id": doc.get("custom_qbo_id") or None,
		"supplier": doc.supplier,
		"supplier_name": doc.get("supplier_name") or doc.supplier,
		"vendor_qbo_id": frappe.db.get_value("Supplier", doc.supplier, "custom_qbo_id") or None,
		"bill_no": doc.get("bill_no") or None,
		"bill_date": doc.get("bill_date") or None,
		"posting_date": doc.posting_date,
		"due_date": doc.get("due_date") or None,
		"currency": doc.currency,
		"lines": lines,
		# Taxes, charges and rounding, so the Bill total equals what ERPNext expects to pay.
		"adjustment": flt(total - sum(line["amount"] for line in lines), 2),
		"total": total,
	}


def send(purchase_invoice, bill_event="Submit"):
	"""Post one Purchase Invoice event to n8n. Failures are logged; the hourly job resends."""
	config = _config()
	if not config:
		return False
	doc = frappe.get_doc("Purchase Invoice", purchase_invoice)
	if not _eligible(doc, config):
		return False
	secret = _get_webhook_secret()
	if not secret:
		frappe.log_error(title="QBO bill push: no webhook secret", message=purchase_invoice)
		return False
	body = json.dumps(bill_payload(doc, bill_event), sort_keys=True, default=str, separators=(",", ":"))
	signature = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()

	import requests

	try:
		response = requests.post(
			config[0],
			data=body.encode("utf-8"),
			headers={"Content-Type": "application/json", SIGNATURE_HEADER: signature},
			timeout=20,
		)
		response.raise_for_status()
	except Exception:
		frappe.log_error(title=f"QBO bill push failed ({purchase_invoice})", message=frappe.get_traceback())
		return False
	return True


def send_pending():
	"""Hourly: resend submitted Purchase Invoices that QuickBooks has not acknowledged."""
	config = _config()
	if not config:
		return
	names = frappe.get_all(
		"Purchase Invoice",
		filters={
			"docstatus": 1,
			"is_return": 0,
			"custom_qbo_id": ["is", "not set"],
			"posting_date": [">=", config[1]],
			"modified": ["<", add_to_date(now_datetime(), minutes=-SETTLE_MINUTES)],
		},
		pluck="name",
		order_by="posting_date asc, name asc",
		limit=RETRY_BATCH,
	)
	for name in names:
		send(name)


# ---------------------------------------------------------------------------
# Inbound: n8n writes the QuickBooks ids back
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=120, seconds=60)
def receive_bill_link():
	"""Body: ``{"purchase_invoice", "qbo_bill_id", "vendor_qbo_id"?}``, signed like the payment events."""
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
		result = link_bill(payload)
	except QBOSyncError as e:
		frappe.local.response["http_status_code"] = 409 if e.code == "qbo_id_conflict" else 400
		return {"success": False, "error": e.code, "message": e.message}
	_commit()
	result["success"] = True
	return result


def link_bill(payload):
	purchase_invoice = str(payload.get("purchase_invoice") or "").strip()
	bill_id = str(payload.get("qbo_bill_id") or "").strip()
	if not purchase_invoice or not bill_id:
		raise QBOSyncError("missing_fields", "purchase_invoice and qbo_bill_id are required")
	_set_qbo_id("Purchase Invoice", purchase_invoice, bill_id)
	result = {"purchase_invoice": purchase_invoice, "qbo_bill_id": bill_id}

	vendor_id = str(payload.get("vendor_qbo_id") or "").strip()
	if vendor_id:
		# The Supplier comes from the invoice, never from the request.
		supplier = frappe.db.get_value("Purchase Invoice", purchase_invoice, "supplier")
		_set_qbo_id("Supplier", supplier, vendor_id)
		result.update(supplier=supplier, vendor_qbo_id=vendor_id)
	return result


def _set_qbo_id(doctype, name, qbo_id):
	if not name or not frappe.db.exists(doctype, name):
		raise QBOSyncError("not_found", f"{doctype} {name} does not exist")
	current = frappe.db.get_value(doctype, name, "custom_qbo_id")
	if current and current != qbo_id and _inherited_from_original(doctype, name, current):
		current = None
	if current and current != qbo_id:
		raise QBOSyncError(
			"qbo_id_conflict", f"{doctype} {name} is already linked to QuickBooks id {current}, not {qbo_id}"
		)
	if current != qbo_id:
		frappe.db.set_value(doctype, name, "custom_qbo_id", qbo_id, update_modified=False)


def _inherited_from_original(doctype, name, qbo_id):
	"""True when an amended invoice still carries its cancelled original's QuickBooks id."""
	if not frappe.get_meta(doctype).has_field("amended_from"):
		return False
	original = frappe.db.get_value(doctype, name, "amended_from")
	return bool(original) and frappe.db.get_value(doctype, original, "custom_qbo_id") == qbo_id
