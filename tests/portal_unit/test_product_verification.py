"""Verification decisions remain authoritative across lines and commercial gates."""

import json
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_product_finder_content import FakeDocument, controller
from test_services import ROOT, Record, load_service

BASE = ROOT + ".portal.product_finder"
REASONS = [{"question": "ip", "answer": "IP67", "reason": "Confirm IP67"}]


class Doc(FakeDocument):
	def set(self, key, value):
		self[key] = value

	def save(self, **kw):
		return self


class Verification(unittest.TestCase):
	def context(self):
		self.session = Doc(name="SESSION", quiz_answers="{}")
		self.notifier = MagicMock()
		return load_service(
			BASE + ".verification",
			{
				BASE + ".sessions": types.SimpleNamespace(
					get_owned=MagicMock(return_value=self.session),
					decoded=lambda v: json.loads(v) if isinstance(v, str) else v,
				),
				ROOT + ".portal.staff": types.SimpleNamespace(allowed=lambda cap, user=None: user == "staff"),
				ROOT + ".portal.notifications": types.SimpleNamespace(notify_user=self.notifier),
				ROOT + ".portal.access": types.SimpleNamespace(
					schedule_permission=lambda doc, ptype, user: doc.get("reader") == user
				),
			},
		)

	def test_access_uses_requester_schedule_and_staff(self):
		with self.context() as (service, frappe):
			doc = Doc(requested_by="buyer", state="REQUESTED", schedule="S")
			frappe.get_doc.return_value = Doc(reader="collaborator")
			for user, expected in [
				("buyer", True),
				("collaborator", True),
				("stranger", False),
				("Guest", False),
				("staff", True),
			]:
				self.assertEqual(service.can_access(doc, "read", user), expected)
			doc.state = "VERIFIED"
			self.assertFalse(service.can_access(doc, "write", "buyer"))
			self.assertFalse(service.has_permission(doc, user="buyer", permission_type="write"))

	def test_line_no_token_no_reasons_verified_reuse_and_pending(self):
		with self.context() as (service, frappe):
			line = Doc(line_key="L", verification_status="Pending")
			service.apply_to_line(Doc(name="S"), line, "P", None)
			self.assertIsNone(line.verification_status)
			service.reasons_for = MagicMock(return_value=[])
			service.apply_to_line(Doc(name="S"), line, "P", "T")
			self.assertEqual(line.finder_session, "SESSION")
			self.assertIsNone(line.verification_status)
			service.reasons_for.return_value = REASONS
			frappe.get_all.return_value = [Record(name="V", reasons=json.dumps(REASONS))]
			service.apply_to_line(Doc(name="S"), line, "P", "T")
			self.assertEqual((line.verification_status, line.verification_request), ("Verified", "V"))
			frappe.get_all.return_value = []
			service._open_request = MagicMock(return_value=Doc(name="OPEN"))
			service.apply_to_line(Doc(name="S"), line, "P", "T")
			self.assertEqual((line.verification_status, line.verification_request), ("Pending", "OPEN"))
			self.assertEqual(service._open_request.call_args.args[-1], "L")

	def test_open_reuse_merges_line_keys_without_duplicate_notifications(self):
		with self.context() as (service, frappe):
			frappe.db.get_value.return_value = "V"
			doc = Doc(name="V", line_keys='["L1"]')
			frappe.get_doc.return_value = doc
			service._open_request("P", self.session, REASONS, Doc(name="S"), "L2")
			service._open_request("P", self.session, REASONS, Doc(name="S"), "L2")
			self.assertEqual(json.loads(doc.line_keys), ["L1", "L2"])
			self.notifier.assert_not_called()

	def test_propagation_and_orphan_after_replacement(self):
		with self.context() as (service, frappe):
			line = Doc(name="LINE", line_key="L", verification_request="V", verification_status="Pending")
			schedule = Doc(name="S", is_locked=1, lines=[line], add_comment=MagicMock())
			frappe.get_all.return_value = ["S", "S"]
			frappe.get_doc.return_value = schedule
			service._message = MagicMock()
			service.propagate(Doc(name="V", state="VERIFIED", requested_by="buyer", resolution="Confirmed"))
			self.assertEqual(line.verification_status, "Verified")
			frappe.db.set_value.assert_any_call(
				"ilL-Child-Fixture-Schedule-Line", "LINE", {"verification_status": "Verified"}
			)
			self.notifier.assert_called_once()
			frappe.get_all.return_value = [Record(name="V", line_keys='["L"]')]
			request = Doc(state="REQUESTED", flags=Record())
			frappe.get_doc.return_value = request
			line.verification_request = None
			service.cancel_orphans(schedule)
			self.assertEqual(request.state, "CANCELLED")

	def test_every_gate_setting_and_stage(self):
		with self.context() as (service, frappe):
			for setting in (
				"Before quote is issued and order is placed",
				"Before order only",
				"Warning only",
			):
				frappe.db.get_single_value.return_value = setting
				for stage in ("issue_quote", "order"):
					for status in ("Pending", "Not Feasible"):
						schedule = Doc(lines=[Doc(line_id="L1", verification_status=status)])
						blocked = setting != "Warning only" and (
							stage == "order" or setting != "Before order only"
						)
						if blocked:
							with self.assertRaisesRegex(ValueError, "L1"):
								service.gate(schedule, stage)
						else:
							service.gate(schedule, stage)
					service.gate(Doc(lines=[Doc(verification_status="Verified")]), stage)

	def test_transitions_resolution_and_final_propagation(self):
		verification = types.SimpleNamespace(
			staff=lambda: True,
			TRANSITIONS={"REQUESTED": {"UNDER_REVIEW"}, "UNDER_REVIEW": {"VERIFIED", "NOT_FEASIBLE"}},
			FINAL=("VERIFIED", "NOT_FEASIBLE", "CANCELLED"),
			due_date=lambda: "2026-09-29",
			propagate=MagicMock(),
		)
		with controller("ill_product_verification_request", {BASE + ".verification": verification}) as (
			module,
			_,
		):
			cls = module.ilLProductVerificationRequest
			doc = cls(
				state="VERIFIED",
				resolution="",
				flags=Record(),
				get_doc_before_save=lambda: Record(state="UNDER_REVIEW"),
			)
			with self.assertRaisesRegex(ValueError, "resolution"):
				doc.validate()
			doc.resolution = "Tested"
			doc.validate()
			self.assertEqual(doc.resolved_by, "buyer@example.com")
			doc.on_update()
			verification.propagate.assert_called_once_with(doc)
			doc.get_doc_before_save = lambda: Record(state="REQUESTED")
			with self.assertRaisesRegex(ValueError, "transition"):
				doc.validate()

	def test_business_days_and_integration_contracts(self):
		with self.context() as (service, _):
			self.assertEqual(str(service.due_date()), "2026-09-29")
		root = Path("illumenate_lighting/illumenate_lighting")
		for path, needle in [
			("portal/offers.py", 'gate(schedule, "issue_quote")'),
			("portal/offers.py", 'gate(schedule, "order")'),
			("doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.py", 'gate(self, "order")'),
			("portal/files.py", "ilL-Product-Verification-Request"),
			("portal/queues.py", "ilL-Product-Verification-Request"),
			("portal/quotes.py", "verification_status"),
		]:
			self.assertIn(needle, (root / path).read_text())
