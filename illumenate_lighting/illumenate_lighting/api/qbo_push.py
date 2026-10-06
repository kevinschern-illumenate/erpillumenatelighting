# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
ERPNext -> QuickBooks Online push.

What is pushed (each can be switched off in ilL-QBO-Settings):

- Sales Invoice submit  -> QBO Invoice (customer found or created first)
- Credit note submit    -> QBO CreditMemo, then applied to the original invoice
                           with a $0 Payment when ERPNext reduced that invoice
- Sales Invoice cancel  -> QBO Invoice voided / CreditMemo deleted
- Payment Entry submit  -> QBO Payment linked to the QBO invoices
- Payment Entry cancel  -> QBO Payment voided
- Customer save         -> QBO Customer contact/address update (linked customers only)

Every push is an ilL-QBO-Push-Log row (an outbox). Doc events only insert the
row and enqueue a job after commit, so a QuickBooks outage never blocks a
submit. Jobs for one document run in creation order, retry with backoff, and
use deterministic Intuit ``requestid`` values plus DocNumber / PrivateNote
lookups so a retry never creates a second QBO record.

Loop guards: Payment Entries that came from QuickBooks (custom_synced_from =
"QuickBooks Online") and anything done while the inbound payment sync is
running (frappe.flags.in_qbo_inbound_sync) are never pushed back.
"""

import hashlib
import json

import frappe
from frappe.utils import add_to_date, cint, flt, getdate, now_datetime, strip_html_tags

from illumenate_lighting.illumenate_lighting.api.qbo_client import QBOClient, QBOError, escape_query_value

PUSH_LOG = "ilL-QBO-Push-Log"
SETTINGS_DOCTYPE = "ilL-QBO-Settings"
SYNCED_FROM_ERPNEXT = "ERPNext"
SYNCED_FROM_QBO = "QuickBooks Online"
LINKED = "Linked to QuickBooks Online"

OPEN_STATUSES = ("Queued", "Processing", "Failed")
DONE_STATUSES = ("Synced", "Skipped")
BACKOFF_MINUTES = (2, 5, 15, 30, 60, 120, 240, 480)
MAX_ATTEMPTS = len(BACKOFF_MINUTES)
STALE_PROCESSING_MINUTES = 15
SCHEDULER_BATCH = 20
QBO_DOC_NUMBER_MAX = 21
DEFAULT_ITEM_NAME = "ERPNext Sales"
DEFAULT_TAX_CODE = "NON"
CACHE_TTL_SECONDS = 6 * 3600

INVOICE_NOTE = "ERPNext Sales Invoice"
PAYMENT_NOTE = "ERPNext Payment Entry"
CUSTOMER_NOTE = "ERPNext Customer"
MANAGER_ROLES = ("System Manager", "Accounts Manager")


class PushSkip(Exception):
	"""Nothing to do; the log ends as Skipped."""


class PushWait(Exception):
	"""A dependency (e.g. the invoice) isn't in QuickBooks yet; retry later."""


class PushError(Exception):
	"""Needs a person to fix data or settings; no automatic retry."""


# ---------------------------------------------------------------------------
# Doc events (must never raise: a QuickBooks problem must not block a submit)
# ---------------------------------------------------------------------------


def on_sales_invoice_submit(doc, method=None):
	flag = "push_credit_notes" if cint(doc.get("is_return")) else "push_sales_invoices"
	_safe_auto_enqueue(doc, "Create", flag, doc.get("posting_date"))


def on_sales_invoice_cancel(doc, method=None):
	if frappe.flags.in_qbo_inbound_sync:
		return
	if doc.get("custom_qbo_id") or _has_log(doc.doctype, doc.name, "Create"):
		_safe_auto_enqueue(doc, "Void", None, None)


def on_payment_entry_submit(doc, method=None):
	if frappe.flags.in_qbo_inbound_sync or doc.get("custom_synced_from") == SYNCED_FROM_QBO:
		return
	if doc.get("payment_type") != "Receive" or doc.get("party_type") != "Customer":
		return
	_safe_auto_enqueue(doc, "Create", "push_payments", doc.get("posting_date"))


def on_payment_entry_cancel(doc, method=None):
	if frappe.flags.in_qbo_inbound_sync:
		return
	if doc.get("custom_synced_from") == SYNCED_FROM_QBO:
		if doc.get("custom_qbo_id") and _push_enabled(_settings()):
			_safe_comment(
				doc,
				f"Cancelled in ERPNext only. This payment came from QuickBooks (Id {doc.custom_qbo_id}); "
				"void it in QuickBooks as well.",
			)
		return
	if doc.get("custom_qbo_id") or _has_log(doc.doctype, doc.name, "Create"):
		_safe_auto_enqueue(doc, "Void", None, None)


def on_customer_update(doc, method=None):
	if frappe.flags.in_qbo_inbound_sync or not doc.get("custom_qbo_id"):
		return
	fields = ("customer_name", "customer_type", "email_id", "mobile_no", "customer_primary_address")
	try:
		changed = any(doc.has_value_changed(f) for f in fields)
	except Exception:
		changed = False
	if changed:
		_safe_auto_enqueue(doc, "Update", "push_customer_updates", None)


def _safe_auto_enqueue(doc, action, flag, posting_date):
	try:
		settings = _settings()
		if not _push_enabled(settings, flag):
			return
		start = settings.get("push_start_date")
		if posting_date and start and getdate(posting_date) < getdate(start):
			return
		enqueue_push(doc.doctype, doc.name, action)
	except Exception:
		frappe.log_error(
			title=f"QBO push: could not queue {doc.doctype} {doc.name}", message=frappe.get_traceback()
		)


def _safe_comment(doc, text):
	try:
		doc.add_comment("Comment", text)
	except Exception:
		pass


# ---------------------------------------------------------------------------
# Outbox
# ---------------------------------------------------------------------------


