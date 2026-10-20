# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Tests for the Sales Invoice QuickBooks id write-back endpoint.

Run inside a bench:
    bench --site <site> run-tests --app illumenate_lighting \
        --module illumenate_lighting.illumenate_lighting.api.test_qbo_invoices

The database reads and writes are mocked against an in-memory table so the
tests don't depend on a seeded Customer/Sales Invoice; auth, conflict and
amendment handling run for real.
"""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from illumenate_lighting.illumenate_lighting.api import qbo_invoices, qbo_sync

MOD = "illumenate_lighting.illumenate_lighting.api.qbo_invoices"
SYNC_MOD = "illumenate_lighting.illumenate_lighting.api.qbo_sync"
SECRET = "test-secret-do-not-use"


def _sign(body: bytes, secret: str = SECRET) -> str:
	return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestQBOInvoices(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.local.request_ip = "127.0.0.1"
		frappe.local.form_dict = frappe._dict(cmd=f"{MOD}.receive_invoice_link")
		frappe.local.response = frappe._dict()
		self.rows = {
			("Sales Invoice", "SINV-TEST-QBO"): {"customer": "Test Customer", "custom_qbo_id": None},
			("Customer", "Test Customer"): {"custom_qbo_id": None},
		}
		self.writes = []

	# -- helpers -----------------------------------------------------------

	def _get_value(self, doctype, name, field):
		return (self.rows.get((doctype, name)) or {}).get(field)

	def _set_value(self, doctype, name, field, value, update_modified=True):
		self.writes.append((doctype, name, field, value))
		self.rows[(doctype, name)][field] = value

	def _call(self, payload, signature=None):
		body = json.dumps(payload).encode()
		if signature is None:
			signature = _sign(body)
		request = MagicMock()
		request.get_data.return_value = body
		request.method = "POST"
		meta = MagicMock()
		meta.has_field.side_effect = lambda field: field == "amended_from"
		with (
			patch.object(frappe, "request", request),
			patch(f"{SYNC_MOD}._get_webhook_secret", return_value=SECRET),
			patch.object(
				frappe,
				"get_request_header",
				side_effect=lambda h: signature if h == qbo_sync.SIGNATURE_HEADER else None,
			),
			patch.object(frappe.db, "exists", side_effect=lambda dt, name: (dt, name) in self.rows),
			patch.object(frappe.db, "get_value", side_effect=self._get_value),
			patch.object(frappe.db, "set_value", side_effect=self._set_value),
			patch.object(frappe, "get_meta", return_value=meta),
			patch(f"{MOD}._commit"),
		):
			return qbo_invoices.receive_invoice_link()

	# -- tests -------------------------------------------------------------

	def test_bad_signature_rejected_without_writes(self):
		with patch.object(frappe, "log_error") as log_error:
			result = self._call(
				{"sales_invoice": "SINV-TEST-QBO", "qbo_invoice_id": "145"}, signature="deadbeef"
			)
		self.assertEqual(result["error"], "unauthorized")
		self.assertEqual(frappe.local.response.get("http_status_code"), 401)
		self.assertEqual(self.writes, [])
		log_error.assert_called_once()

	def test_link_saves_invoice_and_customer_ids(self):
		result = self._call(
			{"sales_invoice": "SINV-TEST-QBO", "qbo_invoice_id": "145", "customer_qbo_id": "62"}
		)
		self.assertTrue(result["success"])
		self.assertEqual(result["customer"], "Test Customer")
		self.assertEqual(self.rows[("Sales Invoice", "SINV-TEST-QBO")]["custom_qbo_id"], "145")
		self.assertEqual(self.rows[("Customer", "Test Customer")]["custom_qbo_id"], "62")

	def test_different_existing_id_returns_409(self):
		self.rows[("Sales Invoice", "SINV-TEST-QBO")]["custom_qbo_id"] = "100"
		result = self._call({"sales_invoice": "SINV-TEST-QBO", "qbo_invoice_id": "145"})
		self.assertEqual(result["error"], "qbo_id_conflict")
		self.assertEqual(frappe.local.response.get("http_status_code"), 409)
		self.assertEqual(self.writes, [])

	def test_amended_invoice_replaces_inherited_id(self):
		self.rows[("Sales Invoice", "SINV-TEST-QBO")]["custom_qbo_id"] = "100"
		self.rows[("Sales Invoice", "SINV-TEST-QBO-1")] = {
			"customer": "Test Customer",
			"custom_qbo_id": "100",
			"amended_from": "SINV-TEST-QBO",
		}
		result = self._call({"sales_invoice": "SINV-TEST-QBO-1", "qbo_invoice_id": "145"})
		self.assertTrue(result["success"])
		self.assertEqual(self.rows[("Sales Invoice", "SINV-TEST-QBO-1")]["custom_qbo_id"], "145")
		self.assertEqual(self.rows[("Sales Invoice", "SINV-TEST-QBO")]["custom_qbo_id"], "100")
