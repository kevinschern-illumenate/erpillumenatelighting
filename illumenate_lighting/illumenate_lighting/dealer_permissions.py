# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Dealer role permissions.

The portal authorises a schedule → Sales Order conversion with the app's own
schedule rules, but the conversion itself ends in a plain ``Sales Order.insert()``
which is checked against ERPNext role permissions. System Managers bypass that
check, so a missing Dealer permission only ever surfaced for real dealers.

This module is the single definition of what the Dealer role may do on ERPNext
masters, and it is applied both on install and by a migration patch. It is
deliberately narrower than "whatever makes it work": dealers get *create* on
Sales Order and *read* on the masters a Sales Order refers to, nothing else.
Customer/Contact/Address creation from the portal runs through whitelisted
endpoints with their own role gate, so no write permission is needed here.

Desk visibility is additionally narrowed by
:func:`sales_order_query_conditions` / :func:`sales_order_has_permission`, which
restrict a dealer to Sales Orders for their own linked Customer.
"""

import frappe

DEALER_ROLE = "Dealer"

# Every permission flag we manage, in an order where dependencies come first
# (Frappe requires `read` before `create`, etc.). Flags omitted from a doctype's
# entry below are explicitly set to 0. Flags absent from the site's DocPerm
# schema are skipped -- Frappe drops flags between versions (e.g.
# `set_user_permissions`), and querying a dropped column is a hard SQL error.
_MANAGED_PTYPES = (
	"select",
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"print",
	"email",
	"report",
	"export",
	"import",
	"share",
	"set_user_permissions",
)

# Least-privilege matrix. Anything not listed is revoked.
DEALER_PERMISSION_MATRIX = {
	# Dealers place orders; they never edit, submit or cancel them.
	"Sales Order": {"select": 1, "read": 1, "create": 1, "print": 1},
	# Read-only masters referenced by a Sales Order.
	"Customer": {"select": 1, "read": 1},
	"Contact": {"select": 1, "read": 1},
	"Address": {"select": 1, "read": 1},
	"Item": {"select": 1, "read": 1},
	"Item Group": {"select": 1, "read": 1},
	"UOM": {"select": 1, "read": 1},
	"Currency": {"select": 1, "read": 1},
}


def apply_dealer_permissions() -> list[str]:
	"""Apply :data:`DEALER_PERMISSION_MATRIX` to the Dealer role.

	Idempotent. Returns the list of doctypes that were changed.

	Uses ``frappe.permissions`` rather than writing DocPerm rows directly so the
	change lands on Custom DocPerm when a site has already customised that
	doctype — writing DocPerm on such a site has no effect at all.
	"""
	from frappe.permissions import add_permission, update_permission_property

	if not frappe.db.exists("Role", DEALER_ROLE):
		frappe.logger().warning("Dealer role missing, skipping permission setup")
		return []

	changed = []

	for doctype, granted in DEALER_PERMISSION_MATRIX.items():
		if not frappe.db.exists("DocType", doctype):
			frappe.logger().warning(f"DocType {doctype} not found, skipping Dealer permissions")
			continue

		add_permission(doctype, DEALER_ROLE, 0)

		table = _permission_table(doctype)
		doctype_changed = False
		for ptype in _supported_ptypes(table):
			value = 1 if granted.get(ptype) else 0
			if _current_permission_value(doctype, ptype, table) == value:
				continue
			update_permission_property(doctype, DEALER_ROLE, 0, ptype, value, validate=False)
			doctype_changed = True

		if doctype_changed:
			changed.append(doctype)

	if changed:
		frappe.clear_cache()

	return changed


def _permission_table(doctype: str) -> str:
	"""Return the table the Dealer's permissions for ``doctype`` actually live in."""
	return "Custom DocPerm" if frappe.db.exists("Custom DocPerm", {"parent": doctype}) else "DocPerm"


def _supported_ptypes(table: str) -> tuple[str, ...]:
	"""Return the managed flags that exist as columns on ``table``."""
	columns = set(frappe.db.get_table_columns(table))
	return tuple(ptype for ptype in _MANAGED_PTYPES if ptype in columns)


def _current_permission_value(doctype: str, ptype: str, table: str | None = None):
	"""Return the Dealer's current value for ``ptype`` on ``doctype``, or None."""
	table = table or _permission_table(doctype)
	value = frappe.db.get_value(
		table,
		{"parent": doctype, "role": DEALER_ROLE, "permlevel": 0},
		ptype,
	)
	return None if value is None else int(value)


def _dealer_customer(user: str):
	"""Return the Customer a dealer is linked to, or None when not applicable."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
		_is_dealer_user,
		_is_internal_user,
	)

	if _is_internal_user(user) or not _is_dealer_user(user):
		return None

	return _get_user_customer(user)


def sales_order_query_conditions(user=None) -> str:
	"""Restrict Dealer list views to Sales Orders for their own Customer."""
	user = user or frappe.session.user

	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_is_dealer_user,
		_is_internal_user,
	)

	if _is_internal_user(user) or not _is_dealer_user(user):
		return ""

	customer = _dealer_customer(user)
	if not customer:
		return f"(`tabSales Order`.owner = {frappe.db.escape(user)})"

	return (
		f"(`tabSales Order`.customer = {frappe.db.escape(customer)}"
		f" OR `tabSales Order`.owner = {frappe.db.escape(user)})"
	)


def sales_order_has_permission(doc, ptype="read", user=None) -> bool:
	"""Deny a Dealer access to Sales Orders outside their own Customer."""
	user = user or frappe.session.user

	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_is_dealer_user,
		_is_internal_user,
	)

	if _is_internal_user(user) or not _is_dealer_user(user):
		return True

	if doc.get("owner") == user:
		return True

	customer = _dealer_customer(user)
	return bool(customer) and doc.get("customer") == customer
