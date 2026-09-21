# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
QuickBooks Online -> ERPNext payment reverse-sync.

n8n receives Intuit webhooks, fetches the full QBO Payment, and POSTs a
normalized payload to ``receive_payment_event``. Every inbound event is logged
to ilL-QBO-Sync-Log before any Payment Entry is touched.

Expected JSON body::

    {
        "qbo_payment_id": "182",
        "event_type": "Create" | "Update" | "Delete" | "Merge",
        "amount": 1234.56,
        "txn_date": "2026-09-15",
        "qbo_invoice_id": "145",
        "qbo_invoice_ids": ["145"],       # optional; >1 entry fails loudly (no multi-invoice allocation)
        "customer_qbo_id": "62",           # optional, logged only
        "merged_from_id": "180",           # Merge only: QBO id that was folded into qbo_payment_id
        "deleted": false                   # true forces event_type=Delete
    }

Auth: ``X-QBO-Signature`` = HMAC-SHA256 hex digest over the raw request body,
keyed with the shared secret (site_config ``qbo_webhook_secret`` or
ilL-QBO-Settings.webhook_secret). Nothing is logged to the DB before the
signature is verified.
"""

import hashlib
import hmac
import json

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, flt, getdate, now_datetime, nowdate

SIGNATURE_HEADER = "X-QBO-Signature"
SYNC_LOG_DOCTYPE = "ilL-QBO-Sync-Log"
SETTINGS_DOCTYPE = "ilL-QBO-Settings"
DEFAULT_PAID_TO_ACCOUNT = "1010 - ilLumenate Lighting WA Trust - ilL"
DEFAULT_MODE_OF_PAYMENT = "QuickBooks Online"
SYNCED_FROM = "QuickBooks Online"
VALID_EVENT_TYPES = ("Create", "Update", "Delete", "Merge")
SAVEPOINT = "qbo_payment_event"


class QBOSyncError(Exception):
	"""Business-rule failure; ``code`` is returned to n8n for branching."""

	def __init__(self, code, message):
		super().__init__(message)
		self.code = code
		self.message = message


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=300, seconds=60)
def receive_payment_event():
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

	# Authenticated by HMAC; run as Administrator so owner/GL entries are not "Guest".
	frappe.set_user("Administrator")

	try:
		event = _normalize_payload(payload)
	except QBOSyncError as e:
		frappe.local.response["http_status_code"] = 400
		return {"success": False, "error": e.code, "message": e.message}

	# Durable record first: Intuit/n8n retry on non-2xx, so the log must survive a downstream failure.
	log = _insert_log(event, payload)
	_commit()

	# An unsaved Single returns None for every field; only an explicit 0 disables the sync.
	sync_enabled = _get_settings().get("sync_enabled")
	if sync_enabled is not None and not cint(sync_enabled):
		_update_log(log, status="Skipped-NoOp", error_message="Sync disabled in ilL-QBO-Settings")
		_commit()
		return {"success": False, "error": "sync_disabled", "log": log.name}

	# No commits between savepoint and the end of _process_event, or the savepoint is lost.
	try:
		frappe.db.savepoint(SAVEPOINT)
		result = _process_event(event, log)
		_commit()
		result.update({"success": True, "log": log.name})
		return result
	except QBOSyncError as e:
		frappe.db.rollback(save_point=SAVEPOINT)
		_update_log(log, status="Failed", error_message=e.message)
		_commit()
		return {"success": False, "error": e.code, "message": e.message, "log": log.name}
	except Exception as e:
		frappe.db.rollback(save_point=SAVEPOINT)
		message = f"{type(e).__name__}: {e}"
		_update_log(log, status="Failed", error_message=message)
		_commit()
		frappe.log_error(
			title=f"QBO payment sync failed ({event['qbo_payment_id']})",
			message=frappe.get_traceback(),
		)
		frappe.local.response["http_status_code"] = 500
		return {"success": False, "error": "processing_failed", "message": message, "log": log.name}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _get_webhook_secret():
	secret = frappe.conf.get("qbo_webhook_secret")
	if secret:
		return str(secret)
	try:
		settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
		return settings.get_password("webhook_secret", raise_exception=False)
	except Exception:
		return None


def _verify_signature(raw_body):
	secret = _get_webhook_secret()
	provided = (frappe.get_request_header(SIGNATURE_HEADER) or "").strip()
	if not secret or not provided:
		return False
	if provided.lower().startswith("sha256="):
		provided = provided[7:]
	expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
	return hmac.compare_digest(expected, provided.lower())


def _record_auth_failure(raw_body):
	# Never log the unauthenticated payload itself; a hash is enough to correlate retries.
	digest = hashlib.sha256(raw_body).hexdigest()[:16]
	ip = getattr(frappe.local, "request_ip", None)
	frappe.log_error(
		title="QBO webhook: signature verification failed",
		message=f"ip={ip} body_sha256_prefix={digest} bytes={len(raw_body)}",
	)


# ---------------------------------------------------------------------------
# Payload handling
# ---------------------------------------------------------------------------


def _normalize_payload(payload):
	qbo_payment_id = str(payload.get("qbo_payment_id") or "").strip()
	if not qbo_payment_id:
		raise QBOSyncError("missing_payment_id", "qbo_payment_id is required")

	event_type = str(payload.get("event_type") or "").strip().title()
	if payload.get("deleted") in (True, 1, "true", "True", "1"):
		event_type = "Delete"
	if event_type not in VALID_EVENT_TYPES:
		raise QBOSyncError("invalid_event_type", f"event_type must be one of {', '.join(VALID_EVENT_TYPES)}")

	invoice_ids = payload.get("qbo_invoice_ids")
	if isinstance(invoice_ids, (list, tuple)):
		invoice_ids = [str(i).strip() for i in invoice_ids if str(i or "").strip()]
	else:
		invoice_ids = []
	qbo_invoice_id = str(payload.get("qbo_invoice_id") or (invoice_ids[0] if invoice_ids else "") or "").strip()
	if qbo_invoice_id and qbo_invoice_id not in invoice_ids:
		invoice_ids.insert(0, qbo_invoice_id)

	txn_date = payload.get("txn_date")
	return {
		"qbo_payment_id": qbo_payment_id,
		"event_type": event_type,
		"amount": flt(payload.get("amount"), 2),
		"txn_date": getdate(txn_date) if txn_date else None,
		"qbo_invoice_id": qbo_invoice_id or None,
		"qbo_invoice_ids": invoice_ids,
		"customer_qbo_id": str(payload.get("customer_qbo_id") or "").strip() or None,
		"merged_from_id": str(payload.get("merged_from_id") or "").strip() or None,
	}


def _process_event(event, log):
	if event["event_type"] == "Delete":
		return _handle_delete(event, log)
	return _handle_upsert(event, log)


def _handle_delete(event, log):
	pe_name = _get_submitted_payment_entry(event["qbo_payment_id"])
	if not pe_name:
		_update_log(
			log,
			status="Skipped-NoOp",
			error_message=f"No submitted Payment Entry with custom_qbo_id={event['qbo_payment_id']}",
		)
		return {"action": "skipped", "payment_entry": None}

	_cancel_payment_entry(pe_name, "Delete", "Cancelled: payment voided/deleted in QuickBooks Online")
	_update_log(log, status="Cancelled", payment_entry=pe_name)
	return {"action": "cancelled", "payment_entry": pe_name}


def _handle_upsert(event, log):
	if len(event["qbo_invoice_ids"]) > 1:
		raise QBOSyncError(
			"multiple_invoices_linked",
			f"QBO Payment {event['qbo_payment_id']} is applied to {len(event['qbo_invoice_ids'])} invoices "
			f"({', '.join(event['qbo_invoice_ids'])}); multi-invoice allocation is not supported — review manually",
		)
	if not event["qbo_invoice_id"]:
		raise QBOSyncError(
			"invoice_not_linked",
			f"QBO Payment {event['qbo_payment_id']} has no linked Invoice (unapplied payment) — review manually",
		)
	if event["amount"] <= 0:
		raise QBOSyncError("invalid_amount", f"amount must be > 0 (got {event['amount']})")

	si = _match_sales_invoice(event["qbo_invoice_id"])
	_update_log(log, status="Matched", sales_invoice=si.name)

	warnings = []
	if abs(flt(si.outstanding_amount) - event["amount"]) > 0.005:
		warnings.append(
			f"QBO amount {event['amount']} differs from invoice outstanding {flt(si.outstanding_amount)}"
		)

	existing = _get_submitted_payment_entry(event["qbo_payment_id"])
	rekeyed_from = None
	if not existing and event["event_type"] == "Merge" and event["merged_from_id"]:
		existing = _get_submitted_payment_entry(event["merged_from_id"])
		rekeyed_from = event["merged_from_id"]
		if existing:
			warnings.append(f"Merge: re-keyed Payment Entry {existing} from QBO id {rekeyed_from} to {event['qbo_payment_id']}")

	if frappe.db.exists("Payment Entry", {"custom_qbo_id": event["qbo_payment_id"], "docstatus": 0}):
		raise QBOSyncError(
			"draft_payment_entry_exists",
			f"A draft Payment Entry already carries custom_qbo_id={event['qbo_payment_id']}; submit or delete it first",
		)

	superseded = None
	if existing:
		if not rekeyed_from and _is_in_sync(existing, event, si.name):
			_update_log(log, status="Skipped-Duplicate", payment_entry=existing, warnings=warnings)
			frappe.db.set_value(
				"Payment Entry",
				existing,
				{"custom_qbo_event_type": event["event_type"], "custom_qbo_last_synced": now_datetime()},
				update_modified=False,
			)
			return {"action": "skipped", "payment_entry": existing}

		_cancel_payment_entry(
			existing,
			event["event_type"],
			f"Cancelled: superseded after QBO {event['event_type']} (amount/date/invoice changed)",
		)
		superseded = existing

	pe = _create_payment_entry(si, event, superseded=superseded)

	if superseded:
		frappe.db.set_value(
			"Payment Entry",
			superseded,
			"custom_qbo_sync_note",
			f"Cancelled: superseded by {pe.name} after QBO {event['event_type']}",
			update_modified=False,
		)

	_update_log(
		log,
		status="Superseded" if superseded else "Created",
		payment_entry=pe.name,
		superseded_payment_entry=superseded,
		warnings=warnings,
	)
	return {
		"action": "recreated" if superseded else "created",
		"payment_entry": pe.name,
		"superseded_payment_entry": superseded,
	}


# ---------------------------------------------------------------------------
# ERPNext document helpers
# ---------------------------------------------------------------------------


def _match_sales_invoice(qbo_invoice_id):
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"custom_qbo_id": qbo_invoice_id},
		fields=["name", "docstatus"],
		order_by="docstatus desc, creation desc",
		limit=2,
	)
	if not rows:
		raise QBOSyncError("invoice_not_matched", f"No Sales Invoice with custom_qbo_id={qbo_invoice_id}")
	submitted = [r for r in rows if r.docstatus == 1]
	if not submitted:
		raise QBOSyncError(
			"invoice_not_submitted",
			f"Sales Invoice {rows[0].name} (custom_qbo_id={qbo_invoice_id}) is not submitted (docstatus={rows[0].docstatus})",
		)
	return frappe.get_doc("Sales Invoice", submitted[0].name)


def _get_submitted_payment_entry(qbo_payment_id):
	if not qbo_payment_id:
		return None
	return frappe.db.get_value(
		"Payment Entry",
		{"custom_qbo_id": qbo_payment_id, "docstatus": 1},
		"name",
		order_by="creation desc",
	)


def _is_in_sync(pe_name, event, sales_invoice_name):
	pe = frappe.db.get_value("Payment Entry", pe_name, ["paid_amount", "posting_date"], as_dict=True)
	if not pe:
		return False
	if abs(flt(pe.paid_amount) - event["amount"]) > 0.005:
		return False
	if event["txn_date"] and getdate(pe.posting_date) != event["txn_date"]:
		return False
	refs = frappe.get_all(
		"Payment Entry Reference",
		filters={"parent": pe_name, "reference_doctype": "Sales Invoice"},
		pluck="reference_name",
	)
	return refs == [sales_invoice_name]


def _cancel_payment_entry(pe_name, event_type, note):
	pe = frappe.get_doc("Payment Entry", pe_name)
	pe.flags.ignore_permissions = True
	pe.cancel()
	frappe.db.set_value(
		"Payment Entry",
		pe_name,
		{
			"custom_qbo_event_type": event_type,
			"custom_qbo_last_synced": now_datetime(),
			"custom_qbo_sync_note": note,
		},
		update_modified=False,
	)


def _create_payment_entry(si, event, superseded=None):
	settings = _get_settings()
	paid_to = settings.get("paid_to_account") or DEFAULT_PAID_TO_ACCOUNT
	mode_of_payment = settings.get("mode_of_payment") or DEFAULT_MODE_OF_PAYMENT
	if not frappe.db.exists("Account", paid_to):
		raise QBOSyncError("paid_to_account_missing", f"Account '{paid_to}' does not exist; set it in ilL-QBO-Settings")
	if mode_of_payment and not frappe.db.exists("Mode of Payment", mode_of_payment):
		mode_of_payment = None

	posting_date = event["txn_date"] or getdate(nowdate())
	amount = event["amount"]

	pe = frappe.new_doc("Payment Entry")
	pe.flags.ignore_permissions = True
	pe.payment_type = "Receive"
	pe.company = si.company
	pe.posting_date = posting_date
	pe.mode_of_payment = mode_of_payment
	pe.party_type = "Customer"
	pe.party = si.customer
	pe.party_name = si.customer_name
	pe.paid_from = si.debit_to
	pe.paid_from_account_currency = frappe.db.get_value("Account", si.debit_to, "account_currency")
	pe.paid_to = paid_to
	pe.paid_to_account_currency = frappe.db.get_value("Account", paid_to, "account_currency")
	pe.paid_amount = amount
	pe.received_amount = amount
	pe.source_exchange_rate = 1
	pe.target_exchange_rate = 1
	pe.reference_no = f"QBO-{event['qbo_payment_id']}"
	pe.reference_date = posting_date
	pe.append(
		"references",
		{
			"reference_doctype": "Sales Invoice",
			"reference_name": si.name,
			"due_date": si.get("due_date"),
			"total_amount": si.grand_total,
			"outstanding_amount": si.outstanding_amount,
			"allocated_amount": amount,
		},
	)
	pe.custom_qbo_id = event["qbo_payment_id"]
	pe.custom_synced_from = SYNCED_FROM
	pe.custom_qbo_event_type = event["event_type"]
	pe.custom_qbo_last_synced = now_datetime()
	pe.custom_qbo_sync_note = (
		f"Recreated after QBO {event['event_type']}; supersedes {superseded}" if superseded else "Created from QBO Payment"
	)
	pe.insert(ignore_permissions=True)
	pe.submit()
	return pe


# ---------------------------------------------------------------------------
# Settings / log helpers
# ---------------------------------------------------------------------------


def _get_settings():
	try:
		return frappe.get_cached_doc(SETTINGS_DOCTYPE).as_dict()
	except Exception:
		return {}


def _insert_log(event, payload):
	log = frappe.new_doc(SYNC_LOG_DOCTYPE)
	log.flags.ignore_permissions = True
	log.qbo_payment_id = event["qbo_payment_id"]
	log.qbo_event_type = event["event_type"]
	log.status = "Received"
	log.received_at = now_datetime()
	log.source_ip = getattr(frappe.local, "request_ip", None)
	log.qbo_amount = event["amount"] or None
	log.qbo_txn_date = event["txn_date"]
	log.qbo_invoice_id = event["qbo_invoice_id"]
	log.customer_qbo_id = event["customer_qbo_id"]
	log.raw_payload = json.dumps(payload, indent=2, default=str)
	log.insert(ignore_permissions=True)
	return log


def _update_log(log, status, **values):
	"""Update log fields in the current transaction; caller decides when to commit."""
	warnings = values.pop("warnings", None)
	if warnings:
		values["warnings"] = "\n".join(warnings)
	values["status"] = status
	frappe.db.set_value(SYNC_LOG_DOCTYPE, log.name, values, update_modified=True)
	log.update(values)


def _commit():
	# Tests run inside a transaction that FrappeTestCase rolls back; don't break that.
	if not frappe.flags.in_test:
		frappe.db.commit()
