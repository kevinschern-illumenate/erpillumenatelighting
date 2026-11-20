"""Kevin's Desk owner seeding: prefer the company-domain user, and the one-time correction patch."""

import types
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock

from test_services import Record, load_service

SEED = "illumenate_lighting.patches.seed_desk_settings"
FIX = "illumenate_lighting.patches.fix_desk_owner_domain"
USERS = [Record(name="kevins@cascadeintegration.com"), Record(name="kevins@illumenate.lighting")]


def email_accounts(doctype, filters, field):
	if doctype == "Email Account" and filters == "Sales":
		return "sales@illumenate.lighting"
	return None


@contextmanager
def seed(users=USERS):
	with load_service(SEED) as (module, frappe):
		frappe.get_all = MagicMock(return_value=list(users))
		frappe.db.get_value.side_effect = email_accounts
		yield module, frappe


@contextmanager
def fix(owner="kevins@cascadeintegration.com", edited_in_desk=False):
	with seed() as (seed_module, _):
		pkg = types.ModuleType("illumenate_lighting.patches.seed_desk_settings")
		pkg.company_domain, pkg.find_owner = seed_module.company_domain, seed_module.find_owner
		with load_service(FIX, {"illumenate_lighting.patches.seed_desk_settings": pkg}) as (module, frappe):
			doc = Record(desk_owner=owner, slug="S" * 32)
			doc.save = MagicMock()
			frappe.get_single = MagicMock(return_value=doc)
			frappe.db.exists.side_effect = lambda dt, filters=None: dt == "DocType" or edited_in_desk
			# the seed helpers run against their own Frappe double; give it the same answers
			seed_module.frappe.get_all = MagicMock(return_value=list(USERS))
			seed_module.frappe.db.get_value.side_effect = email_accounts
			yield module, doc


class OwnerSeed(unittest.TestCase):
	def test_prefers_the_company_domain_over_another_kevins_account(self):
		with seed() as (module, frappe):
			self.assertEqual(module.find_owner(), "kevins@illumenate.lighting")
			self.assertEqual(frappe.get_all.call_args.kwargs["order_by"], "last_active desc")

	def test_falls_back_to_the_most_recently_active(self):
		with seed(users=[Record(name="kevins@other.example"), Record(name="kevins@old.example")]) as (
			module,
			_,
		):
			self.assertEqual(module.find_owner(), "kevins@other.example")
		with seed(users=[]) as (module, _):
			self.assertIsNone(module.find_owner())


class OwnerFix(unittest.TestCase):
	def test_moves_the_desk_to_the_company_user_and_rotates_the_link(self):
		with fix() as (module, doc):
			module.execute()
		self.assertEqual((doc.desk_owner, doc.slug), ("kevins@illumenate.lighting", ""))
		doc.save.assert_called_once_with(ignore_permissions=True)

	def test_leaves_a_correct_or_deliberately_chosen_owner_alone(self):
		for kwargs in ({"owner": "kevins@illumenate.lighting"}, {"edited_in_desk": True}, {"owner": None}):
			with self.subTest(**kwargs), fix(**kwargs) as (module, doc):
				before = (doc.desk_owner, doc.slug)
				module.execute()
				self.assertEqual((doc.desk_owner, doc.slug), before)
				doc.save.assert_not_called()

	def test_runs_after_the_seed_and_before_mailboxes_are_seeded(self):
		from pathlib import Path

		text = (Path(__file__).resolve().parents[2] / "illumenate_lighting/patches.txt").read_text()
		order = [
			text.index(p) for p in ("seed_desk_settings", "fix_desk_owner_domain", "seed_desk_mailboxes")
		]
		self.assertEqual(order, sorted(order))


if __name__ == "__main__":
	unittest.main()
