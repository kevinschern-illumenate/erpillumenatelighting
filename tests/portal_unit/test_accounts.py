"""Account scope, invitation replay and reviewed master-data changes (Frappe boundary doubles)."""

import types
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service


class Accounts(unittest.TestCase):
	def dependencies(self):
		return {
			ROOT + ".portal.access": types.SimpleNamespace(get_actor=MagicMock()),
			ROOT + ".portal.staff": types.SimpleNamespace(allowed=MagicMock(return_value=True)),
		}

	def test_dealer_cannot_select_another_company_or_staff_scope(self):
		with load_service(ROOT + ".portal.accounts", self.dependencies()) as (module, frappe):
			actor = types.SimpleNamespace(user="buyer", is_dealer=True, is_guest=False, customer="OWN")
			with patch.object(module, "get_actor", return_value=actor):
				with self.assertRaises(PermissionError):
					module._invite_authority("FOREIGN")
				with self.assertRaisesRegex(ValueError, "VIEW or EDIT"):
					module.invite("member@example.com", "Member", access_level="System Manager")
			frappe.get_doc.assert_not_called()

	def test_shared_or_foreign_address_cannot_be_changed(self):
		with load_service(ROOT + ".portal.accounts", self.dependencies()) as (module, _frappe):
			foreign = Record(links=[Record(link_doctype="Customer", link_name="FOREIGN")])
			with self.assertRaises(PermissionError):
				module.require_owned(foreign, "OWN")
			foreign.links.append(Record(link_doctype="Customer", link_name="OWN"))
			self.assertIs(module.require_owned(foreign, "OWN"), foreign)
			with self.assertRaises(PermissionError):
				module.require_owned(foreign, "OWN", exclusive=True)

	def test_contact_email_cannot_bind_an_existing_user(self):
		with load_service(ROOT + ".portal.accounts", self.dependencies()) as (module, frappe):
			frappe.db.exists.return_value = True
			doc = MagicMock()
			doc.get.return_value = None
			with self.assertRaisesRegex(ValueError, "invitation"):
				module._apply_contact(doc, {"email_id": "foreign@example.com"})
			doc.set.assert_not_called()

	def test_invitation_replay_expiry_wrong_actor_and_revoked_inviter(self):
		for failure in ("replay", "expired", "actor", "inviter"):
			with (
				self.subTest(failure=failure),
				load_service(ROOT + ".portal.accounts", self.dependencies()) as (module, frappe),
			):
				frappe.db.get_value.return_value = "INVITE"
				frappe.utils.now_datetime = lambda: datetime(2026, 9, 25, 12)
				doc = Record(
					name="INVITE",
					email="buyer@example.com",
					state="Accepted" if failure == "replay" else "Pending",
					expires_on="2026-09-24" if failure == "expired" else "2026-10-01",
					customer="OWN",
					project=None,
					invited_by="dealer",
				)
				user = Record(
					name="wrong@example.com" if failure == "actor" else "buyer@example.com",
					user_type="Website User",
					enabled=1,
				)
				frappe.get_doc.side_effect = [doc, user]
				with patch.object(
					module,
					"_invite_authority",
					side_effect=PermissionError("revoked") if failure == "inviter" else None,
				):
					with self.assertRaises((ValueError, PermissionError)):
						module.accept_invitation("token")
				frappe.db.set_value.assert_not_called()

	def test_acceptance_retains_member_roles_and_binds_only_named_company(self):
		with load_service(ROOT + ".portal.accounts", self.dependencies()) as (module, frappe):
			frappe.db.get_value.return_value = "INVITE"
			frappe.utils.now_datetime = lambda: datetime(2026, 9, 25, 12)
			doc = Record(
				name="INVITE",
				email="buyer@example.com",
				state="Pending",
				expires_on="2026-10-01",
				customer="OWN",
				project=None,
				invited_by="dealer",
			)
			user = Record(name="buyer@example.com", user_type="Website User", enabled=1)
			frappe.get_doc.side_effect = [doc, user]
			with (
				patch.object(module, "_invite_authority"),
				patch.object(module, "get_actor", return_value=Record(customer="OWN")),
				patch.object(module, "_link_member") as link,
			):
				module.accept_invitation("token")
				link.assert_called_once_with(user, "OWN")
			self.assertEqual(frappe.db.set_value.call_args.args[2]["state"], "Accepted")
			self.assertNotIn("roles", user)

	def test_staff_cannot_apply_stale_address_change(self):
		with load_service(ROOT + ".portal.accounts", self.dependencies()) as (module, frappe):
			request = Record(
				request_type="Address change",
				reference_name="A",
				customer="OWN",
				expected_modified="old",
				proposed_json='{"city":"New City"}',
			)
			doc = Record(modified="new", links=[Record(link_doctype="Customer", link_name="OWN")])
			frappe.get_doc.return_value = doc
			with self.assertRaisesRegex(ValueError, "source changed"):
				module._apply_request(request, None)
			self.assertNotIn("city", doc)

	def test_disabled_dealer_cannot_manage_company(self):
		with load_service(ROOT + ".portal.accounts", self.dependencies()) as (module, frappe):
			frappe.db.get_value.return_value = 0
			with patch.object(
				module,
				"get_actor",
				return_value=Record(user="buyer", is_dealer=True, is_guest=False, customer="OWN"),
			):
				with self.assertRaises(PermissionError):
					module.company()

	def test_new_contact_is_not_an_implicit_invitation(self):
		with load_service(ROOT + ".portal.accounts", self.dependencies()) as (module, frappe):
			frappe.utils.validate_email_address = lambda value: value
			frappe.db.exists.return_value = False
			doc = MagicMock()
			doc.name, doc.modified = "CONTACT", "now"
			frappe.new_doc = MagicMock(return_value=doc)
			with patch.object(module, "company", return_value="OWN"):
				module.save_record("Contact", {"first_name": "Member", "email_id": "future@example.com"})
			self.assertEqual(doc.ill_portal_contact_only, 1)
			doc.append.assert_called_once_with("links", {"link_doctype": "Customer", "link_name": "OWN"})
