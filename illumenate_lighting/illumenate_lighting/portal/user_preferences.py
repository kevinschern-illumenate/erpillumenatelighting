"""Per-user portal preferences kept in ilL-Portal-User-Settings (plan 3.14).

``show_dealer_pricing`` remembers the schedule page's "Show Dealer Pricing" toggle, so the choice
persists across pages and sessions instead of resetting on every load. Only dealers with pricing
access can see or change it.
"""

import frappe
from frappe import _

SETTINGS = "ilL-Portal-User-Settings"
FIELD = "show_dealer_pricing"


def can_toggle_dealer_pricing(user=None):
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	from illumenate_lighting.illumenate_lighting.api.exports import _check_pricing_permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import _is_dealer_user

	return bool(_is_dealer_user(user) and _check_pricing_permission(user))


def show_dealer_pricing(user=None):
	"""The saved choice; on (the field default) when the user has not chosen yet."""
	user = user or frappe.session.user
	value = frappe.db.get_value(SETTINGS, {"user": user}, FIELD)
	return True if value is None else bool(int(value or 0))


@frappe.whitelist(methods=["POST"])
def set_show_dealer_pricing(show):
	"""Save the schedule page's dealer pricing toggle for the current user."""
	from illumenate_lighting.illumenate_lighting.api.configuration_contract import parse_bool

	if not can_toggle_dealer_pricing():
		frappe.throw(_("Dealer pricing is not available for your account"), frappe.PermissionError)
	try:
		value = 1 if parse_bool(show) else 0
	except ValueError:
		frappe.throw(_("Choose whether to show dealer pricing"))
	user = frappe.session.user
	name = frappe.db.get_value(SETTINGS, {"user": user}, "name")
	if name:
		frappe.db.set_value(SETTINGS, name, FIELD, value)
	else:
		settings = frappe.new_doc(SETTINGS)
		settings.user = user
		settings.set(FIELD, value)
		settings.insert(ignore_permissions=True)
	return {"success": True, FIELD: bool(value)}