def enqueue_push(doctype, name, action, reset=False, process_now=False):
	"""Queue (or re-queue) one push and return the log name."""
	existing = frappe.db.get_value(
		PUSH_LOG,
		{
			"reference_doctype": doctype,
			"reference_name": name,
			"action": action,
			"status": ["in", ("Queued", "Failed")],
		},
		"name",
		order_by="creation desc",
	)
	if existing:
		values = {"status": "Queued", "next_attempt_at": now_datetime()}
		if reset:
			values["attempts"] = 0
		frappe.db.set_value(PUSH_LOG, existing, values, update_modified=True)
		log_name = existing
	else:
		log = frappe.get_doc(
			{
				"doctype": PUSH_LOG,
				"reference_doctype": doctype,
				"reference_name": name,
				"action": action,
				"status": "Queued",
				"attempts": 0,
				# The job below normally runs first; the scheduler is the fallback.
				"next_attempt_at": add_to_date(now_datetime(), minutes=2),
			}
		)
		log.insert(ignore_permissions=True)
		log_name = log.name

	if process_now:
		process_log(log_name)
	else:
		frappe.enqueue(
			"illumenate_lighting.illumenate_lighting.api.qbo_push.process_log",
			queue="short",
			log_name=log_name,
			enqueue_after_commit=True,
		)
	return log_name


def process_log(log_name):
	"""Run one push. Safe to call twice concurrently: a per-document lock and a status re-check guard it."""
	log = _load_log(log_name)
	if not log or log.status in DONE_STATUSES:
		return log.status if log else None

	lock_key = _lock_key(log.reference_doctype, log.reference_name)
	if not _acquire_lock(lock_key):
		# Another worker owns this document; next_attempt_at is already set, so the
		# scheduler comes back. Writing here could overwrite that worker's final status.
		return "Queued"
	try:
		log = _load_log(log_name)
		if log.status in DONE_STATUSES:
			return log.status

		blocker = _earlier_open_log(log)
		if blocker:
			dead = blocker.status == "Failed" and not blocker.next_attempt_at
			_defer(
				log,
				f"Waiting for {blocker.name} ({blocker.action}, {blocker.status}) to finish first",
				minutes=30 if dead else 2,
			)
			return "Queued"

		attempts = cint(log.attempts) + 1
		frappe.db.set_value(
			PUSH_LOG,
			log.name,
			{"status": "Processing", "attempts": attempts, "last_attempt_at": now_datetime()},
		)
		_commit()
		return _run_handler(log, attempts)
	finally:
		_release_lock(lock_key)


def _run_handler(log, attempts):
	handler = HANDLERS.get((log.reference_doctype, log.action))
	try:
		if not handler:
			raise PushError(f"No QuickBooks handler for {log.reference_doctype} / {log.action}")
		result = handler(log, QBOClient()) or {}
	except PushSkip as e:
		_finish(log, "Skipped", message=str(e))
		return "Skipped"
	except PushWait as e:
		_failed(log, attempts, str(e), retry=True, waiting=True)
		return "Queued"
	except PushError as e:
		_failed(log, attempts, str(e), retry=False)
		return "Failed"
	except QBOError as e:
		_failed(log, attempts, str(e), retry=e.transient)
		return "Failed"
	except Exception as e:
		_rollback()
		_failed(log, attempts, f"{type(e).__name__}: {e}", retry=True)
		frappe.log_error(
			title=f"QBO push failed: {log.reference_doctype} {log.reference_name}",
			message=frappe.get_traceback(),
		)
		return "Failed"

	_finish(
		log,
		"Synced",
		message=result.get("message"),
		qbo_entity=result.get("qbo_entity"),
		qbo_id=result.get("qbo_id"),
		request_payload=_json(result.get("request")),
		response_payload=_json(result.get("response")),
		warnings="\n".join(result.get("warnings") or []) or None,
		synced_at=now_datetime(),
	)
	return "Synced"


def _finish(log, status, **values):
	values = {k: v for k, v in values.items() if v is not None}
	values.update({"status": status, "next_attempt_at": None, "last_error": None})
	frappe.db.set_value(PUSH_LOG, log.name, values)
	_commit()


def _failed(log, attempts, message, retry, waiting=False):
	values = {"last_error": message[:5000]}
	if retry and attempts < MAX_ATTEMPTS:
		minutes = BACKOFF_MINUTES[min(attempts, MAX_ATTEMPTS) - 1]
		values.update(
			status="Queued" if waiting else "Failed",
			next_attempt_at=add_to_date(now_datetime(), minutes=minutes),
		)
	else:
		values.update(status="Failed", next_attempt_at=None)
		frappe.log_error(
			title=f"QBO push needs attention: {log.reference_doctype} {log.reference_name}",
			message=f"{log.name} ({log.action}) failed after {attempts} attempt(s): {message}",
		)
	frappe.db.set_value(PUSH_LOG, log.name, values)
	_commit()


def _defer(log, message, minutes):
	"""Postpone without counting an attempt."""
	frappe.db.set_value(
		PUSH_LOG,
		log.name,
		{
			"status": "Queued",
			"last_error": message,
			"next_attempt_at": add_to_date(now_datetime(), minutes=minutes),
		},
	)
	_commit()


def _load_log(log_name):
	return frappe.db.get_value(
		PUSH_LOG,
		log_name,
		["name", "reference_doctype", "reference_name", "action", "status", "attempts", "creation"],
		as_dict=True,
	)


def _earlier_open_log(log):
	rows = frappe.get_all(
		PUSH_LOG,
		filters={
			"reference_doctype": log.reference_doctype,
			"reference_name": log.reference_name,
			"status": ["in", OPEN_STATUSES],
			"creation": ["<", log.creation],
			"name": ["!=", log.name],
		},
		fields=["name", "action", "status", "next_attempt_at"],
		order_by="creation asc",
		limit=1,
	)
	return rows[0] if rows else None


