"""Session input validation and owner/claim boundaries."""

import types
import unittest
from datetime import datetime
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

BASE = ROOT + ".portal.product_finder"
DEF = {
	"version": 2,
	"questions": [
		{"id": "family", "type": "family", "options": [{"value": "Driver"}]},
		{"id": "one", "type": "single", "options": [{"value": "a"}]},
		{"id": "multi", "type": "multi", "options": [{"value": "a"}, {"value": "b"}]},
		{"id": "number", "type": "number", "number": {"min": 1, "max": 100}},
		{"id": "range", "type": "range", "number": {"min": 1, "max": 100}},
		{"id": "info", "type": "info"},
	],
}


class Sessions(unittest.TestCase):
	def context(self):
		return load_service(
			BASE + ".sessions", {BASE + ".server_definition": types.SimpleNamespace(load=lambda **kw: DEF)}
		)

	def test_all_answer_validation_rules(self):
		with self.context() as (service, _frappe):
			valid = {
				"family": "Driver",
				"one": "a",
				"multi": '["a", "b"]',
				"number": 5,
				"range": {"low": 1, "high": 10},
			}
			self.assertEqual(service.validate_answers(DEF, valid)["multi"], ["a", "b"])
			for bad in (
				0,
				False,
				[1],
				{str(i): 1 for i in range(41)},
				{"unknown": "x"},
				{"one": "x"},
				{"multi": ["x"]},
				{"number": float("nan")},
				{"number": 101},
				{"number": True},
				{"range": {"low": 5, "high": 2}},
				{"range": {"low": 1}},
				{"info": "x"},
				{"one": "a" * 17000},
			):
				with self.subTest(bad=str(bad)[:50]), self.assertRaises(ValueError):
					service.validate_answers(DEF, bad)

	def test_missing_foreign_and_guest_have_identical_errors(self):
		with self.context() as (service, frappe):
			frappe.db.get_value.return_value = None
			with self.assertRaisesRegex(PermissionError, service.DENIED):
				service.get_owned("missing")
			frappe.db.get_value.return_value = "S"
			frappe.get_doc.return_value = Record(user="other", status="Active")
			with self.assertRaisesRegex(PermissionError, service.DENIED):
				service.get_owned("foreign")
			frappe.session.user = "Guest"
			with self.assertRaisesRegex(PermissionError, service.DENIED):
				service.get_owned("owned")

	def test_claim_single_use_and_age(self):
		with self.context() as (service, frappe):
			frappe.db.get_value.return_value = "S"
			for doc in [
				Record(user="buyer", claimed_on=None, status="Completed", creation="2026-09-24"),
				Record(user=None, claimed_on="2026-09-24", status="Completed", creation="2026-09-24"),
				Record(user=None, claimed_on=None, status="Completed", creation="2026-09-01"),
			]:
				frappe.get_doc.return_value = doc
				with self.assertRaises(PermissionError):
					service.claim("token")
			doc = MagicMock()
			doc.user = None
			doc.claimed_on = None
			doc.status = "Completed"
			doc.creation = datetime(2026, 9, 24)
			frappe.get_doc.return_value = doc
			service._complete_doc = MagicMock(return_value={"catalog_url": "/portal/products?finder=token"})
			self.assertEqual(service.claim("token")["token"], "token")
			self.assertEqual(doc.user, frappe.session.user)

	def test_expiry_and_guest_retention(self):
		with self.context() as (service, frappe):
			frappe.db.get_single_value.return_value = 30
			frappe.get_all.return_value = [
				Record(
					name="P", user="buyer", creation="2026-07-01", last_seen="2026-07-01", status="Active"
				),
				Record(name="G", user=None, creation="2026-09-01", status="Completed"),
				Record(name="D", user=None, creation="2026-07-01", status="Expired"),
			]
			frappe.delete_doc = MagicMock()
			service.expire_sessions()
			self.assertEqual(frappe.db.set_value.call_count, 2)
			frappe.delete_doc.assert_called_once_with(service.DOCTYPE, "D", ignore_permissions=True)

	def test_save_complete_and_result_refresh(self):
		from test_product_finder_content import FakeDocument

		with self.context() as (service, frappe):
			doc = FakeDocument(
				user=frappe.session.user,
				status="Active",
				session_token="T",
				quiz_answers="{}",
				save=MagicMock(),
				db_set=MagicMock(),
			)
			service.get_owned = MagicMock(return_value=doc)
			service.save_answers("T", {"one": "a"}, include_inactive=True)
			self.assertEqual(doc.quiz_answers, '{"one":"a"}')
			self.assertEqual(doc.definition_version, 2)
			self.assertIsNone(doc.result_stamp)
			service._complete_doc = MagicMock(return_value={"catalog_url": "/portal/products?finder=T"})
			service.complete("T", include_inactive=True)
			service._complete_doc.assert_called_with(doc, include_inactive=True)
			service.stamp = lambda: "new"
			doc.result_json = "{}"
			doc.result_stamp = "old"
			self.assertEqual(service.result("T")["catalog_url"], "/portal/products?finder=T")

	def test_owner_permissions_and_escaped_query_condition(self):
		with self.context() as (service, frappe):
			service._staff = lambda user: user == "staff"
			frappe.db.escape = lambda value: "'" + value.replace("'", "''") + "'"
			doc = Record(user="buyer'o")
			self.assertTrue(service.has_permission(doc, user="buyer'o"))
			self.assertFalse(service.has_permission(doc, user="buyer'o", permission_type="write"))
			self.assertFalse(service.has_permission(doc, user="Guest"))
			self.assertTrue(service.has_permission(doc, user="staff", permission_type="write"))
			self.assertIn("buyer''o", service.get_permission_query_conditions("buyer'o"))
			self.assertEqual(service.get_permission_query_conditions("Guest"), "1=0")
