"""Invitations are emailed through the outbox, even to people without an account (FLOW-4)."""

import hashlib
import types
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

NOW = datetime(2026, 10, 14, 12)


def utilities(frappe):
	frappe.utils.now_datetime = lambda: NOW
	frappe.utils.add_days = lambda value, days: datetime(2026, 10, 14 + days, 12)
	frappe.utils.escape_html = lambda value: str(value).replace("<", "&lt;").replace(">", "&gt;")
	frappe.utils.get_url = lambda path: "https://portal.test" + path
	frappe.utils.format_date = lambda value: str(value)[:10]
	frappe.utils.validate_email_address = lambda value: "@" in value


class OutboxInvitations(unittest.TestCase):
	def test_address_without_account_gets_a_logged_delivery(self):
		with load_service(ROOT + ".portal.outbox") as (module, frappe):
			utilities(frappe)
			inserted = []
			frappe.get_doc.side_effect = lambda values: Record(
				values, flags=Record(), insert=lambda **kw: inserted.append(values)
			)
			frappe.db.exists.return_value = False
			frappe.db.get_value.return_value = Record(
				state="Pending", email="architect@studio.test", expires_on=datetime(2026, 10, 21)
			)
			self.assertTrue(
				module.record_invitation("INV-1", " Architect@Studio.test ", "Invited", "<p>link</p>", "hash")
			)
			event, delivery = inserted
			self.assertEqual(
				(event["reference_type"], event["preference"]), ("ilL-Portal-Invitation", "invitation")
			)
			self.assertIsNone(delivery["recipient"])
			self.assertEqual(delivery["recipient_email"], "architect@studio.test")
			self.assertEqual(delivery["state"], "PENDING")

	def test_used_revoked_expired_or_foreign_invitations_are_skipped(self):
		event = Record(
			preference="invitation", reference_type="ilL-Portal-Invitation", reference_name="INV-1"
		)
		cases = {
			"used": (
				Record(state="Accepted", email="a@x.test", expires_on=datetime(2026, 10, 21)),
				"a@x.test",
			),
			"expired": (
				Record(state="Pending", email="a@x.test", expires_on=datetime(2026, 10, 13)),
				"a@x.test",
			),
			"foreign": (
				Record(state="Pending", email="a@x.test", expires_on=datetime(2026, 10, 21)),
				"b@x.test",
			),
			"missing": (None, "a@x.test"),
		}
		for case, (invite, email) in cases.items():
			with self.subTest(case=case), load_service(ROOT + ".portal.outbox") as (module, frappe):
				utilities(frappe)
				frappe.db.get_value.return_value = invite
				self.assertEqual(module.eligibility(event, email)[0], "SKIPPED")

	def test_dispatch_sends_to_the_bare_email(self):
		with load_service(ROOT + ".portal.outbox") as (module, frappe):
			delivery = Record(
				name="DEL1",
				recipient=None,
				recipient_email="architect@studio.test",
				event="E1",
				state="PENDING",
				attempts=0,
				email_queue=None,
			)
			frappe.get_doc.side_effect = [delivery, Record(subject="Invited", message="<p>link</p>")]
			frappe.sendmail = MagicMock(return_value=Record(name="EMAIL1"))
			with patch.object(module, "eligibility", return_value=("PENDING", "Ready")) as eligible:
				module.dispatch_one("DEL1")
			self.assertEqual(eligible.call_args.args[1], "architect@studio.test")
			self.assertEqual(frappe.sendmail.call_args.kwargs["recipients"], ["architect@studio.test"])