def _has_log(doctype, name, action):
	return bool(
		frappe.db.exists(
			PUSH_LOG,
			{
				"reference_doctype": doctype,
				"reference_name": name,
				"action": action,
				"status": ["!=", "Skipped"],
			},
		)
	)


def run_due_pushes(force=False):
	"""Scheduler (every 5 min): retry due logs and recover jobs that died mid-flight."""
	if not force and not _push_enabled(_settings()):
		return
	stale_before = add_to_date(now_datetime(), minutes=-STALE_PROCESSING_MINUTES)
	for name in frappe.get_all(
		PUSH_LOG, filters={"status": "Processing", "last_attempt_at": ["<", stale_before]}, pluck="name"
	):
		frappe.db.set_value(
			PUSH_LOG,
			name,
			{
				"status": "Failed",
				"next_attempt_at": now_datetime(),
				"last_error": "Worker stopped mid-push; retrying",
			},
		)
	_commit()

	due = frappe.get_all(
		PUSH_LOG,
		filters={"status": ["in", ("Queued", "Failed")], "next_attempt_at": ["<=", now_datetime()]},
		pluck="name",
		order_by="creation asc",
		limit=SCHEDULER_BATCH,
	)
	for name in due:
		try:
			process_log(name)
		except Exception:
			_rollback()
			frappe.log_error(title=f"QBO push scheduler: {name}", message=frappe.get_traceback())


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _push_customer(log, client):
	customer = frappe.db.get_value("Customer", log.reference_name, "custom_qbo_id")
	if customer:
		raise PushSkip(f"Already in QuickBooks (Id {customer})")
	qbo_id = ensure_customer(client, log.reference_name)
	return {"qbo_entity": "Customer", "qbo_id": qbo_id, "message": "Customer linked/created in QuickBooks"}


def _update_customer(log, client):
	cust = _customer_row(log.reference_name)
	if not cust.custom_qbo_id:
		raise PushSkip("Customer is not in QuickBooks yet; it is created with its first invoice")
	current = _read_or_none(client, "Customer", cust.custom_qbo_id)
	if not current:
		raise PushError(
			f"QuickBooks customer {cust.custom_qbo_id} no longer exists; relink it from the Customer"
		)
	body = _customer_body(cust)
	body.pop("Notes", None)
	body.update({"Id": cust.custom_qbo_id, "SyncToken": current.get("SyncToken"), "sparse": True})
	updated = client.update("Customer", body, _requestid(log.name, "update"))
	return {
		"qbo_entity": "Customer",
		"qbo_id": cust.custom_qbo_id,
		"request": body,
		"response": updated,
		"message": "Contact details updated in QuickBooks",
	}


def _push_sales_invoice(log, client):
	si = frappe.get_doc("Sales Invoice", log.reference_name)
	entity = "CreditMemo" if cint(si.is_return) else "Invoice"
	if si.get("custom_qbo_id"):
		raise PushSkip(f"Already in QuickBooks ({entity} Id {si.custom_qbo_id})")
	if si.docstatus == 0:
		raise PushSkip("Sales Invoice is a draft")
	_require_company_currency(si.company, [si.currency])

	settings = _settings()
	target = document_total(si)
	customer_id = ensure_customer(client, si.customer)

	existing = _find_existing_sales_txn(client, entity, si, customer_id, target)
	if existing:
		_write_back("Sales Invoice", si.name, existing["Id"], LINKED)
		_queue_credit_application(si, settings)
		return {
			"qbo_entity": entity,
			"qbo_id": existing["Id"],
			"response": existing,
			"message": f"Linked to existing QuickBooks {entity} #{existing.get('DocNumber') or existing['Id']}",
		}
	if si.docstatus == 2:
		raise PushSkip("Cancelled before it reached QuickBooks; nothing to create")

	body = build_sales_body(si, client, settings, customer_id, target)
	created = client.create(entity, body, _requestid("Sales Invoice", si.name, "create"))
	if not created.get("Id"):
		raise QBOError(f"QuickBooks did not return an {entity} Id", transient=True)
	_write_back("Sales Invoice", si.name, created["Id"], SYNCED_FROM_ERPNEXT)

	warnings = []
	qbo_total = flt(created.get("TotalAmt"), 2)
	if abs(qbo_total - target) > 0.005:
		warnings.append(
			f"QuickBooks total {qbo_total} differs from ERPNext {target}. Check QuickBooks sales tax "
			"(lines are sent as non-taxable; ERPNext taxes are separate lines) before payments sync."
		)
	if cint(si.get("is_pos")) and flt(si.get("paid_amount")):
		warnings.append("Payment recorded inside this POS invoice is not pushed; record it in QuickBooks")
	_queue_credit_application(si, settings)
	return {
		"qbo_entity": entity,
		"qbo_id": created["Id"],
		"request": body,
		"response": created,
		"warnings": warnings,
		"message": f"Created QuickBooks {entity} #{created.get('DocNumber') or created['Id']}",
	}


def _queue_credit_application(si, settings):
	if not cint(si.is_return) or si.docstatus != 1 or not si.return_against:
		return
	if settings.get("apply_credit_notes") is not None and not cint(settings.get("apply_credit_notes")):
		return
	# ERPNext only reduces the original invoice when "Update Outstanding for Self" is off.
	if cint(si.get("update_outstanding_for_self")):
		return
	enqueue_push("Sales Invoice", si.name, "Apply Credit")


