"""Hardening plan 1.2: signed QuickBooks webhooks run as a least-privilege user."""

import hashlib
import hmac
import json
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

SECRET = "s3cret"


def utils():
	module = types.ModuleType("frappe.utils")
	module.flt = lambda value, precision=None: float(value or 0)
	module.cint = lambda value: int(value or 0)
	module.getdate = lambda value: str(value)[:10]
	module.nowdate = lambda: "2026-11-04"
	module.now_datetime = lambda: "2026-11-04 12:00:00"
	module.add_to_date = lambda value, minutes=0: value
	return {module.__name__: module}


class SignedWebhooks(unittest.TestCase):
	def load(self, body, *, secret=SECRET, signature=None, length=None, users=None, conf=None):
		context = load_service(ROOT + ".api.qbo_sync", utils())
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.request = MagicMock()
		frappe.request.get_data.return_value = body
		frappe.request.content_length = len(body) if length is None else length
		frappe.local.response = {}
		frappe.local.request_ip = "127.0.0.1"
		frappe.conf = Record(qbo_webhook_secret=secret, **(conf or {}))
		frappe.get_request_header = lambda header: (
			signature if signature is not None else hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
		)
		frappe.set_user = MagicMock()
		frappe.log_error = MagicMock()
		enabled = {"qbo-integration@illumenate.lighting": 1} if users is None else users
		frappe.db.get_value.side_effect = lambda doctype, name, field=None, *a, **k: enabled.get(name) if doctype == "User" else None
		return module, frappe

	def test_signed_json_is_returned(self):
		body = json.dumps({"qbo_payment_id": "1"}).encode()
		module, _frappe = self.load(body)
		self.assertEqual(module.read_signed_json(), ({"qbo_payment_id": "1"}, None))

	def test_oversized_bodies_are_refused_before_hashing(self):
		for declared in (module_cap := 256 * 1024 + 1, None):
			body = b"{}" if declared else b" " * module_cap
			module, frappe = self.load(body, length=declared)
			payload, refused = module.read_signed_json()
			self.assertIsNone(payload)
			self.assertEqual(refused["error"], "payload_too_large")
			self.assertEqual(frappe.local.response["http_status_code"], 413)
			frappe.log_error.assert_not_called()

	def test_blank_or_missing_secrets_never_verify(self):
		for secret in ("", "   ", None):
			body = b"{}"
			signature = hmac.new((secret or "").encode(), body, hashlib.sha256).hexdigest()
			module, frappe = self.load(body, secret=secret, signature=signature)
			settings = MagicMock()
			settings.get_password.return_value = secret
			frappe.get_cached_doc = MagicMock(return_value=settings)
			payload, refused = module.read_signed_json()
			self.assertEqual(refused["error"], "unauthorized")
			self.assertEqual(frappe.local.response["http_status_code"], 401)

	def test_bad_signature_and_bad_json_are_refused(self):
		module, _frappe = self.load(b"{}", signature="deadbeef")
		self.assertEqual(module.read_signed_json()[1]["error"], "unauthorized")
		module, _frappe = self.load(b"[1]")
		self.assertEqual(module.read_signed_json()[1]["error"], "invalid_json")

	def test_requests_run_as_the_integration_user(self):
		module, frappe = self.load(b"{}")
		self.assertIsNone(module.become_integration_user())
		frappe.set_user.assert_called_once_with("qbo-integration@illumenate.lighting")

	def test_site_config_can_point_at_another_user(self):
		module, frappe = self.load(b"{}", users={"n8n@example.com": 1}, conf={"ill_service_users": {"qbo": "n8n@example.com"}})
		self.assertIsNone(module.become_integration_user())
		frappe.set_user.assert_called_once_with("n8n@example.com")

	def test_missing_user_returns_503_so_the_sender_retries(self):
		module, frappe = self.load(b"{}", users={})
		refused = module.become_integration_user()
		self.assertEqual(refused["error"], "integration_user_unavailable")
		self.assertEqual(frappe.local.response["http_status_code"], 503)
		frappe.set_user.assert_not_called()
		frappe.log_error.assert_called_once()

	def test_rollback_flag_restores_administrator(self):
		module, frappe = self.load(b"{}", users={}, conf={"qbo_webhooks_run_as_administrator": "1"})
		self.assertIsNone(module.become_integration_user())
		frappe.set_user.assert_called_once_with("Administrator")

	def test_no_receiver_switches_to_administrator_directly(self):
		from pathlib import Path

		api = Path(__file__).resolve().parents[2] / "illumenate_lighting" / "illumenate_lighting" / "api"
		for name in ("qbo_sync.py", "qbo_invoices.py", "qbo_bills.py"):
			source = (api / name).read_text(encoding="utf-8")
			with self.subTest(name=name):
				self.assertEqual(source.count('set_user("Administrator")'), 1 if name == "qbo_sync.py" else 0)
				if name != "qbo_sync.py":
					self.assertIn("become_integration_user()", source)
					self.assertIn("read_signed_json()", source)


class ServiceUser(unittest.TestCase):
	def test_qbo_user_is_a_system_user_with_only_integration_and_accounts_roles(self):
		with load_service(ROOT + ".portal.service_users") as (module, _frappe):
			self.assertEqual(module.SERVICE_USERS["qbo"]["roles"], ("ilL Integration", "Accounts User"))
			self.assertNotIn("System Manager", module.SERVICE_USERS["qbo"]["roles"])


if __name__ == "__main__":
	unittest.main()