class AccountInvitations(unittest.TestCase):
	def service(self):
		self.outbox = types.SimpleNamespace(record_invitation=MagicMock(return_value=True))
		return load_service(
			ROOT + ".portal.accounts",
			{
				ROOT + ".portal.access": types.SimpleNamespace(get_actor=MagicMock()),
				ROOT + ".portal.staff": types.SimpleNamespace(allowed=MagicMock(return_value=True)),
				ROOT + ".portal.outbox": self.outbox,
			},
		)

	def test_invite_emails_the_link_and_still_returns_it(self):
		with self.service() as (module, frappe):
			utilities(frappe)
			frappe.session = Record(user="dealer@acme.test")
			frappe.db.get_value.side_effect = lambda doctype, name, field=None, *a, **kw: {
				("User", "enabled"): 1,
				("User", "full_name"): "Dana <Dealer>",
				("ilL-Project", "project_name"): "Lobby Refit",
			}.get((doctype, field))
			frappe.db.exists.return_value = False
			frappe.get_doc.side_effect = lambda values: Record(
				values, name="INV-1", flags=Record(), insert=lambda **kw: None
			)
			with patch.object(module, "_invite_authority"):
				result = module.invite("Architect@Studio.test", "Ada", project="P-1", access_level="EDIT")
			self.assertTrue(result["emailed"])
			token = result["invite_url"].split("#", 1)[1]
			name, email, subject, message, event_key = self.outbox.record_invitation.call_args.args
			self.assertEqual((name, email), ("INV-1", "architect@studio.test"))
			self.assertIn("https://portal.test/portal/accept-invitation#" + token, message)
			self.assertEqual(event_key, hashlib.sha256(token.encode()).hexdigest())
			self.assertIn("Lobby Refit", subject)
			self.assertIn("Dana &lt;Dealer&gt;", message)
			self.assertIn("view and edit", message)

	def test_resend_replaces_the_link_and_extends_the_expiry(self):
		with self.service() as (module, frappe):
			utilities(frappe)
			frappe.db.get_value.return_value = "Someone"
			doc = Record(
				name="INV-1",
				state="Pending",
				email="a@x.test",
				project="P-1",
				customer=None,
				token_hash="old",
				expires_on=datetime(2026, 10, 15),
				invited_by="dealer@acme.test",
				access_level="VIEW",
				first_name="Ada",
			)
			doc.update = lambda values: dict.update(doc, values)
			frappe.get_doc.return_value = doc
			with patch.object(module, "_invite_authority"), patch.object(module, "_login"):
				result = module.resend_invitation("INV-1")
			stored = frappe.db.set_value.call_args.args[2]
			token = result["invite_url"].split("#", 1)[1]
			self.assertEqual(stored["token_hash"], hashlib.sha256(token.encode()).hexdigest())
			self.assertEqual(stored["expires_on"], datetime(2026, 10, 21, 12))
			self.assertEqual(self.outbox.record_invitation.call_args.args[4], stored["token_hash"])

	def test_only_pending_invitations_are_resent(self):
		with self.service() as (module, frappe):
			utilities(frappe)
			frappe.get_doc.return_value = Record(name="INV-1", state="Accepted", project="P-1", customer=None)
			with patch.object(module, "_invite_authority"), patch.object(module, "_login"):
				with self.assertRaises(ValueError):
					module.resend_invitation("INV-1")
			self.outbox.record_invitation.assert_not_called()

	def test_preview_explains_each_state(self):
		pending = Record(
			name="INV-1",
			email="a@x.test",
			project="P-1",
			customer=None,
			invited_by="dealer@acme.test",
			state="Pending",
			expires_on=datetime(2026, 10, 21),
		)
		cases = (
			(None, {"valid": False, "reason": "invalid"}),
			(Record(pending, state="Accepted"), {"valid": False, "reason": "used"}),
			(Record(pending, state="Revoked"), {"valid": False, "reason": "revoked"}),
			(Record(pending, expires_on=datetime(2026, 10, 1)), {"valid": False, "reason": "expired"}),
		)
		for invite, expected in cases:
			with self.subTest(expected=expected), self.service() as (module, frappe):
				utilities(frappe)
				frappe.db.get_value.return_value = invite
				self.assertEqual(module.invitation_preview("token"), expected)
		with self.service() as (module, frappe):
			utilities(frappe)
			frappe.session = Record(user="Guest")
			frappe.db.exists.return_value = False
			frappe.db.get_value.side_effect = lambda doctype, *a, **kw: (
				pending
				if doctype == "ilL-Portal-Invitation"
				else ("Lobby Refit" if doctype == "ilL-Project" else "Dana")
			)
			preview = module.invitation_preview("token")
			self.assertEqual(
				preview,
				{
					"valid": True,
					"email": "a@x.test",
					"target": "Lobby Refit",
					"kind": "project",
					"inviter": "Dana",
					"has_account": False,
					"signed_in_as": None,
				},
			)


if __name__ == "__main__":
	unittest.main()