def _apply_credit_note(log, client):
	si = frappe.get_doc("Sales Invoice", log.reference_name)
	if si.docstatus != 1:
		raise PushSkip("Credit note is not submitted")
	if not si.get("custom_qbo_id"):
		raise PushWait("Credit memo is not in QuickBooks yet")
	original_qbo_id = frappe.db.get_value("Sales Invoice", si.return_against, "custom_qbo_id")
	if not original_qbo_id:
		raise PushSkip(
			f"Original invoice {si.return_against} is not in QuickBooks; the credit memo stays unapplied"
		)

	invoice = _read_or_none(client, "Invoice", original_qbo_id)
	if not invoice:
		raise PushSkip(f"QuickBooks invoice {original_qbo_id} no longer exists; credit left unapplied")
	amount = round(min(document_total(si), flt(invoice.get("Balance"))), 2)
	if amount <= 0:
		raise PushSkip(f"QuickBooks invoice {original_qbo_id} has no open balance; credit left unapplied")

	body = {
		"CustomerRef": {"value": ensure_customer(client, si.customer)},
		"TotalAmt": 0,
		"TxnDate": str(si.posting_date),
		"PrivateNote": f"ERPNext credit note {si.name} applied to {si.return_against}",
		"Line": [
			{"Amount": amount, "LinkedTxn": [{"TxnId": str(original_qbo_id), "TxnType": "Invoice"}]},
			{"Amount": amount, "LinkedTxn": [{"TxnId": str(si.custom_qbo_id), "TxnType": "CreditMemo"}]},
		],
	}
	payment = client.create("Payment", body, _requestid("Sales Invoice", si.name, "apply-credit"))
	return {
		"qbo_entity": "Payment",
		"qbo_id": payment.get("Id"),
		"request": body,
		"response": payment,
		"message": f"Applied {amount} of credit memo {si.custom_qbo_id} to invoice {original_qbo_id}",
	}


def _void_sales_invoice(log, client):
	si = frappe.db.get_value(
		"Sales Invoice", log.reference_name, ["name", "custom_qbo_id", "is_return"], as_dict=True
	)
	if not si or not si.custom_qbo_id:
		raise PushSkip("Never reached QuickBooks; nothing to void")

	if cint(si.is_return):
		# QuickBooks can't void a credit memo: remove its application, then delete it.
		application = frappe.db.get_value(
			PUSH_LOG,
			{
				"reference_doctype": "Sales Invoice",
				"reference_name": si.name,
				"action": "Apply Credit",
				"status": "Synced",
			},
			"qbo_id",
		)
		if application:
			_delete_if_exists(client, "Payment", application, _requestid(log.name, "delete-application"))
		deleted = _delete_if_exists(client, "CreditMemo", si.custom_qbo_id, _requestid(log.name, "delete"))
		return {
			"qbo_entity": "CreditMemo",
			"qbo_id": si.custom_qbo_id,
			"response": deleted,
			"message": "Credit memo deleted in QuickBooks" if deleted else "Credit memo was already gone",
		}

	invoice = _read_or_none(client, "Invoice", si.custom_qbo_id)
	if not invoice:
		raise PushSkip(f"QuickBooks invoice {si.custom_qbo_id} is already deleted")
	if _is_voided(invoice):
		raise PushSkip(f"QuickBooks invoice {si.custom_qbo_id} is already voided")
	body = {"Id": si.custom_qbo_id, "SyncToken": invoice.get("SyncToken")}
	voided = client.operation("Invoice", body, "void", _requestid(log.name, "void"))
	return {
		"qbo_entity": "Invoice",
		"qbo_id": si.custom_qbo_id,
		"request": body,
		"response": voided,
		"message": f"Voided QuickBooks invoice {si.custom_qbo_id}",
	}


def _push_payment_entry(log, client):
	pe = frappe.get_doc("Payment Entry", log.reference_name)
	if pe.get("custom_synced_from") == SYNCED_FROM_QBO:
		raise PushSkip("Payment came from QuickBooks")
	if pe.get("custom_qbo_id"):
		raise PushSkip(f"Already in QuickBooks (Payment Id {pe.custom_qbo_id})")
	if pe.docstatus != 1:
		raise PushSkip("Payment Entry is not submitted")
	if pe.payment_type != "Receive" or pe.party_type != "Customer":
		raise PushSkip("Only customer receipts are pushed")
	_require_company_currency(pe.company, [pe.paid_from_account_currency, pe.paid_to_account_currency])
	if pe.get("deductions"):
		raise PushError(
			"Payment Entry has deductions/write-offs, which QuickBooks payments can't express; "
			"record this payment in QuickBooks by hand, then link it"
		)

	lines, warnings = [], []
	for ref in pe.get("references") or []:
		if ref.reference_doctype != "Sales Invoice":
			warnings.append(
				f"{ref.reference_doctype} {ref.reference_name} allocation left unapplied in QuickBooks"
			)
			continue
		allocated = flt(ref.allocated_amount, 2)
		if allocated <= 0:
			raise PushError(
				f"Allocation to {ref.reference_name} is {allocated}; payments against credit notes are not pushed"
			)
		qbo_invoice_id = frappe.db.get_value("Sales Invoice", ref.reference_name, "custom_qbo_id")
		if not qbo_invoice_id:
			if _has_open_log("Sales Invoice", ref.reference_name, "Create"):
				raise PushWait(f"Waiting for Sales Invoice {ref.reference_name} to reach QuickBooks")
			raise PushError(
				f"Sales Invoice {ref.reference_name} is not in QuickBooks. Push it (Sales Invoice → "
				"QuickBooks → Push now), then retry this log"
			)
		lines.append(
			{"Amount": allocated, "LinkedTxn": [{"TxnId": str(qbo_invoice_id), "TxnType": "Invoice"}]}
		)

	total = flt(pe.received_amount, 2)
	if sum(line["Amount"] for line in lines) - total > 0.005:
		raise PushError(f"Allocated amounts exceed the received amount {total}")
	if total - sum(line["Amount"] for line in lines) > 0.005:
		warnings.append("Unallocated amount stays as customer credit in QuickBooks")

	customer_id = ensure_customer(client, pe.party)
	marker = f"{PAYMENT_NOTE} {pe.name}"
	existing = _find_by_note(
		client,
		"Payment",
		f"select * from Payment where CustomerRef = '{escape_query_value(customer_id)}' "
		f"and TxnDate = '{pe.posting_date}'",
		marker,
	)
	if existing:
		_write_back("Payment Entry", pe.name, existing["Id"], SYNCED_FROM_ERPNEXT)
		return {
			"qbo_entity": "Payment",
			"qbo_id": existing["Id"],
			"message": "Linked to existing QuickBooks payment",
		}

	body = {
		"CustomerRef": {"value": customer_id},
		"TotalAmt": total,
		"TxnDate": str(pe.posting_date),
		"PrivateNote": marker,
		"Line": lines,
	}
	if pe.reference_no:
		body["PaymentRefNum"] = str(pe.reference_no)[:QBO_DOC_NUMBER_MAX]
	deposit_account = (_settings().get("qbo_deposit_account") or "").strip()
	if deposit_account:
		body["DepositToAccountRef"] = {"value": qbo_ref_id(client, "Account", deposit_account)}

	created = client.create("Payment", body, _requestid("Payment Entry", pe.name, "create"))
	if not created.get("Id"):
		raise QBOError("QuickBooks did not return a Payment Id", transient=True)
	_write_back("Payment Entry", pe.name, created["Id"], SYNCED_FROM_ERPNEXT)
	return {
		"qbo_entity": "Payment",
		"qbo_id": created["Id"],
		"request": body,
		"response": created,
		"warnings": warnings,
		"message": f"Created QuickBooks payment {created['Id']}",
	}


