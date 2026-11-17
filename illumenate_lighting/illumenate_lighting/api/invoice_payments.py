# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Payments received against a Sales Invoice, for the ilL Sales Invoice print format.

The print format calls ``ill_invoice_payments(doc)`` (a jinja method) and lists the
rows as a payment history, so a paid invoice exported as PDF doubles as a receipt.

Rows come from three places, oldest first:

- Payment Entry Reference rows that point at the invoice (QuickBooks-synced payments
  land here, see ``qbo_sync``). Several rows of one Payment Entry are summed.
- Sales Invoice Advance rows, for an advance allocated on the invoice whose Payment
  Entry does not (yet) reference the invoice itself.
- Journal Entry Account rows that credit the invoice (manual bank or adjustment
  entries).

Only submitted vouchers count. Cancelled payments drop off, so a payment QuickBooks
deleted or edited shows once, as its replacement.
"""

import frappe
from frappe.utils import flt, getdate

INVOICE_DOCTYPE = "Sales Invoice"
QBO_SOURCE = "QuickBooks Online"

# Payment Entry fields the print shows. The custom ones are created by patches and
# may be missing on a site that has not migrated, so they are read only when present.
PE_FIELDS = ["name", "posting_date", "mode_of_payment", "reference_no", "payment_type"]
PE_OPTIONAL_FIELDS = [
	"custom_qbo_id",
	"custom_synced_from",
	"custom_qbo_payment_method",
	"custom_qbo_payment_ref_num",
]


def get_invoice_payments(invoice):
	"""Return the payments applied to ``invoice`` (a Sales Invoice doc or name).

	Each row is a dict with ``date``, ``amount`` (in the invoice currency; refunds are
	negative), ``method``, ``reference``, ``qbo_id``, ``voucher_type`` and
	``voucher_no``. Returns ``[]`` for a draft invoice or one with no payments.
	"""
	doc = frappe.get_doc(INVOICE_DOCTYPE, invoice) if isinstance(invoice, str) else invoice
	if not doc or not doc.get("name") or doc.get("docstatus") == 2:
		return []

	rows = []
	seen = set()
	precision = 2

	pe_amounts = _payment_entry_allocations(doc.name)
	for advance in doc.get("advances") or []:
		voucher = advance.get("reference_name")
		amount = flt(advance.get("allocated_amount"), precision)
		if (
			advance.get("reference_type") == "Payment Entry"
			and voucher
			and amount > 0
			and voucher not in pe_amounts
		):
			pe_amounts[voucher] = amount

	for pe in _payment_entries(list(pe_amounts)):
		amount = flt(pe_amounts.get(pe.name), precision)
		if not amount:
			continue
		if pe.get("payment_type") == "Pay":
			amount = -abs(amount)
		qbo_id = pe.get("custom_qbo_id") or None
		rows.append(
			{
				"date": getdate(pe.posting_date) if pe.posting_date else None,
				"amount": amount,
				"method": pe.get("custom_qbo_payment_method") or pe.get("mode_of_payment") or "",
				"reference": _pe_reference(pe, qbo_id),
				"qbo_id": qbo_id,
				"voucher_type": "Payment Entry",
				"voucher_no": pe.name,
			}
		)
		seen.add(pe.name)

	je_amounts = _journal_entry_amounts(doc.name)
	for advance in doc.get("advances") or []:
		voucher = advance.get("reference_name")
		amount = flt(advance.get("allocated_amount"), precision)
		if (
			advance.get("reference_type") == "Journal Entry"
			and voucher
			and amount > 0
			and voucher not in je_amounts
		):
			je_amounts[voucher] = amount

	for je in _journal_entries(list(je_amounts)):
		amount = flt(je_amounts.get(je.name), precision)
		if not amount or je.name in seen:
			continue
		rows.append(
			{
				"date": getdate(je.posting_date) if je.posting_date else None,
				"amount": amount,
				"method": je.get("mode_of_payment") or je.get("voucher_type") or "Journal Entry",
				"reference": je.get("cheque_no") or je.name,
				"qbo_id": None,
				"voucher_type": "Journal Entry",
				"voucher_no": je.name,
			}
		)
		seen.add(je.name)

	rows.sort(key=lambda r: (r["date"] or getdate("1900-01-01"), r["voucher_no"]))
	return rows


def ill_invoice_payments(doc):
	"""Jinja method for print formats. Never raises, so a lookup failure cannot break the print."""
	try:
		return get_invoice_payments(doc)
	except Exception:
		frappe.log_error(title="ilL Sales Invoice print: payment history lookup failed")
		return []


def _pe_reference(pe, qbo_id):
	ref_num = pe.get("custom_qbo_payment_ref_num")
	if ref_num:
		return ref_num
	if qbo_id:
		# The sync stores "QBO-<id>" in reference_no; the id is shown on its own.
		return ""
	return pe.get("reference_no") or pe.name


def _payment_entry_allocations(invoice_name):
	totals = {}
	for row in frappe.get_all(
		"Payment Entry Reference",
		filters={
			"parenttype": "Payment Entry",
			"reference_doctype": INVOICE_DOCTYPE,
			"reference_name": invoice_name,
			"docstatus": 1,
		},
		fields=["parent", "allocated_amount"],
	):
		totals[row.parent] = flt(totals.get(row.parent, 0) + flt(row.allocated_amount), 2)
	return totals


def _payment_entries(names):
	if not names:
		return []
	meta = frappe.get_meta("Payment Entry")
	fields = PE_FIELDS + [f for f in PE_OPTIONAL_FIELDS if meta.has_field(f)]
	return frappe.get_all(
		"Payment Entry",
		filters={"name": ["in", names], "docstatus": 1},
		fields=fields,
	)


def _journal_entry_amounts(invoice_name):
	totals = {}
	for row in frappe.get_all(
		"Journal Entry Account",
		filters={
			"parenttype": "Journal Entry",
			"reference_type": INVOICE_DOCTYPE,
			"reference_name": invoice_name,
			"docstatus": 1,
		},
		fields=["parent", "credit_in_account_currency", "debit_in_account_currency"],
	):
		net = flt(row.credit_in_account_currency) - flt(row.debit_in_account_currency)
		totals[row.parent] = flt(totals.get(row.parent, 0) + net, 2)
	return totals


def _journal_entries(names):
	if not names:
		return []
	return frappe.get_all(
		"Journal Entry",
		filters={"name": ["in", names], "docstatus": 1},
		fields=["name", "posting_date", "voucher_type", "mode_of_payment", "cheque_no"],
	)
