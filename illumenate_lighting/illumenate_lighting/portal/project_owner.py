# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Who may set a project's owner company, and which companies qualify (REL-5).

A project's ``owner_customer`` decides which dealer team sees it in the portal.
Dealers get their own company automatically; sales staff creating a project on
a dealer's behalf must name the dealer company, and only a Customer with at
least one enabled Dealer contact qualifies.
"""

import frappe
from frappe import _


def can_set_owner_company(user=None):
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	user = user or frappe.session.user
	return user == "Administrator" or allowed("sales", user)


def has_dealer_contact(customer):
	return bool(
		frappe.db.sql(
			"""
			SELECT 1
			FROM `tabDynamic Link` link
			JOIN `tabContact` contact ON contact.name = link.parent AND link.parenttype = 'Contact'
			JOIN `tabUser` user ON user.name = contact.user AND user.enabled = 1
			JOIN `tabHas Role` role ON role.parent = user.name AND role.parenttype = 'User' AND role.role = 'Dealer'
			WHERE link.link_doctype = 'Customer' AND link.link_name = %(customer)s
			LIMIT 1
			""",
			{"customer": customer},
		)
	)


def validate_owner_company(customer):
	"""Return ``customer`` when it is a dealer company, else raise a user-facing error."""
	customer = str(customer or "").strip()
	if not customer:
		frappe.throw(_("Choose the dealer company that owns this project."))
	if not frappe.db.exists("Customer", customer):
		frappe.throw(_("Owner company {0} does not exist.").format(customer))
	if not has_dealer_contact(customer):
		frappe.throw(
			_("{0} has no dealer contact yet, so no one could see this project in the portal.").format(
				customer
			)
		)
	return customer


def dealer_companies():
	"""Customers that qualify as a project's owner company, as select options.

	The same test as :func:`has_dealer_contact`, for every Customer in one query.
	"""
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT customer.name, customer.customer_name
		FROM `tabCustomer` customer
		JOIN `tabDynamic Link` link ON link.link_doctype = 'Customer' AND link.link_name = customer.name
			AND link.parenttype = 'Contact'
		JOIN `tabContact` contact ON contact.name = link.parent
		JOIN `tabUser` user ON user.name = contact.user AND user.enabled = 1
		JOIN `tabHas Role` role ON role.parent = user.name AND role.parenttype = 'User' AND role.role = 'Dealer'
		ORDER BY customer.customer_name, customer.name
		""",
		as_dict=True,
	)
	return [{"value": row.name, "label": row.customer_name or row.name} for row in rows]
