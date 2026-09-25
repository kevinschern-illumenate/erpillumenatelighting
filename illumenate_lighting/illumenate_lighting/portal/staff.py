"""Named staff capabilities shared by service endpoints and Desk queues."""

import frappe
from frappe import _

CAPABILITIES = {
	"accounts": {"ilL Support", "ilL Sales Review", "ilL Order Approver"},
	"catalog": {"ilL Catalog Publisher"},
	"integration": {"ilL Integration"},
	"sales": {"ilL Sales Review", "ilL Order Approver"},
	"engineering": {"ilL Engineering"},
	"support": {"ilL Support"},
	"operations": {"ilL Operations"},
}


def allowed(capability, user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	if (
		user == "Guest"
		or not frappe.db.get_value("User", user, "enabled")
		or frappe.db.get_value("User", user, "user_type") != "System User"
	):
		return False
	return bool(set(frappe.get_roles(user)) & (CAPABILITIES[capability] | {"System Manager"}))


def require(capability):
	if not allowed(capability):
		frappe.throw(_("This action requires an authorized staff account"), frappe.PermissionError)


def require_catalog_reader():
	if not (allowed("catalog") or allowed("integration")):
		frappe.throw(_("Catalog staff access is required"), frappe.PermissionError)
