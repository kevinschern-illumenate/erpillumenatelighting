# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Row scoping for the ERPNext masters the Dealer role can read.

The Dealer role reads Customer, Contact and Address so a portal Sales Order
can be inserted. REST (``/api/resource``, ``frappe.client.get_list``) honours
role DocPerms for website users too, so without these hooks a dealer could
list every company's customers, contacts and addresses.

System Users (staff on Desk) stay unrestricted. A website user sees:

- Customer: their own company, Customers they created, and Customers named on
  a project they can read (end client, architect, lighting designer,
  general contractor).
- Contact / Address: rows they created, rows linked to one of those
  Customers, their own Contact, and a readable project's project manager.

Each ``has_permission`` answer runs the matching list predicate against the
single row, so the two can never disagree.
"""

import frappe

from illumenate_lighting.illumenate_lighting.portal import access

PROJECT_CUSTOMER_FIELDS = (
	"customer",
	"architect",
	"lighting_designer",
	"general_contractor",
)
DENY = "1=0"


def _unrestricted(user) -> bool:
	if user == "Administrator":
		return True
	return frappe.db.get_value("User", user, "user_type") == "System User"


def _project_predicate(actor) -> str:
	return access._project_visibility_sql(actor, table="p") or "1=1"


def _customer_predicate(actor, column: str) -> str:
	"""SQL predicate: ``column`` names a Customer the website user may read."""
	user = frappe.db.escape(actor.user)
	project_columns = ", ".join(f"p.{field}" for field in PROJECT_CUSTOMER_FIELDS)
	clauses = [
		f"{column} IN (SELECT c.name FROM `tabCustomer` c WHERE c.owner = {user})",
		f"""EXISTS (
			SELECT 1 FROM {access.PROJECT_TABLE} p
			WHERE {column} IN ({project_columns}) AND {_project_predicate(actor)}
		)""",
	]
	if actor.customer:
		clauses.insert(0, f"{column} = {frappe.db.escape(actor.customer)}")
	return "(" + " OR ".join(clauses) + ")"


def _linked_to_readable_customer(actor, parent_doctype: str, table: str) -> str:
	return f"""{table}.name IN (
		SELECT dl.parent FROM `tabDynamic Link` dl
		WHERE dl.parenttype = {frappe.db.escape(parent_doctype)} AND dl.link_doctype = 'Customer'
		AND {_customer_predicate(actor, "dl.link_name")}
	)"""


def _conditions(doctype: str, user=None) -> str | None:
	"""SQL predicate for ``doctype`` rows the user may read; ``None`` when unrestricted."""
	user = user or frappe.session.user
	if user == "Guest":
		return DENY
	if _unrestricted(user):
		return None
	actor = access.get_actor(user)
	if actor.is_guest:
		return DENY
	if doctype == "Customer":
		return _customer_predicate(actor, "`tabCustomer`.name")
	user_sql = frappe.db.escape(actor.user)
	table = f"`tab{doctype}`"
	clauses = [f"{table}.owner = {user_sql}", _linked_to_readable_customer(actor, doctype, table)]
	if doctype == "Contact":
		clauses += [
			f"`tabContact`.user = {user_sql}",
			f"""EXISTS (
				SELECT 1 FROM {access.PROJECT_TABLE} p
				WHERE p.project_manager = `tabContact`.name AND {_project_predicate(actor)}
			)""",
		]
	return "(" + " OR ".join(clauses) + ")"


def _has_row(doctype: str, doc, user=None) -> bool:
	condition = _conditions(doctype, user)
	if condition is None:
		return True
	name = doc.get("name") if hasattr(doc, "get") else doc
	if not name or condition == DENY:
		return False
	table = f"`tab{doctype}`"
	return bool(
		frappe.db.sql(f"SELECT {table}.name FROM {table} WHERE {table}.name = %s AND {condition}", (name,))
	)


def customer_query_conditions(user=None) -> str:
	return _conditions("Customer", user) or ""


def contact_query_conditions(user=None) -> str:
	return _conditions("Contact", user) or ""


def address_query_conditions(user=None) -> str:
	return _conditions("Address", user) or ""


def customer_has_permission(doc, ptype="read", user=None) -> bool:
	return _has_row("Customer", doc, user)


def contact_has_permission(doc, ptype="read", user=None) -> bool:
	return _has_row("Contact", doc, user)


def address_has_permission(doc, ptype="read", user=None) -> bool:
	return _has_row("Address", doc, user)
