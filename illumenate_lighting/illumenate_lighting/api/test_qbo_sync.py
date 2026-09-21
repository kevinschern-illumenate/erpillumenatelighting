# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Tests for the QBO Payment -> Payment Entry reverse sync endpoint.

Run inside a bench:
    bench --site <site> run-tests --app illumenate_lighting \
        --module illumenate_lighting.illumenate_lighting.api.test_qbo_sync

Payment Entry creation/cancellation is mocked so the tests don't depend on a
seeded Company/Account/Sales Invoice; the routing, idempotency, auth and log
behaviour is exercised for real against ilL-QBO-Sync-Log.
"""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from illumenate_lighting.illumenate_lighting.api import qbo_sync

MOD = "illumenate_lighting.illumenate_lighting.api.qbo_sync"
SECRET = "test-secret-do-not-use"
TEST_PREFIX = "TEST-QBO-"


def _sign(body: bytes, secret: str = SECRET) -> str:
	return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestQBOSync(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.local.request_ip = "127.0.0.1"
		frappe.local.form_dict = frappe._dict(cmd=f"{MOD}.receive_payment_event")
		frappe.local.response = frappe._dict()
		self._sync_enabled = patch(f"{MOD}._get_settings", return_value={"sync_enabled": 1})
		self._sync_enabled.start()

	def tearDown(self):
		self._sync_enabled.stop()
		frappe.db.delete("ilL-QBO-Sync-Log", {"qbo_payment_id": ["like", f"{TEST_PREFIX}%"]})

	# -- helpers -----------------------------------------------------------

	def _call(self, payload, signature=None, raw=None):
		body = raw if raw is not None else json.dumps(payload).encode()
		if signature is None:
			signature = _sign(body)
		request = MagicMock()
		request.get_data.return_value = body
		request.method = "POST"
		with patch.object(frappe, "request", request), patch(
			f"{MOD}._get_webhook_secret", return_value=SECRET
		), patch.object(frappe, "get_request_header", side_effect=lambda h: signature if h == qbo_sync.SIGNATURE_HEADER else None):
			return qbo_sync.receive_payment_event()

	def _logs(self, qbo_payment_id):
		return frappe.get_all(
			"ilL-QBO-Sync-Log",
			filters={"qbo_payment_id": qbo_payment_id},
			fields=["name", "status", "payment_entry", "superseded_payment_entry", "sales_invoice", "error_message", "warnings"],
			order_by="creation desc",
		)

	@staticmethod
	def _fake_invoice(name="SINV-TEST-QBO", outstanding=100.0):
		return frappe._dict(
			name=name,
			customer="Test Customer",
			customer_name="Test Customer",
			company="Test Co",
			debit_to="Debtors - TC",
			grand_total=outstanding,
			outstanding_amount=outstanding,
			due_date=None,
		)

	# -- auth --------------------------------------------------------------

	def test_missing_signature_rejected_without_db_writes(self):
		pid = f"{TEST_PREFIX}AUTH1"
		with patch.object(frappe, "log_error") as log_error:
			result = self._call({"qbo_payment_id": pid, "event_type": "Create"}, signature="")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"], "unauthorized")
		self.assertEqual(frappe.local.response.get("http_status_code"), 401)
		self.assertEqual(self._logs(pid), [])
		log_error.assert_called_once()

	def test_bad_signature_rejected(self):
		pid = f"{TEST_PREFIX}AUTH2"
		with patch.object(frappe, "log_error"):
			result = self._call({"qbo_payment_id": pid, "event_type": "Create"}, signature="deadbeef")
		self.assertEqual(result["error"], "unauthorized")
		self.assertEqual(self._logs(pid), [])

	def test_signature_accepts_sha256_prefix(self):
		body = b'{"a":1}'
		request = MagicMock()
		with patch(f"{MOD}._get_webhook_secret", return_value=SECRET), patch.object(
			frappe, "get_request_header", return_value=f"sha256={_sign(body).upper()}"
		), patch.object(frappe, "request", request):
			self.assertTrue(qbo_sync._verify_signature(body))

	def test_no_secret_configured_rejects_everything(self):
		body = b"{}"
		with patch(f"{MOD}._get_webhook_secret", return_value=None), patch.object(
			frappe, "get_request_header", return_value=_sign(body)
		):
			self.assertFalse(qbo_sync._verify_signature(body))

	# -- payload validation ------------------------------------------------

	def test_invalid_json_returns_400(self):
		raw = b"not json"
		result = self._call(None, raw=raw)
		self.assertEqual(result["error"], "invalid_json")
		self.assertEqual(frappe.local.response.get("http_status_code"), 400)

	def test_missing_payment_id_returns_400(self):
		result = self._call({"event_type": "Create"})
		self.assertEqual(result["error"], "missing_payment_id")
		self.assertEqual(frappe.local.response.get("http_status_code"), 400)

	def test_deleted_flag_forces_delete_event(self):
		event = qbo_sync._normalize_payload({"qbo_payment_id": "1", "event_type": "Update", "deleted": True})
		self.assertEqual(event["event_type"], "Delete")

	def test_invoice_ids_are_merged_with_primary(self):
		event = qbo_sync._normalize_payload(
			{"qbo_payment_id": "1", "event_type": "Create", "qbo_invoice_id": "10", "qbo_invoice_ids": ["10", "11"]}
		)
		self.assertEqual(event["qbo_invoice_ids"], ["10", "11"])

	# -- create / idempotency ----------------------------------------------

	def test_invoice_not_matched_logs_failure(self):
		pid = f"{TEST_PREFIX}NOMATCH"
		result = self._call(
			{
				"qbo_payment_id": pid,
				"event_type": "Create",
				"amount": 100,
				"txn_date": "2026-09-15",
				"qbo_invoice_id": "QBO-INV-DOES-NOT-EXIST-424242",
			}
		)
		self.assertFalse(result["success"])
		self.assertEqual(result["error"], "invoice_not_matched")
		logs = self._logs(pid)
		self.assertEqual(len(logs), 1)
		self.assertEqual(logs[0].status, "Failed")
		self.assertIn("QBO-INV-DOES-NOT-EXIST-424242", logs[0].error_message)

	def test_create_event_creates_payment_entry(self):
		pid = f"{TEST_PREFIX}CREATE"
		created = frappe._dict(name="PE-TEST-NEW")
		with patch(f"{MOD}._match_sales_invoice", return_value=self._fake_invoice()), patch(
			f"{MOD}._get_submitted_payment_entry", return_value=None
		), patch(f"{MOD}._create_payment_entry", return_value=created) as create:
			result = self._call(
				{"qbo_payment_id": pid, "event_type": "Create", "amount": 100, "txn_date": "2026-09-15", "qbo_invoice_id": "145"}
			)
		self.assertTrue(result["success"])
		self.assertEqual(result["action"], "created")
		self.assertEqual(result["payment_entry"], "PE-TEST-NEW")
		create.assert_called_once()
		si_arg, event_arg = create.call_args[0]
		self.assertEqual(si_arg.name, "SINV-TEST-QBO")
		self.assertEqual(event_arg["qbo_payment_id"], pid)
		self.assertEqual(event_arg["amount"], 100)
		logs = self._logs(pid)
		self.assertEqual(logs[0].status, "Created")
		self.assertEqual(logs[0].payment_entry, "PE-TEST-NEW")
		self.assertEqual(logs[0].sales_invoice, "SINV-TEST-QBO")
		self.assertFalse(logs[0].warnings)

	def test_amount_mismatch_is_a_warning_not_a_failure(self):
		pid = f"{TEST_PREFIX}WARN"
		with patch(f"{MOD}._match_sales_invoice", return_value=self._fake_invoice(outstanding=250)), patch(
			f"{MOD}._get_submitted_payment_entry", return_value=None
		), patch(f"{MOD}._create_payment_entry", return_value=frappe._dict(name="PE-TEST-WARN")):
			result = self._call({"qbo_payment_id": pid, "event_type": "Create", "amount": 100, "qbo_invoice_id": "145"})
		self.assertTrue(result["success"])
		self.assertIn("differs from invoice outstanding", self._logs(pid)[0].warnings)

	def test_duplicate_create_is_skipped(self):
		pid = f"{TEST_PREFIX}DUP"
		with patch(f"{MOD}._match_sales_invoice", return_value=self._fake_invoice()), patch(
			f"{MOD}._get_submitted_payment_entry", return_value="PE-TEST-EXISTING"
		), patch(f"{MOD}._is_in_sync", return_value=True), patch(
			f"{MOD}._create_payment_entry"
		) as create, patch(f"{MOD}._cancel_payment_entry") as cancel:
			result = self._call({"qbo_payment_id": pid, "event_type": "Create", "amount": 100, "qbo_invoice_id": "145"})
		self.assertTrue(result["success"])
		self.assertEqual(result["action"], "skipped")
		self.assertEqual(result["payment_entry"], "PE-TEST-EXISTING")
		create.assert_not_called()
		cancel.assert_not_called()
		self.assertEqual(self._logs(pid)[0].status, "Skipped-Duplicate")

	def test_update_with_changed_amount_supersedes(self):
		pid = f"{TEST_PREFIX}UPD"
		with patch(f"{MOD}._match_sales_invoice", return_value=self._fake_invoice(outstanding=120)), patch(
			f"{MOD}._get_submitted_payment_entry", return_value="PE-TEST-OLD"
		), patch(f"{MOD}._is_in_sync", return_value=False), patch(
			f"{MOD}._create_payment_entry", return_value=frappe._dict(name="PE-TEST-NEW2")
		) as create, patch(f"{MOD}._cancel_payment_entry") as cancel:
			result = self._call({"qbo_payment_id": pid, "event_type": "Update", "amount": 120, "qbo_invoice_id": "145"})
		self.assertTrue(result["success"])
		self.assertEqual(result["action"], "recreated")
		self.assertEqual(result["superseded_payment_entry"], "PE-TEST-OLD")
		cancel.assert_called_once()
		self.assertEqual(cancel.call_args[0][0], "PE-TEST-OLD")
		self.assertEqual(create.call_args.kwargs.get("superseded"), "PE-TEST-OLD")
		log = self._logs(pid)[0]
		self.assertEqual(log.status, "Superseded")
		self.assertEqual(log.payment_entry, "PE-TEST-NEW2")
		self.assertEqual(log.superseded_payment_entry, "PE-TEST-OLD")

	def test_multiple_linked_invoices_fail_loudly(self):
		pid = f"{TEST_PREFIX}MULTI"
		result = self._call(
			{"qbo_payment_id": pid, "event_type": "Create", "amount": 100, "qbo_invoice_ids": ["145", "146"]}
		)
		self.assertEqual(result["error"], "multiple_invoices_linked")
		self.assertEqual(self._logs(pid)[0].status, "Failed")

	def test_unapplied_payment_fails_loudly(self):
		pid = f"{TEST_PREFIX}UNAPPLIED"
		result = self._call({"qbo_payment_id": pid, "event_type": "Create", "amount": 100})
		self.assertEqual(result["error"], "invoice_not_linked")

	def test_unexpected_exception_rolls_back_and_logs_failed(self):
		pid = f"{TEST_PREFIX}BOOM"
		with patch(f"{MOD}._match_sales_invoice", return_value=self._fake_invoice()), patch(
			f"{MOD}._get_submitted_payment_entry", return_value=None
		), patch(f"{MOD}._create_payment_entry", side_effect=RuntimeError("boom")), patch.object(frappe, "log_error"):
			result = self._call({"qbo_payment_id": pid, "event_type": "Create", "amount": 100, "qbo_invoice_id": "145"})
		self.assertFalse(result["success"])
		self.assertEqual(result["error"], "processing_failed")
		self.assertEqual(frappe.local.response.get("http_status_code"), 500)
		log = self._logs(pid)[0]
		self.assertEqual(log.status, "Failed")
		self.assertIn("boom", log.error_message)

	# -- delete ------------------------------------------------------------

	def test_delete_without_payment_entry_is_noop(self):
		pid = f"{TEST_PREFIX}DELNONE"
		result = self._call({"qbo_payment_id": pid, "event_type": "Delete"})
		self.assertTrue(result["success"])
		self.assertEqual(result["action"], "skipped")
		self.assertEqual(self._logs(pid)[0].status, "Skipped-NoOp")

	def test_delete_cancels_existing_payment_entry(self):
		pid = f"{TEST_PREFIX}DEL"
		with patch(f"{MOD}._get_submitted_payment_entry", return_value="PE-TEST-OLD"), patch(
			f"{MOD}._cancel_payment_entry"
		) as cancel:
			result = self._call({"qbo_payment_id": pid, "event_type": "Delete"})
		self.assertTrue(result["success"])
		self.assertEqual(result["action"], "cancelled")
		cancel.assert_called_once()
		self.assertEqual(cancel.call_args[0][0], "PE-TEST-OLD")
		self.assertEqual(cancel.call_args[0][1], "Delete")
		log = self._logs(pid)[0]
		self.assertEqual(log.status, "Cancelled")
		self.assertEqual(log.payment_entry, "PE-TEST-OLD")

	# -- settings ----------------------------------------------------------

	def test_sync_disabled_skips(self):
		pid = f"{TEST_PREFIX}DISABLED"
		with patch(f"{MOD}._get_settings", return_value={"sync_enabled": 0}):
			result = self._call({"qbo_payment_id": pid, "event_type": "Create", "amount": 1, "qbo_invoice_id": "1"})
		self.assertEqual(result["error"], "sync_disabled")
		self.assertEqual(self._logs(pid)[0].status, "Skipped-NoOp")
