"""Collaborator changes are granular, company-bound and never delete history (SEC-5)."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

OWNER_COMPANY = "Acme Lighting"
MEMBERS = {"teammate@acme.test": OWNER_COMPANY, "outsider@other.test": "Other Co"}


def actor(user=None):
	customer = MEMBERS.get(user)
	return types.SimpleNamespace(is_company_member_of=lambda owner: bool(customer and customer == owner))


def accounts_double():
	return types.SimpleNamespace(invite=MagicMock(return_value={"success": True, "invitation": "INV-1"}))


class Harness:
	def __init__(self, rows=(), manage=True):
		self.rows = [Record(row) for row in rows]
		self.manage = manage

	def __enter__(self):
		self.accounts = accounts_double()
		deps = {
			ROOT + ".portal.access": types.SimpleNamespace(
				can_manage_project_collaborators=lambda project, user: self.manage, get_actor=actor
			),
			ROOT + ".portal.accounts": self.accounts,
		}
		self._context = load_service(ROOT + ".portal.collaborators", deps)
		module, frappe = self._context.__enter__()
		frappe.DoesNotExistError = LookupError
		frappe.db.exists.return_value = True
		users = {
			"teammate@acme.test": Record(enabled=1, user_type="Website User"),
			"outsider@other.test": Record(enabled=1, user_type="Website User"),
			"staff@illumenate.test": Record(enabled=1, user_type="System User"),
		}
		frappe.db.get_value.side_effect = lambda doctype, name, fields=None, as_dict=False: users.get(name)
		project = Record(
			name="P-1",
			owner="owner@acme.test",
			owner_customer=OWNER_COMPANY,
			modified="2026-10-14 01:00:00",
			collaborators=self.rows,
			save=MagicMock(),
			add_comment=MagicMock(),
		)
		project.append = lambda field, row: project.collaborators.append(Record(row))
		frappe.get_doc.return_value = project
		self.module, self.frappe, self.project = module, frappe, project
		return self

	def __exit__(self, *exc):
		return self._context.__exit__(*exc)


class DirectAccess(unittest.TestCase):
	def test_crafted_arbitrary_email_is_a_permission_error(self):
		for user in ("anyone@random.test", "outsider@other.test", "staff@illumenate.test"):
			with self.subTest(user=user), Harness() as h:
				with self.assertRaises(PermissionError):
					h.module.set_access_level("P-1", user, "EDIT")
				self.assertEqual(h.project.collaborators, [])
				h.project.save.assert_not_called()

	def test_same_company_website_user_is_added_in_place(self):
		with Harness([{"user": "existing@acme.test", "access_level": "VIEW", "is_active": 1}]) as h:
			result = h.module.set_access_level("P-1", "teammate@acme.test", "EDIT", "2026-10-14 01:00:00")
			self.assertEqual(
				result["collaborator"], {"user": "teammate@acme.test", "access_level": "EDIT", "is_active": 1}
			)
			self.assertEqual(
				[r.user for r in h.project.collaborators], ["existing@acme.test", "teammate@acme.test"]
			)
			h.project.save.assert_called_once_with(ignore_permissions=True)

	def test_active_collaborator_level_changes_without_company_check(self):
		with Harness([{"user": "architect@studio.test", "access_level": "VIEW", "is_active": 1}]) as h:
			h.module.set_access_level("P-1", "architect@studio.test", "EDIT")
			self.assertEqual(h.project.collaborators[0].access_level, "EDIT")

	def test_inactive_outsider_cannot_be_reactivated_directly(self):
		with Harness([{"user": "architect@studio.test", "access_level": "VIEW", "is_active": 0}]) as h:
			with self.assertRaises(PermissionError):
				h.module.set_access_level("P-1", "architect@studio.test", "VIEW")
			self.assertEqual(h.project.collaborators[0].is_active, 0)

	def test_non_managers_are_refused(self):
		with Harness(manage=False) as h:
			with self.assertRaises(PermissionError):
				h.module.set_access_level("P-1", "teammate@acme.test", "VIEW")

	def test_stale_page_is_refused(self):
		with Harness() as h:
			with self.assertRaises(ValueError) as caught:
				h.module.set_access_level("P-1", "teammate@acme.test", "VIEW", "2026-10-13 23:00:00")
			self.assertIn("changed since you opened it", str(caught.exception))


class Removal(unittest.TestCase):
	def test_removing_keeps_an_inactive_row(self):
		rows = [
			{
				"user": "architect@studio.test",
				"access_level": "EDIT",
				"is_active": 1,
				"added_on": "2026-09-01",
			},
			{"user": "teammate@acme.test", "access_level": "VIEW", "is_active": 1},
		]
		with Harness(rows) as h:
			result = h.module.deactivate("P-1", "architect@studio.test")
			self.assertEqual(len(h.project.collaborators), 2)
			removed = h.project.collaborators[0]
			self.assertEqual(
				(removed.is_active, removed.access_level, removed.added_on), (0, "EDIT", "2026-09-01")
			)
			self.assertEqual(result["collaborator"]["is_active"], 0)
			self.assertIn("architect@studio.test", h.project.add_comment.call_args.args[1])

	def test_concurrent_edits_touch_only_their_own_row(self):
		rows = [
			{"user": "architect@studio.test", "access_level": "VIEW", "is_active": 1},
			{"user": "designer@studio.test", "access_level": "VIEW", "is_active": 1},
		]
		with Harness(rows) as h:
			h.module.set_access_level("P-1", "architect@studio.test", "EDIT")
			h.module.deactivate("P-1", "designer@studio.test")
			h.module.set_access_level("P-1", "teammate@acme.test", "VIEW")
			self.assertEqual(
				[(r.user, r.access_level, r.is_active) for r in h.project.collaborators],
				[
					("architect@studio.test", "EDIT", 1),
					("designer@studio.test", "VIEW", 0),
					("teammate@acme.test", "VIEW", 1),
				],
			)


class Invitation(unittest.TestCase):
	def test_outsiders_go_through_the_invitation(self):
		with Harness() as h:
			h.module.invite("P-1", " architect@studio.test ", "Ada", access_level="EDIT")
			h.accounts.invite.assert_called_once_with("architect@studio.test", "Ada", "", "P-1", "EDIT")


class DeprecatedListSave(unittest.TestCase):
	def run_wrapper(self, rows, submitted):
		deps = {
			ROOT + ".portal.access": types.SimpleNamespace(
				can_manage_project_collaborators=lambda *a: True, get_actor=actor
			),
		}
		with load_service(ROOT + ".api.portal", deps) as (api, frappe):
			project = Record(
				name="P-1",
				owner="owner@acme.test",
				owner_customer=OWNER_COMPANY,
				collaborators=[Record(row) for row in rows],
				save=MagicMock(),
				add_comment=MagicMock(),
			)
			project.append = lambda field, row: project.collaborators.append(Record(row))
			frappe.db.exists.return_value = True
			frappe.db.get_value.side_effect = lambda doctype, name, fields=None, as_dict=False: (
				Record(enabled=1, user_type="Website User") if name in MEMBERS else None
			)
			frappe.get_doc.return_value = project
			return api.update_project_collaborators("P-1", submitted), project

	def test_arbitrary_user_in_the_list_is_rejected(self):
		result, project = self.run_wrapper(
			[], [{"user": "anyone@random.test", "access_level": "EDIT", "is_active": 1}]
		)
		self.assertFalse(result["success"])
		self.assertEqual(result["error_code"], "permission_denied")
		project.save.assert_not_called()

	def test_users_missing_from_the_list_are_deactivated_not_deleted(self):
		rows = [{"user": "architect@studio.test", "access_level": "EDIT", "is_active": 1}]
		result, project = self.run_wrapper(
			rows, [{"user": "teammate@acme.test", "access_level": "VIEW", "is_active": 1}]
		)
		self.assertTrue(result["success"])
		self.assertEqual(
			[(r.user, r.is_active) for r in project.collaborators],
			[("architect@studio.test", 0), ("teammate@acme.test", 1)],
		)


if __name__ == "__main__":
	unittest.main()