def _void_payment_entry(log, client):
	pe = frappe.db.get_value(
		"Payment Entry", log.reference_name, ["name", "custom_qbo_id", "custom_synced_from"], as_dict=True
	)
	if not pe or not pe.custom_qbo_id:
		raise PushSkip("Never reached QuickBooks; nothing to void")
	if pe.custom_synced_from == SYNCED_FROM_QBO:
		raise PushSkip("Payment came from QuickBooks; void it there")
	payment = _read_or_none(client, "Payment", pe.custom_qbo_id)
	if not payment:
		raise PushSkip(f"QuickBooks payment {pe.custom_qbo_id} is already deleted")
	if _is_voided(payment):
		raise PushSkip(f"QuickBooks payment {pe.custom_qbo_id} is already voided")
	body = {"Id": pe.custom_qbo_id, "SyncToken": payment.get("SyncToken"), "sparse": True}
	voided = client.operation("Payment", body, "update", _requestid(log.name, "void"), include="void")
	return {
		"qbo_entity": "Payment",
		"qbo_id": pe.custom_qbo_id,
		"request": body,
		"response": voided,
		"message": f"Voided QuickBooks payment {pe.custom_qbo_id}",
	}


HANDLERS = {
	("Customer", "Create"): _push_customer,
	("Customer", "Update"): _update_customer,
	("Sales Invoice", "Create"): _push_sales_invoice,
	("Sales Invoice", "Apply Credit"): _apply_credit_note,
	("Sales Invoice", "Void"): _void_sales_invoice,
	("Payment Entry", "Create"): _push_payment_entry,
	("Payment Entry", "Void"): _void_payment_entry,
}


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def document_total(si):
	"""What the customer owes in ERPNext (rounded total unless rounding is off), as a positive number."""
	total = si.grand_total
	if not cint(si.get("disable_rounded_total")) and flt(si.get("rounded_total")):
		total = si.rounded_total
	return round(abs(flt(total)), 2)


def build_sales_body(si, client, settings, customer_id, target):
	"""QBO Invoice / CreditMemo body whose total equals ``target`` exactly."""
	sign = -1 if cint(si.is_return) else 1
	tax_code = (settings.get("qbo_tax_code") or DEFAULT_TAX_CODE).strip()
	default_item = (settings.get("qbo_default_item") or DEFAULT_ITEM_NAME).strip()
	charge_item = (settings.get("qbo_tax_item") or default_item).strip()
	group_map = {
		row.item_group: (row.qbo_item_name or "").strip()
		for row in (settings.get("item_group_map") or [])
		if row.item_group and row.qbo_item_name
	}

	lines = []
	for row in si.get("items") or []:
		amount = round(sign * flt(row.net_amount), 2)
		qty = sign * flt(row.qty)
		rate = flt(row.net_rate)
		item_name = _mapped_item_name(row.get("item_group"), group_map) or default_item
		description = _line_description(row)
		detail = {"ItemRef": {"value": qbo_ref_id(client, "Item", item_name)}}
		if qty > 0 and rate >= 0 and abs(round(qty * rate, 2) - amount) <= 0.005:
			detail.update({"Qty": qty, "UnitPrice": rate})
		else:
			# QBO rejects Amount != Qty * UnitPrice; keep the exact amount and put qty in the text.
			detail.update({"Qty": 1, "UnitPrice": amount})
			description = f"{_fmt_qty(qty)} x {description}"
		if tax_code:
			detail["TaxCodeRef"] = {"value": tax_code}
		lines.append(
			{
				"DetailType": "SalesItemLineDetail",
				"Amount": amount,
				"Description": description[:4000],
				"SalesItemLineDetail": detail,
			}
		)

	charge_item_id = None
	for tax in si.get("taxes") or []:
		amount = round(sign * flt(tax.tax_amount_after_discount_amount), 2)
		if not amount:
			continue
		charge_item_id = charge_item_id or qbo_ref_id(client, "Item", charge_item)
		label = strip_html_tags(tax.description or "") or tax.account_head or "Tax"
		lines.append(_charge_line(label, amount, charge_item_id, tax_code))

	difference = round(target - sum(line["Amount"] for line in lines), 2)
	if difference >= 0.01:
		charge_item_id = charge_item_id or qbo_ref_id(client, "Item", charge_item)
		lines.append(_charge_line("Rounding adjustment", difference, charge_item_id, tax_code))
	elif difference <= -0.01:
		lines.append(
			{
				"DetailType": "DiscountLineDetail",
				"Amount": abs(difference),
				"Description": "Rounding adjustment",
				"DiscountLineDetail": {"PercentBased": False},
			}
		)

	body = {
		"CustomerRef": {"value": customer_id},
		"DocNumber": doc_number(si.name),
		"TxnDate": str(si.posting_date),
		"PrivateNote": f"{INVOICE_NOTE} {si.name}",
		"Line": lines,
	}
	if not cint(si.is_return) and si.get("due_date"):
		body["DueDate"] = str(si.due_date)
	email = (si.get("contact_email") or "").strip()
	if "@" in email:
		body["BillEmail"] = {"Address": email[:100]}
	bill_addr = _qbo_address(si.get("customer_address"))
	if bill_addr:
		body["BillAddr"] = bill_addr
	ship_addr = _qbo_address(si.get("shipping_address_name"))
	if ship_addr:
		body["ShipAddr"] = ship_addr
	if si.get("po_no"):
		body["CustomerMemo"] = {"value": f"PO {si.po_no}"[:1000]}
	return body


