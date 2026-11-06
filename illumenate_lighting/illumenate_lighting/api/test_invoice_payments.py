# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Tests for the Sales Invoice payment history used by the ilL Sales Invoice print.

Run inside a bench:
    bench --site <site> run-tests --app illumenate_lighting \
        --module illumenate_lighting.illumenate_lighting.api.test_invoice_payments

The voucher lookups are mocked so the tests don't need a seeded Company, Accounts
or submitted Payment Entries.
"""

import datetime
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from illumenate_lighting.illumenate_lighting.api import invoice_payments

MOD = "illumenate_lighting.illumenate_lighting.api.invoice_payments"


def _invoice(advances=None, docstatus=1):
	return frappe._dict(name="SINV-TEST-PAY", docstatus=docstatus, advances=advances or [])


class TestInvoicePayments(FrappeTestCase):
	def _run(self, tables, invoice=None, has_custom_fields=True):
		"""``tables`` maps doctype -> rows returned by frappe.get_all for it."""
		calls = []

		def get_all(doctype, filters=None, fields=None, **kwargs):
			calls.append((doctype, filters, fields))
			rows = tables.get(doctype, [])
			if filters and isinstance(filters.get("name"), list):
				wanted = set(filters["name"][1])
				rows = [r for r in rows if r.name in wanted]
			return [frappe._dict(r) for r in rows]

		meta = MagicMock()
		meta.has_field.side_effect = lambda f: has_custom_fields
		with (
			patch(f"{MOD}.frappe.get_all", side_effect=get_all),
			patch(f"{MOD}.frappe.get_meta", return_value=meta),
		):
			rows = invoice_payments.get_invoice_payments(invoice or _invoice())
		return rows, calls

	def test_qbo_payments_listed_with_method_and_reference(self):
		rows, _calls = self._run(
			{
				"Payment Entry Reference": [
					{"parent": "PE-2", "allocated_amount": 400},
					{"parent": "PE-1", "allocated_amount": 250},
					{"parent": "PE-1", "allocated_amount": 350},  # split payment terms
				],
				"Payment Entry": [
					frappe._dict(
						name="PE-1",
						posting_date="2026-10-01",
						mode_of_payment="QuickBooks Online",
						reference_no="QBO-182",
						payment_type="Receive",
						custom_qbo_id="182",
						custom_qbo_payment_method="Check",
						custom_qbo_payment_ref_num="10452",
					),
					frappe._dict(
						name="PE-2",
						posting_date="2026-10-20",
						mode_of_payment="QuickBooks Online",
						reference_no="QBO-190",
						payment_type="Receive",
						custom_qbo_id="190",
					),
				],
			}
		)
		self.assertEqual([r["voucher_no"] for r in rows], ["PE-1", "PE-2"])
		first, second = rows
		self.assertEqual(first["amount"], 600)
		self.assertEqual(first["date"], datetime.date(2026, 10, 1))
		self.assertEqual(first["method"], "Check")
		self.assertEqual(first["reference"], "10452")
		self.assertEqual(first["qbo_id"], "182")
		# No QBO method synced yet: fall back to the Mode of Payment, and the
		# synthetic "QBO-<id>" reference_no is not repeated next to the id.
		self.assertEqual(second["method"], "QuickBooks Online")
		self.assertEqual(second["reference"], "")
		self.assertEqual(second["qbo_id"], "190")

	def test_manual_payment_uses_reference_no(self):
		rows, _calls = self._run(
			{
				"Payment Entry Reference": [{"parent": "PE-3", "allocated_amount": 100}],
				"Payment Entry": [
					frappe._dict(
						name="PE-3",
						posting_date="2026-10-05",
						mode_of_payment="Wire Transfer",
						reference_no="FED-991",
						payment_type="Receive",
					)
				],
			}
		)
		self.assertEqual(rows[0]["method"], "Wire Transfer")
		self.assertEqual(rows[0]["reference"], "FED-991")
		self.assertIsNone(rows[0]["qbo_id"])

	def test_advance_not_double_counted(self):
		advances = [
			frappe._dict(reference_type="Payment Entry", reference_name="PE-1", allocated_amount=500),
			frappe._dict(reference_type="Payment Entry", reference_name="PE-ADV", allocated_amount=200),
		]
		rows, _calls = self._run(
			{
				"Payment Entry Reference": [{"parent": "PE-1", "allocated_amount": 500}],
				"Payment Entry": [
					frappe._dict(name="PE-1", posting_date="2026-10-01", payment_type="Receive"),
					frappe._dict(name="PE-ADV", posting_date="2026-09-01", payment_type="Receive"),
				],
			},
			invoice=_invoice(advances=advances),
		)
		self.assertEqual([(r["voucher_no"], r["amount"]) for r in rows], [("PE-ADV", 200), ("PE-1", 500)])

	def test_journal_entry_credit_listed(self):
		rows, _calls = self._run(
			{
				"Journal Entry Account": [
					{"parent": "JV-1", "credit_in_account_currency": 75, "debit_in_account_currency": 0},
					{"parent": "JV-ZERO", "credit_in_account_currency": 10, "debit_in_account_currency": 10},
				],
				"Journal Entry": [
					frappe._dict(
						name="JV-1", posting_date="2026-10-03", voucher_type="Bank Entry", cheque_no="5512"
					),
					frappe._dict(name="JV-ZERO", posting_date="2026-10-03", voucher_type="Journal Entry"),
				],
			}
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["method"], "Bank Entry")
		self.assertEqual(rows[0]["reference"], "5512")
		self.assertEqual(rows[0]["amount"], 75)

	def test_refund_is_negative(self):
		rows, _calls = self._run(
			{
				"Payment Entry Reference": [{"parent": "PE-R", "allocated_amount": 50}],
				"Payment Entry": [frappe._dict(name="PE-R", posting_date="2026-10-09", payment_type="Pay")],
			}
		)
		self.assertEqual(rows[0]["amount"], -50)

	def test_custom_fields_skipped_before_migrate(self):
		_rows, calls = self._run(
			{
				"Payment Entry Reference": [{"parent": "PE-1", "allocated_amount": 10}],
				"Payment Entry": [
					frappe._dict(name="PE-1", posting_date="2026-10-01", payment_type="Receive")
				],
			},
			has_custom_fields=False,
		)
		pe_fields = next(fields for doctype, _f, fields in calls if doctype == "Payment Entry")
		self.assertNotIn("custom_qbo_payment_method", pe_fields)

	def test_only_submitted_vouchers_queried(self):
		_rows, calls = self._run({})
		for doctype, filters, _fields in calls:
			self.assertEqual(filters.get("docstatus"), 1, doctype)

	def test_cancelled_invoice_has_no_history(self):
		rows, calls = self._run({}, invoice=_invoice(docstatus=2))
		self.assertEqual(rows, [])
		self.assertEqual(calls, [])

	def test_jinja_method_never_raises(self):
		with (
			patch(f"{MOD}.get_invoice_payments", side_effect=RuntimeError("boom")),
			patch(f"{MOD}.frappe.log_error") as log_error,
		):
			self.assertEqual(invoice_payments.ill_invoice_payments(_invoice()), [])
		log_error.assert_called_once()
