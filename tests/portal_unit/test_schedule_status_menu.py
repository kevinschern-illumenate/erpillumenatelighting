"""The schedule status menu offers only reachable states, and leaving QUOTED
supersedes the issued offer instead of silently stranding it (REL-4)."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


def controller():
	document = types.ModuleType("frappe.model.document")
	document.Document = object
	return load_service(
		ROOT + ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule",
		{"frappe.model.document": document},
	)


class StatusMenu(unittest.TestCase):
	def test_quoted_is_never_a_manual_target(self):
		with controller() as (module, _frappe):
			self.assertNotIn("QUOTED", module.PORTAL_SETTABLE_STATUSES)
			for internal in (False, True):
				module._is_internal_user = lambda user, internal=internal: internal
				for status in ("DRAFT", "READY", "QUOTED", "ISSUE", "ORDER_REQUESTED", "ORDERED", "CLOSED"):
					with self.subTest(status=status, internal=internal):
						self.assertNotIn("QUOTED", module.allowed_portal_transitions(status, "u@x.test"))

	def test_setting_quoted_by_hand_is_refused(self):
		with controller() as (module, _frappe):
			schedule = Record(status="READY", name="S-1", save=MagicMock())
			with self.assertRaises(ValueError):
				module.transition_schedule_status(schedule, "QUOTED", "dealer@a.test")
			schedule.save.assert_not_called()


class LeavingQuoted(unittest.TestCase):
	def test_open_offer_is_superseded_and_sales_is_told(self):
		with controller() as (module, frappe):
			module._is_internal_user = lambda user: False
			offer = Record(
				name="OFFER-1", state="ISSUED", quote_request="QR-1", flags=Record(), save=MagicMock()
			)
			request = Record(name="QR-1", add_comment=MagicMock())
			new_version = Record(db_set=MagicMock())
			docs = {("ilL-Quote-Offer", "OFFER-1"): offer, ("ilL-Quote-Request", "QR-1"): request}
			frappe.get_doc.side_effect = lambda doctype, name: docs.get((doctype, name), new_version)
			frappe.get_all.return_value = ["OFFER-1"]
			schedule = Record(
				doctype="ilL-Project-Fixture-Schedule",
				name="S-1",
				status="QUOTED",
				create_new_version=MagicMock(return_value="S-1-v2"),
				get_linked_sales_order=lambda: None,
			)
			outcome = module.transition_schedule_status(schedule, "DRAFT", "dealer@a.test")
			self.assertEqual(outcome["new_schedule_name"], "S-1-v2")
			self.assertEqual(
				frappe.get_all.call_args.kwargs["filters"], {"schedule": "S-1", "state": "ISSUED"}
			)
			self.assertEqual(offer.state, "SUPERSEDED")
			self.assertTrue(offer.flags.offer_write)
			offer.save.assert_called_once_with(ignore_permissions=True)
			comment = request.add_comment.call_args.args[1]
			self.assertIn("OFFER-1", comment)
			self.assertIn("S-1-v2", comment)


if __name__ == "__main__":
	unittest.main()