def _charge_line(label, amount, item_id, tax_code):
	detail = {"ItemRef": {"value": item_id}, "Qty": 1, "UnitPrice": amount}
	if tax_code:
		detail["TaxCodeRef"] = {"value": tax_code}
	return {
		"DetailType": "SalesItemLineDetail",
		"Amount": amount,
		"Description": str(label)[:4000],
		"SalesItemLineDetail": detail,
	}


def _line_description(row):
	head = " - ".join(p for p in (row.get("item_code"), row.get("item_name")) if p)
	text = strip_html_tags(row.get("description") or "").strip()
	if text and text != (row.get("item_name") or "").strip():
		return f"{head}\n{text}" if head else text
	return head or text or "Item"


def _fmt_qty(qty):
	return f"{qty:g}"


def _mapped_item_name(item_group, group_map):
	seen = set()
	group = item_group
	while group and group not in seen:
		if group in group_map:
			return group_map[group]
		seen.add(group)
		group = frappe.get_cached_value("Item Group", group, "parent_item_group")
	return None


def doc_number(name):
	# Keep the end of long names: it carries the sequence number.
	return name if len(name) <= QBO_DOC_NUMBER_MAX else name[-QBO_DOC_NUMBER_MAX:]


def ensure_customer(client, customer_name):
	"""QBO Customer Id for an ERPNext customer: linked id, else match on DisplayName, else create."""
	cust = _customer_row(customer_name)
	if cust.custom_qbo_id:
		return cust.custom_qbo_id

	display = _display_name(cust.customer_name or cust.name)
	found = _customer_by_display_name(client, display)
	if found:
		_write_back("Customer", cust.name, found["Id"], LINKED)
		return found["Id"]

	body = _customer_body(cust)
	body["DisplayName"] = display
	try:
		created = client.create("Customer", body, _requestid("Customer", cust.name, "create"))
	except QBOError as e:
		# 6240 = name already used by a vendor, employee or inactive customer.
		if e.code != "6240":
			raise
		display = _display_name(
			f"{display} ({cust.name})" if cust.name != display else f"{display} (Customer)"
		)
		found = _customer_by_display_name(client, display)
		if found:
			created = found
		else:
			body["DisplayName"] = display
			created = client.create("Customer", body, _requestid("Customer", cust.name, "create-alt"))
	if not created.get("Id"):
		raise QBOError("QuickBooks did not return a Customer Id", transient=True)
	_write_back("Customer", cust.name, created["Id"], SYNCED_FROM_ERPNEXT)
	return created["Id"]


def _customer_by_display_name(client, display):
	return client.query_one(
		"Customer", f"select * from Customer where DisplayName = '{escape_query_value(display)}'"
	)


def _customer_row(customer_name):
	cust = frappe.db.get_value(
		"Customer",
		customer_name,
		[
			"name",
			"customer_name",
			"customer_type",
			"email_id",
			"mobile_no",
			"customer_primary_address",
			"custom_qbo_id",
		],
		as_dict=True,
	)
	if not cust:
		raise PushError(f"Customer {customer_name} not found")
	return cust


def _customer_body(cust):
	body = {"Notes": f"{CUSTOMER_NOTE} {cust.name}"}
	if cust.customer_type == "Company" and cust.customer_name:
		body["CompanyName"] = cust.customer_name[:100]
	email = (cust.email_id or "").strip()
	if "@" in email:
		body["PrimaryEmailAddr"] = {"Address": email[:100]}
	if cust.mobile_no:
		body["PrimaryPhone"] = {"FreeFormNumber": str(cust.mobile_no)[:30]}
	addr = _qbo_address(cust.customer_primary_address)
	if addr:
		body["BillAddr"] = addr
	return body


def _display_name(name):
	# QBO uses ':' for sub-customer paths and rejects control characters.
	cleaned = " ".join(str(name).replace(":", "-").split())
	return cleaned[:100] or "Customer"


def _qbo_address(address_name):
	if not address_name:
		return None
	addr = frappe.db.get_value(
		"Address",
		address_name,
		["address_line1", "address_line2", "city", "state", "pincode", "country"],
		as_dict=True,
	)
	if not addr or not addr.address_line1:
		return None
	out = {
		"Line1": addr.address_line1,
		"Line2": addr.address_line2,
		"City": addr.city,
		"CountrySubDivisionCode": addr.state,
		"PostalCode": addr.pincode,
		"Country": addr.country,
	}
	return {k: str(v)[:255] for k, v in out.items() if v}


