# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Which Customers a user may pick as a project's end client or stakeholder (REL-9).

Sales staff (and System Managers) may pick any Customer. Everyone else gets
their own company, Customers created by users of their company, and Customers
already used on projects they can read. A contact shared between two dealers
no longer pulls the other dealer's Customers into the list.
"""

import frappe

STAKEHOLDER_FIELDS = ("customer", "architect", "lighting_designer", "general_contractor")


def _options(names):
	if not names:
		return []
	rows = frappe.get_all(
		"Customer", filters={"name": ["in", sorted(names)]}, fields=["name", "customer_name"]
	)
	options = [{"value": row.name, "label": row.customer_name or row.name} for row in rows]
	return sorted(options, key=lambda option: (option["label"].lower(), option["value"]))


def _company_users(customer):
	return frappe.db.sql_list(
		"""
		SELECT DISTINCT contact.user
		FROM `tabContact` contact
		JOIN `tabDynamic Link` link ON link.parent = contact.name AND link.parenttype = 'Contact'
		WHERE link.link_doctype = 'Customer' AND link.link_name = %(customer)s
			AND IFNULL(contact.user, '') != ''
		""",
		{"customer": customer},
	)


def _used_on_readable_projects(user):
	names = set()
	for row in frappe.get_list(
		"ilL-Project", fields=list(STAKEHOLDER_FIELDS), user=user, limit_page_length=0
	):
		names.update(row.get(field) for field in STAKEHOLDER_FIELDS if row.get(field))
	return names


def allowed_customers(user=None):
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import _get_user_customer
	from illumenate_lighting.illumenate_lighting.portal.project_owner import can_set_owner_company

	user = user or frappe.session.user
	if can_set_owner_company(user):
		rows = frappe.get_all("Customer", fields=["name", "customer_name"], order_by="customer_name asc")
		return {
			"success": True,
			"user_customer": None,
			"allowed_customers": [
				{"value": row.name, "label": row.customer_name or row.name} for row in rows
			],
		}
	user_customer = _get_user_customer(user)
	if not user_customer:
		return {"success": True, "user_customer": None, "allowed_customers": []}
	names = {user_customer}
	company_users = _company_users(user_customer)
	if company_users:
		names.update(frappe.get_all("Customer", filters={"owner": ["in", company_users]}, pluck="name"))
	names.update(_used_on_readable_projects(user))
	return {"success": True, "user_customer": user_customer, "allowed_customers": _options(names)}
