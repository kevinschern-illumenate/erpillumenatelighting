"""Lead webhooks require an integration API user, are throttled and hide internals (SEC-4)."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

LIMITS = []


def _rate_limit(**options):
	def decorate(function):
		LIMITS.append((function.__name__, options))
		return function

	return decorate


class AuthenticationError(Exception):
	pass


class LeadWebhooks(unittest.TestCase):
	def setUp(self):
		LIMITS.clear()
		loaded = load_service(
			ROOT + ".api.webflow_leads",
			{"frappe.rate_limiter": types.SimpleNamespace(rate_limit=_rate_limit)},
		)
		self.module, self.frappe = loaded.__enter__()
		self.addCleanup(loaded.__exit__, None, None, None)
		frappe = self.frappe
		frappe.AuthenticationError = AuthenticationError
		frappe.exceptions = types.SimpleNamespace(
			DuplicateEntryError=type("DuplicateEntryError", (Exception,), {})
		)
		frappe.local.response = {}
		frappe.get_traceback = lambda: "Traceback: secret internals"
		frappe.log_error = MagicMock()
		self.user_types = {"n8n@ill.test": "System User", "dealer@a.test": "Website User"}
		frappe.db.get_value.side_effect = lambda doctype, filters, field=None: (
			self.user_types.get(filters) if doctype == "User" else None
		)
		frappe.db.sql.return_value = []
		self.lead = MagicMock(name="lead")
		self.lead.name = "CRM-LEAD-0001"
		frappe.get_doc.return_value = self.lead

	def as_user(self, user):
		self.frappe.session = Record(user=user)

	def test_guests_and_website_users_are_rejected_before_any_write(self):
		for user in ("Guest", "dealer@a.test"):
			with self.subTest(user=user):
				self.as_user(user)
				self.frappe.local.response = {}
				for call in (
					lambda: self.module.create_lead_from_webflow(first_name="Jo", email="jo@x.test"),
					lambda: self.module.create_lead_from_webflow_webhook(data='{"first_name": "Jo"}'),
				):
					with self.assertRaises(AuthenticationError):
						call()
					self.assertEqual(self.frappe.local.response["http_status_code"], 401)
				self.frappe.get_doc.assert_not_called()

	def test_integration_user_creates_the_lead(self):
		self.as_user("n8n@ill.test")
		result = self.module.create_lead_from_webflow(first_name="Jo", email="jo@x.test", utm_source="google")
		self.assertEqual(result["lead_name"], "CRM-LEAD-0001")
		data = self.frappe.get_doc.call_args.args[0]
		self.assertEqual(
			(data["first_name"], data["email"], data["webflow_utm_source"]), ("Jo", "jo@x.test", "google")
		)
		self.lead.insert.assert_called_once_with(ignore_permissions=True)

	def test_webhook_maps_fields_into_the_same_creation(self):
		self.as_user("n8n@ill.test")
		result = self.module.create_lead_from_webflow_webhook(
			data='{"First Name": "Jo", "Email": "jo@x.test"}'
		)
		self.assertTrue(result["success"])
		self.assertEqual(self.frappe.get_doc.call_args.args[0]["email"], "jo@x.test")

	def test_failures_return_a_generic_message_and_log_the_traceback(self):
		self.as_user("n8n@ill.test")
		self.lead.insert.side_effect = RuntimeError("column webflow_x missing in tabCRM Lead")
		result = self.module.create_lead_from_webflow(first_name="Jo")
		self.assertFalse(result["success"])
		self.assertNotIn("tabCRM", result["error"])
		self.assertIn("Traceback", self.frappe.log_error.call_args.kwargs["message"])
		bad = self.module.create_lead_from_webflow_webhook(data="{not json")
		self.assertEqual(bad["error"], "Invalid JSON")

	def test_both_endpoints_are_throttled_and_post_only(self):
		self.assertEqual(
			dict(LIMITS),
			{
				"create_lead_from_webflow": {"limit": 30, "seconds": 60},
				"create_lead_from_webflow_webhook": {"limit": 30, "seconds": 60},
			},
		)
		for name in ("create_lead_from_webflow", "create_lead_from_webflow_webhook"):
			self.assertEqual(getattr(self.module, name).whitelist_options, {"methods": ["POST"]})


if __name__ == "__main__":
	unittest.main()
