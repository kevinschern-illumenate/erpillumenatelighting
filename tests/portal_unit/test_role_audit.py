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


HR_USERS = [
	Record(name="lead@example.com", full_name="HR lead"),
	Record(name="ryan@example.com", full_name="Ryan"),
	Record(name="web@example.com", full_name="Web"),
	Record(name="sm@example.com", full_name="Admin"),
]
HR_EMPLOYEES = [
	Record(
		name="EMP-1",
		employee_name="HR lead",
		user_id="lead@example.com",
		create_user_permission=1,
		company="ilL",
		leave_approver="owner@example.com",
		expense_approver="owner@example.com",
	),
	Record(
		name="EMP-2",
		employee_name="Ryan",
		user_id="ryan@example.com",
		create_user_permission=0,
		company="ilL",
		department="Operations",
		leave_approver="lead@example.com",
	),
	Record(name="EMP-3", employee_name="Contractor", user_id=None, create_user_permission=1, company="ilL"),
]
HR_ROLES_HELD = {
	"lead@example.com": {"HR Manager", "Employee"},
	"ryan@example.com": {"Employee", "HR User"},
	"web@example.com": {"Employee"},
	"sm@example.com": {"System Manager"},
}


class HrReport(unittest.TestCase):
	def run_report(self):
		def get_all(doctype, filters=None, fields=None, pluck=None, **kwargs):
			if doctype == "User":
				return HR_USERS
			if doctype == "Employee":
				return HR_EMPLOYEES
			if doctype == "Has Role":
				return [
					Record(parent=user, role=role)
					for user in filters["parent"][1]
					for role in sorted(HR_ROLES_HELD.get(user, ()))
				]
			if doctype == "Leave Policy Assignment":
				return ["EMP-1"]
			raise AssertionError(doctype)

		with load_service(ROOT + ".portal.role_audit", {ROOT + ".portal.staff": _staff_module()}) as (
			module,
			frappe,
		):
			frappe.only_for = MagicMock()
			frappe.get_installed_apps = MagicMock(return_value=["frappe", "erpnext", "hrms"])
			frappe.get_all = MagicMock(side_effect=get_all)
			frappe.db.get_value.return_value = None
			result = module.hr()
			frappe.only_for.assert_called_once_with("System Manager")
			return result

	def test_gaps_and_hr_access_beyond_the_lead_are_listed(self):
		result = self.run_report()
		self.assertEqual(
			[row["user"] for row in result["users_without_employee"]], ["web@example.com", "sm@example.com"]
		)
		self.assertEqual([row["employee"] for row in result["employees_without_user"]], ["EMP-3"])
		self.assertEqual([row["employee"] for row in result["employees_without_user_permission"]], ["EMP-2"])
		self.assertEqual(
			[row["employee"] for row in result["employees_without_leave_policy"]], ["EMP-2", "EMP-3"]
		)
		approvers = {row["employee"]: row["missing"] for row in result["employees_without_approvers"]}
		self.assertEqual(
			approvers, {"EMP-2": ["expense_approver"], "EMP-3": ["leave_approver", "expense_approver"]}
		)
		self.assertEqual(result["companies_without_holiday_list"], ["ilL"])
		holders = {row["user"]: row["roles"] for row in result["hr_role_holders"]}
		self.assertEqual(holders, {"lead@example.com": ["HR Manager"], "ryan@example.com": ["HR User"]})
		self.assertEqual(result["system_managers"], ["sm@example.com"])

	def test_without_hrms_only_says_so(self):
		with load_service(ROOT + ".portal.role_audit", {ROOT + ".portal.staff": _staff_module()}) as (
			module,
			frappe,
		):
			frappe.only_for = MagicMock()
			frappe.get_installed_apps = MagicMock(return_value=["frappe", "erpnext"])
			self.assertEqual(module.hr(), {"hrms_installed": False})
			frappe.get_all.assert_not_called()


if __name__ == "__main__":
	unittest.main()
