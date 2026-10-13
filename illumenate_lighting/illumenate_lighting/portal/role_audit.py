"""Read-only staff and dealer access audit (deployment recovery plan §7.1-7.3).

Invoke with bench execute; these functions are deliberately not HTTP endpoints:

    bench --site <site> execute illumenate_lighting.illumenate_lighting.portal.role_audit.report
    bench --site <site> execute illumenate_lighting.illumenate_lighting.portal.role_audit.dealers
    bench --site <site> execute illumenate_lighting.illumenate_lighting.portal.role_audit.hr

No roles are assigned automatically. Use the output with the role checklist in
docs/B2B_STAFF_OPERATIONS.md, and ``hr`` with docs/HR_SETUP.md.
"""

import frappe

from illumenate_lighting.illumenate_lighting.portal.staff import CAPABILITIES

# Standard roles staff used before the B2B portal. Shown so each person can be
# mapped to the ilL job roles that now gate their work.
ERP_ROLES = (
	"Sales User",
	"Sales Manager",
	"Stock User",
	"Stock Manager",
	"Manufacturing User",
	"Manufacturing Manager",
	"Accounts User",
	"Accounts Manager",
	"Item Manager",
	"Website Manager",
	"HR User",
	"HR Manager",
)
# HRMS roles that open other people's HR records. Only the HR lead should hold them.
HR_ROLES = ("HR User", "HR Manager")
STAFF_ROLES = frozenset().union(*CAPABILITIES.values())


def _roles_by_user(users):
	roles = {user: set() for user in users}
	if users:
		for row in frappe.get_all(
			"Has Role",
			filters={"parenttype": "User", "parent": ["in", list(users)]},
			fields=["parent", "role"],
		):
			roles[row.parent].add(row.role)
	return roles


def report():
	"""Enabled System Users, the staff capabilities each has or lacks, and uncovered capabilities.

	Capabilities follow ``portal.staff.allowed``: an ilL job role, or System Manager.
	"""
	frappe.only_for("System Manager")
	users = frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User", "name": ["not in", ["Administrator", "Guest"]]},
		fields=["name", "full_name"],
		order_by="name asc",
	)
	roles = _roles_by_user([user.name for user in users])
	rows = []
	holders = {capability: [] for capability in CAPABILITIES}
	for user in users:
		held = roles[user.name]
		system_manager = "System Manager" in held
		has = []
		for capability, granting in CAPABILITIES.items():
			if system_manager or held & granting:
				has.append(capability)
				if held & granting:
					holders[capability].append(user.name)
		rows.append(
			{
				"user": user.name,
				"full_name": user.full_name,
				"system_manager": system_manager,
				"ill_roles": sorted(held & STAFF_ROLES),
				"erp_roles": [role for role in ERP_ROLES if role in held],
				"has": has,
				"lacks": [capability for capability in CAPABILITIES if capability not in has],
			}
		)
	return {
		"users": rows,
		"capability_holders": holders,
		# Only System Managers can do this work until someone holds a granting ilL role.
		"uncovered": [capability for capability, names in holders.items() if not names],
	}


def dealers():
	"""Dealer users the portal cannot place in one company, and Dealer users at risk of losing Desk.

	``unresolved``: 0 or several Customers at the deciding Contact tier, so the portal
	shows them no company projects, schedules or orders until staff fix Contact links.
	``desk_access_at_risk``: System Users whose only Desk-granting role was Dealer; they
	become Website Users the next time their User record is saved.
	"""
	frappe.only_for("System Manager")
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_user_customer_candidates,
	)

	names = frappe.get_all(
		"Has Role", filters={"parenttype": "User", "role": "Dealer"}, pluck="parent", distinct=True
	)
	if not names:
		return {"unresolved": [], "desk_access_at_risk": []}
	users = frappe.get_all(
		"User",
		filters={"name": ["in", names], "enabled": 1},
		fields=["name", "full_name", "user_type"],
		order_by="name asc",
	)
	roles = _roles_by_user([user.name for user in users])
	desk_roles = set(frappe.get_all("Role", filters={"desk_access": 1}, pluck="name")) - {"Dealer"}
	unresolved = []
	desk_at_risk = []
	for user in users:
		customers = sorted(_user_customer_candidates(user.name))
		if len(customers) != 1:
			unresolved.append(
				{
					"user": user.name,
					"full_name": user.full_name,
					"customers": customers,
					"problem": "no linked Customer" if not customers else "several linked Customers",
				}
			)
		if user.user_type == "System User" and not roles[user.name] & desk_roles:
			desk_at_risk.append({"user": user.name, "full_name": user.full_name})
	return {"unresolved": unresolved, "desk_access_at_risk": desk_at_risk}


def hr():
	"""Frappe HR setup gaps and who can read other people's HR records.

	``users_without_employee``: staff who cannot request leave or claim expenses yet.
	``employees_without_user`` and ``employees_without_user_permission``: records that
	are not tied to exactly one person's login, so self-service or privacy is broken.
	``hr_role_holders``: everyone who can open any Employee, leave or expense record;
	expect only the HR lead (System Managers can too, and are listed apart).
	"""
	frappe.only_for("System Manager")
	if "hrms" not in frappe.get_installed_apps():
		return {"hrms_installed": False}

	users = frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User", "name": ["not in", ["Administrator", "Guest"]]},
		fields=["name", "full_name"],
		order_by="name asc",
	)
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=[
			"name",
			"employee_name",
			"user_id",
			"create_user_permission",
			"company",
			"department",
			"leave_approver",
			"expense_approver",
		],
		order_by="name asc",
	)
	linked = {row.user_id for row in employees if row.user_id}
	roles = _roles_by_user([user.name for user in users])

	today = frappe.utils.nowdate()
	with_policy = set(
		frappe.get_all(
			"Leave Policy Assignment",
			filters={"docstatus": 1, "effective_from": ["<=", today], "effective_to": [">=", today]},
			pluck="employee",
		)
	)
	companies = {row.company for row in employees if row.company}

	return {
		"hrms_installed": True,
		"users_without_employee": [
			{"user": user.name, "full_name": user.full_name} for user in users if user.name not in linked
		],
		"employees_without_user": [
			{"employee": row.name, "employee_name": row.employee_name} for row in employees if not row.user_id
		],
		"employees_without_user_permission": [
			{"employee": row.name, "employee_name": row.employee_name, "user": row.user_id}
			for row in employees
			if row.user_id and not row.create_user_permission
		],
		"employees_without_leave_policy": [
			{"employee": row.name, "employee_name": row.employee_name}
			for row in employees
			if row.name not in with_policy
		],
		# HRMS falls back to the Department's approvers when these are blank.
		"employees_without_approvers": [
			{
				"employee": row.name,
				"employee_name": row.employee_name,
				"department": row.department,
				"missing": [field for field in ("leave_approver", "expense_approver") if not row.get(field)],
			}
			for row in employees
			if not (row.leave_approver and row.expense_approver)
		],
		"companies_without_holiday_list": [
			company
			for company in sorted(companies)
			if not frappe.db.get_value("Company", company, "default_holiday_list")
		],
		"hr_role_holders": [
			{
				"user": user.name,
				"full_name": user.full_name,
				"roles": sorted(roles[user.name] & set(HR_ROLES)),
			}
			for user in users
			if roles[user.name] & set(HR_ROLES)
		],
		"system_managers": [user.name for user in users if "System Manager" in roles[user.name]],
	}
