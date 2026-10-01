"""Read-only staff and dealer access audit (recovery plan §7.1-7.3)."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

ROLES = {
	"sm@example.com": {"System Manager"},
	"sales@example.com": {"Sales Manager", "ilL Sales Review"},
	"stock@example.com": {"Stock User"},
	"dealer-ok@example.com": {"Dealer"},
	"dealer-none@example.com": {"Dealer"},
	"dealer-two@example.com": {"Dealer", "Sales User"},
}


def _get_all(users):
	def get_all(doctype, filters=None, fields=None, pluck=None, **kwargs):
		if doctype == "User":
			wanted = (
				filters["name"][1]
				if isinstance(filters.get("name"), list) and filters["name"][0] == "in"
				else None
			)
			return [Record(row) for row in users if wanted is None or row["name"] in wanted]
		if doctype == "Has Role" and pluck:
			return [user for user, roles in ROLES.items() if filters["role"] in roles]
		if doctype == "Has Role":
			return [
				Record(parent=user, role=role)
				for user in filters["parent"][1]
				for role in sorted(ROLES.get(user, ()))
			]
		if doctype == "Role":
			return ["System Manager", "Sales User", "Sales Manager", "Stock User", "ilL Sales Review"]
		raise AssertionError(doctype)

	return MagicMock(side_effect=get_all)


def _staff_module():
	staff = types.ModuleType(ROOT + ".portal.staff")
	staff.CAPABILITIES = {
		"sales": {"ilL Sales Review", "ilL Order Approver"},
		"catalog": {"ilL Catalog Publisher"},
	}
	return staff


class StaffReport(unittest.TestCase):
	def test_capabilities_follow_staff_allowed_and_uncovered_ones_are_named(self):
		users = [
			{"name": name, "full_name": name.split("@")[0]}
			for name in ("sm@example.com", "sales@example.com", "stock@example.com")
		]
		with load_service(ROOT + ".portal.role_audit", {ROOT + ".portal.staff": _staff_module()}) as (
			module,
			frappe,
		):
			frappe.only_for = MagicMock()
			frappe.get_all = _get_all(users)
			result = module.report()
		frappe.only_for.assert_called_once_with("System Manager")
		rows = {row["user"]: row for row in result["users"]}
		self.assertEqual(rows["sm@example.com"]["has"], ["sales", "catalog"])
		self.assertEqual(rows["sales@example.com"]["has"], ["sales"])
		self.assertEqual(rows["sales@example.com"]["lacks"], ["catalog"])
		self.assertEqual(rows["sales@example.com"]["erp_roles"], ["Sales Manager"])
		self.assertEqual(rows["stock@example.com"]["lacks"], ["sales", "catalog"])
		# A System Manager covers the work, but nobody holds a catalog role.
		self.assertEqual(result["capability_holders"]["sales"], ["sales@example.com"])
		self.assertEqual(result["uncovered"], ["catalog"])


class DealerAudit(unittest.TestCase):
	def test_lists_unresolved_dealers_and_desk_access_at_risk(self):
		users = [
			{"name": "dealer-ok@example.com", "full_name": "OK", "user_type": "System User"},
			{"name": "dealer-none@example.com", "full_name": "None", "user_type": "Website User"},
			{"name": "dealer-two@example.com", "full_name": "Two", "user_type": "System User"},
		]
		candidates = {
			"dealer-ok@example.com": {"Dealer Co"},
			"dealer-none@example.com": set(),
			"dealer-two@example.com": {"B Co", "A Co"},
		}
		project = types.ModuleType(ROOT + ".doctype.ill_project.ill_project")
		project._user_customer_candidates = candidates.get
		extras = {ROOT + ".portal.staff": _staff_module(), ROOT + ".doctype.ill_project.ill_project": project}
		with load_service(ROOT + ".portal.role_audit", extras) as (module, frappe):
			frappe.only_for = MagicMock()
			frappe.get_all = _get_all(users)
			result = module.dealers()
		self.assertEqual(
			result["unresolved"],
			[
				{
					"user": "dealer-none@example.com",
					"full_name": "None",
					"customers": [],
					"problem": "no linked Customer",
				},
				{
					"user": "dealer-two@example.com",
					"full_name": "Two",
					"customers": ["A Co", "B Co"],
					"problem": "several linked Customers",
				},
			],
		)
		# dealer-two keeps Desk through Sales User; dealer-ok has only Dealer.
		self.assertEqual(
			result["desk_access_at_risk"], [{"user": "dealer-ok@example.com", "full_name": "OK"}]
		)

	def test_no_dealers(self):
		project = types.ModuleType(ROOT + ".doctype.ill_project.ill_project")
		project._user_customer_candidates = MagicMock()
		extras = {ROOT + ".portal.staff": _staff_module(), ROOT + ".doctype.ill_project.ill_project": project}
		with load_service(ROOT + ".portal.role_audit", extras) as (module, frappe):
			frappe.only_for = MagicMock()
			frappe.get_all = MagicMock(return_value=[])
			self.assertEqual(module.dealers(), {"unresolved": [], "desk_access_at_risk": []})


if __name__ == "__main__":
	unittest.main()