def qbo_ref_id(client, entity, name):
	"""Id of a QBO Item/Account by Name, cached."""
	key = f"ill_qbo_ref::{entity}::{name}"
	cached = frappe.cache().get_value(key)
	if cached:
		return cached
	row = client.query_one(entity, f"select * from {entity} where Name = '{escape_query_value(name)}'")
	if not row:
		raise PushError(
			f"QuickBooks has no {entity} named '{name}'. Create it in QuickBooks or fix the name in ilL-QBO-Settings"
		)
	frappe.cache().set_value(key, row["Id"], expires_in_sec=CACHE_TTL_SECONDS)
	return row["Id"]


def _find_existing_sales_txn(client, entity, si, customer_id, target):
	number = doc_number(si.name)
	rows = (
		client.query(f"select * from {entity} where DocNumber = '{escape_query_value(number)}'").get(entity)
		or []
	)
	marker = f"{INVOICE_NOTE} {si.name}"
	for row in rows:
		same_customer = str((row.get("CustomerRef") or {}).get("value")) == str(customer_id)
		same_total = abs(flt(row.get("TotalAmt")) - target) <= 0.005
		if marker in (row.get("PrivateNote") or "") or (same_customer and same_total):
			return row
	if rows:
		row = rows[0]
		raise PushError(
			f"QuickBooks already has {entity} #{number} (Id {row.get('Id')}) for a different customer or amount. "
			"Link the right one from the Sales Invoice (QuickBooks → Link existing record) or renumber it in QuickBooks"
		)
	return None


def _find_by_note(client, entity, statement, marker):
	for row in client.query(statement).get(entity) or []:
		if marker in (row.get("PrivateNote") or ""):
			return row
	return None


def _read_or_none(client, entity, qbo_id):
	try:
		return client.read(entity, qbo_id) or None
	except QBOError as e:
		if e.code == "610" or e.status == 404:  # Object Not Found
			return None
		raise


def _delete_if_exists(client, entity, qbo_id, requestid):
	current = _read_or_none(client, entity, qbo_id)
	if not current:
		return None
	return client.operation(
		entity, {"Id": str(qbo_id), "SyncToken": current.get("SyncToken")}, "delete", requestid
	)


def _is_voided(txn):
	note = (txn.get("PrivateNote") or "").lower()
	return flt(txn.get("TotalAmt")) == 0 and note.startswith("voided")


def _require_company_currency(company, currencies):
	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	for currency in currencies:
		if currency and company_currency and currency != company_currency:
			raise PushError(
				f"Currency {currency} differs from the company currency {company_currency}; "
				"multi-currency documents are not pushed to QuickBooks"
			)


def _has_open_log(doctype, name, action):
	return bool(
		frappe.db.exists(
			PUSH_LOG,
			{
				"reference_doctype": doctype,
				"reference_name": name,
				"action": action,
				"status": ["in", OPEN_STATUSES],
			},
		)
	)


# ---------------------------------------------------------------------------
# Desk actions
# ---------------------------------------------------------------------------

SUPPORTED_DOCTYPES = ("Sales Invoice", "Payment Entry", "Customer")
ENTITY_FOR = {"Payment Entry": "Payment", "Customer": "Customer"}


@frappe.whitelist()
def push_now(doctype, name):
	"""Queue the right action for a document and run it immediately."""
	_require_manager()
	if doctype not in SUPPORTED_DOCTYPES:
		frappe.throw(f"{doctype} is not synced to QuickBooks")
	doc = frappe.get_doc(doctype, name)
	if doctype == "Customer":
		action = "Update" if doc.get("custom_qbo_id") else "Create"
	elif doc.docstatus == 2:
		action = "Void"
	elif doc.docstatus == 1:
		action = "Create"
		if doctype == "Sales Invoice" and doc.get("custom_qbo_id") and cint(doc.is_return):
			action = "Apply Credit"
	else:
		frappe.throw("Submit the document first")
	log_name = enqueue_push(doctype, name, action, reset=True, process_now=True)
	return _log_summary(log_name)


@frappe.whitelist()
def retry(log_name):
	_require_manager()
	frappe.db.set_value(
		PUSH_LOG, log_name, {"status": "Queued", "attempts": 0, "next_attempt_at": now_datetime()}
	)
	process_log(log_name)
	return _log_summary(log_name)


@frappe.whitelist()
def retry_failed():
	"""Re-queue every Failed log (e.g. after fixing settings or reconnecting QuickBooks)."""
	_require_manager()
	names = frappe.get_all(PUSH_LOG, filters={"status": "Failed"}, pluck="name", order_by="creation asc")
	for name in names:
		frappe.db.set_value(
			PUSH_LOG, name, {"status": "Queued", "attempts": 0, "next_attempt_at": now_datetime()}
		)
	_commit()
	frappe.enqueue(
		"illumenate_lighting.illumenate_lighting.api.qbo_push.run_due_pushes", queue="long", force=True
	)
	return len(names)


@frappe.whitelist()
def link_existing(doctype, name, qbo_id):
	"""Point an ERPNext document at a QBO record that already exists (e.g. entered by hand in QBO)."""
	_require_manager()
	if doctype not in SUPPORTED_DOCTYPES:
		frappe.throw(f"{doctype} is not synced to QuickBooks")
	qbo_id = str(qbo_id or "").strip()
	if not qbo_id.isdigit():
		frappe.throw("Enter the numeric QuickBooks Id (from the record's URL, e.g. txnId=145)")
	entity = ENTITY_FOR.get(doctype)
	if doctype == "Sales Invoice":
		entity = "CreditMemo" if cint(frappe.db.get_value(doctype, name, "is_return")) else "Invoice"
	try:
		record = _read_or_none(QBOClient(), entity, qbo_id)
	except QBOError as e:
		frappe.throw(f"Could not check QuickBooks: {e}")
	if not record:
		frappe.throw(f"QuickBooks has no {entity} with Id {qbo_id}")
	_write_back(doctype, name, qbo_id, LINKED)
	for log in frappe.get_all(
		PUSH_LOG,
		filters={
			"reference_doctype": doctype,
			"reference_name": name,
			"action": ["in", ("Create",)],
			"status": ["in", ("Queued", "Failed")],
		},
		pluck="name",
	):
		frappe.db.set_value(
			PUSH_LOG,
			log,
			{"status": "Skipped", "next_attempt_at": None, "last_error": f"Linked by hand to {qbo_id}"},
		)
	return {"qbo_id": qbo_id, "entity": entity}


