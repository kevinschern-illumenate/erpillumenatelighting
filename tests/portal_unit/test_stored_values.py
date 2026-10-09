"""Immutability guards compare in-memory string dates with the DB's date objects."""

import types
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import test_reviews
from test_build_immutability import FakeDocument, Row, document_module
from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.stored_values import same

DOCTYPE = ROOT + ".doctype."


class Same(unittest.TestCase):
	def test_string_and_stored_dates_are_the_same_value(self):
		self.assertTrue(same("2026-10-08 15:31:00.123456", datetime(2026, 10, 8, 15, 31, 0, 123456)))
		self.assertTrue(same(date(2026, 11, 7), "2026-11-07"))
		self.assertTrue(same(None, ""))
		self.assertTrue(same("HASH", "HASH"))

	def test_real_changes_still_differ(self):
		self.assertFalse(same("2026-10-09 15:31:00", datetime(2026, 10, 8, 15, 31)))
		self.assertFalse(same(date(2026, 11, 7), "2026-11-08"))
		self.assertFalse(same(None, date(2026, 11, 7)))
		self.assertFalse(same(date(2026, 11, 7), "not a date"))
		self.assertFalse(same("HASH", "OTHER"))


STORED_OFFER = {
	"quotation": "QTN-1",
	"quote_request": "QR-1",
	"schedule": "S1",
	"customer": "A",
	"valid_until": date(2026, 11, 7),
	"issued_by": "sales@example.com",
	"issued_on": datetime(2026, 10, 8, 15, 31, 0, 123456),
	"snapshot_json": "{}",
	"snapshot_hash": "SNAP",
	"schedule_hash": "SCOPE",
}


class QuoteOfferIssue(unittest.TestCase):
	def offer(self, **changes):
		with load_service(
			DOCTYPE + "ill_quote_offer.ill_quote_offer", {"frappe.model.document": document_module()}
		) as (module, _frappe):
			# on_submit inserts with string dates, attaches the PDF and saves the same object again.
			current = {**STORED_OFFER, "valid_until": "2026-11-07", "issued_on": "2026-10-08 15:31:00.123456"}
			doc = module.ilLQuoteOffer([], {**current, **changes}, FakeDocument([], dict(STORED_OFFER)))
			doc.flags.offer_write = True
			return doc

	def test_pdf_attachment_save_after_issue_is_not_a_content_change(self):
		self.offer(pdf_file="FILE-1", pdf_sha256="SHA").validate()

	def test_changed_terms_are_still_immutable(self):
		with self.assertRaisesRegex(ValueError, "immutable"):
			self.offer(valid_until="2026-12-31").validate()


class OrderIntakeDecisions(unittest.TestCase):
	def test_desk_resave_keeps_append_only_decisions(self):
		with load_service(
			DOCTYPE + "ill_order_intake.ill_order_intake", {"frappe.model.document": document_module()}
		) as (module, _frappe):
			decision = {"action": "ACKNOWLEDGED", "actor": "b@example.com", "revision_hash": "H"}
			old = FakeDocument(
				[],
				{"state": "UNDER_REVIEW", "decisions": [Row(decision, recorded_on=datetime(2026, 10, 8, 9))]},
			)
			current = {
				"state": "UNDER_REVIEW",
				"decisions": [Row(decision, recorded_on="2026-10-08 09:00:00")],
			}
			module.ilLOrderIntake([], current, old).validate()
			current["decisions"][0]["note"] = "rewritten"
			with self.assertRaisesRegex(ValueError, "append-only"):
				module.ilLOrderIntake([], current, old).validate()


class ConfirmedDeliveryPromise(unittest.TestCase):
	def test_submitting_an_order_with_an_unchanged_confirmed_date(self):
		with load_service(ROOT + ".portal.order_review", test_reviews.OrderApproval().dependencies()) as (
			module,
			frappe,
		):
			old = Record(
				ill_confirmed_delivery_date=date(2020, 11, 1),
				ill_delivery_confirmed_by="sales@example.com",
				ill_delivery_confirmed_on=datetime(2020, 10, 1, 9),
			)
			# The Desk form posts the stored (now past) date back as a string on Submit.
			data = {
				"name": "SO-PORTAL",
				"ill_fixture_schedule": "S1",
				"amended_from": None,
				"docstatus": 1,
				"ill_confirmed_delivery_date": "2020-11-01",
				"ill_delivery_confirmed_by": "sales@example.com",
				"ill_delivery_confirmed_on": "2020-10-01 09:00:00",
			}
			order = types.SimpleNamespace(**data)
			order.get = lambda field: getattr(order, field, None)
			order.get_doc_before_save = lambda: old
			frappe.db.exists.return_value = "INTAKE-1"
			with patch.object(module, "_staff") as staff:
				module.validate_order(order)
			staff.assert_not_called()
			self.assertEqual(order.ill_delivery_confirmed_by, "sales@example.com")
			self.assertEqual(order.ill_delivery_confirmed_on, old.ill_delivery_confirmed_on)
			order.ill_confirmed_delivery_date = "2026-12-01"
			with patch.object(module, "_staff"), self.assertRaisesRegex(ValueError, "order-change workflow"):
				module.validate_order(order)


class TemplateSandbox(unittest.TestCase):
	def test_templates_do_not_call_helpers_missing_from_frappes_sandbox(self):
		# Frappe's Jinja sandbox exposes only whitelisted ``frappe.utils`` data helpers;
		# anything else resolves to None and fails the page with "'NoneType' object is not callable".
		root = Path(__file__).parents[2] / "illumenate_lighting"
		for path in [*root.glob("templates/**/*.html"), *root.glob("**/print_format/**/*.html")]:
			self.assertNotIn("frappe.utils.sanitize_html", path.read_text(), path)