@frappe.whitelist()
def get_status(doctype, name):
	if not frappe.has_permission(doctype, "read", name):
		frappe.throw("Not permitted", frappe.PermissionError)
	logs = frappe.get_all(
		PUSH_LOG,
		filters={"reference_doctype": doctype, "reference_name": name},
		fields=["name", "action", "status", "last_error", "warnings", "qbo_id", "modified"],
		order_by="creation desc",
		limit=5,
	)
	settings = _settings()
	return {
		"qbo_id": frappe.db.get_value(doctype, name, "custom_qbo_id"),
		"push_enabled": _push_enabled(settings),
		"logs": logs,
	}


@frappe.whitelist()
def test_connection():
	_require_manager()
	client = QBOClient()
	info = client.query_one("CompanyInfo", "select * from CompanyInfo")
	if not info:
		frappe.throw("QuickBooks answered but returned no company info")
	settings = _settings()
	checks = []
	names = {(settings.get("qbo_default_item") or DEFAULT_ITEM_NAME).strip()}
	if settings.get("qbo_tax_item"):
		names.add(settings.qbo_tax_item.strip())
	names.update(
		(r.qbo_item_name or "").strip() for r in settings.get("item_group_map") or [] if r.qbo_item_name
	)
	for name in sorted(names):
		checks.append(_check_ref(client, "Item", name))
	if settings.get("qbo_deposit_account"):
		checks.append(_check_ref(client, "Account", settings.qbo_deposit_account.strip()))
	return {"company_name": info.get("CompanyName"), "realm_country": info.get("Country"), "checks": checks}


def _check_ref(client, entity, name):
	frappe.cache().delete_value(f"ill_qbo_ref::{entity}::{name}")
	try:
		return {"entity": entity, "name": name, "ok": True, "id": qbo_ref_id(client, entity, name)}
	except PushError as e:
		return {"entity": entity, "name": name, "ok": False, "error": str(e)}


@frappe.whitelist()
def backfill(from_date, to_date=None, include_payments=1):
	"""Queue submitted invoices (and optionally receipts) in a date range that aren't in QuickBooks."""
	_require_manager()
	filters = {"docstatus": 1, "custom_qbo_id": ["is", "not set"], "posting_date": [">=", getdate(from_date)]}
	if to_date:
		filters["posting_date"] = ["between", (getdate(from_date), getdate(to_date))]
	queued = {"Sales Invoice": 0, "Payment Entry": 0}
	invoices = frappe.get_all("Sales Invoice", filters=filters, pluck="name", order_by="posting_date asc")
	for name in invoices:
		if not _has_open_log("Sales Invoice", name, "Create"):
			enqueue_push("Sales Invoice", name, "Create")
			queued["Sales Invoice"] += 1
	if cint(include_payments):
		payment_filters = dict(filters, payment_type="Receive", party_type="Customer")
		payment_filters["custom_synced_from"] = ["!=", SYNCED_FROM_QBO]
		for name in frappe.get_all(
			"Payment Entry", filters=payment_filters, pluck="name", order_by="posting_date asc"
		):
			if not _has_open_log("Payment Entry", name, "Create"):
				enqueue_push("Payment Entry", name, "Create")
				queued["Payment Entry"] += 1
	return queued


def _log_summary(log_name):
	return frappe.db.get_value(
		PUSH_LOG,
		log_name,
		["name", "action", "status", "qbo_id", "last_error", "warnings", "attempts"],
		as_dict=True,
	)


def _require_manager():
	frappe.only_for(MANAGER_ROLES)


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


def _settings():
	try:
		return frappe.get_cached_doc(SETTINGS_DOCTYPE)
	except Exception:
		return frappe._dict()


def _push_enabled(settings, flag=None):
	if not settings or not cint(settings.get("push_enabled")):
		return False
	if flag and settings.get(flag) is not None and not cint(settings.get(flag)):
		return False
	return True


def _write_back(doctype, name, qbo_id, synced_from):
	# db.set_value: no hooks, no "changed after submit" validation. Commit now —
	# the QuickBooks side already exists, so this link must survive a later failure.
	frappe.db.set_value(
		doctype,
		name,
		{"custom_qbo_id": str(qbo_id), "custom_synced_from": synced_from},
		update_modified=False,
	)
	_commit()


def _requestid(*parts):
	"""Deterministic Intuit requestid: a retry of the same step returns the original result."""
	raw = ":".join([frappe.local.site or ""] + [str(p) for p in parts])
	return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:36]


def _lock_key(doctype, name):
	return "qbo_push_" + hashlib.sha1(f"{frappe.local.site}:{doctype}:{name}".encode()).hexdigest()[:40]


def _acquire_lock(key):
	if frappe.db.db_type != "mariadb":
		return True
	return bool(frappe.db.sql("SELECT GET_LOCK(%s, %s)", (key, 0))[0][0])


def _release_lock(key):
	if frappe.db.db_type == "mariadb":
		frappe.db.sql("SELECT RELEASE_LOCK(%s)", (key,))


def _json(value):
	if value is None:
		return None
	return json.dumps(value, indent=2, default=str)


def _commit():
	# Tests run inside a transaction that FrappeTestCase rolls back; don't break that.
	if not frappe.flags.in_test:
		# Deliberate: log/outbox state must survive a later failure in the same request.
		frappe.db.commit()  # nosemgrep


def _rollback():
	# Everything worth keeping (log state, write-backs) is committed as it happens.
	if not frappe.flags.in_test:
		frappe.db.rollback()
