"""Least-privilege system users that background integrations run as.

A worker switches to one of these users so the capability checks inside the code it
calls still apply. Nothing here bypasses a permission check. A site can point a key
at an existing user through the ``ill_service_users`` site config, for example
``{"publication": "n8n@example.com"}``.
"""

from contextlib import contextmanager

import frappe
from frappe import _

CONFIG_KEY = "ill_service_users"

SERVICE_USERS = {
	"publication": {
		"email": "publication-worker@illumenate.lighting",
		"first_name": "Publication Worker",
		"roles": ("ilL Integration",),
	},
	# Automatic pushes to Webflow (plan 4.19 Q2): requests the same STAGE sync as the Sync to
	# Webflow button, which needs the catalog capability. The integration role is not enough.
	"webflow_auto_push": {
		"email": "webflow-auto-push@illumenate.lighting",
		"first_name": "Webflow Auto Push",
		"roles": ("ilL Catalog Publisher",),
	},
	# Signed QuickBooks webhooks write Payment Entries and QuickBooks ids (hardening plan 1.2).
	"qbo": {
		"email": "qbo-integration@illumenate.lighting",
		"first_name": "QuickBooks Integration",
		"roles": ("ilL Integration", "Accounts User"),
	},
}


def service_user(key):
	spec = SERVICE_USERS[key]
	override = (frappe.conf.get(CONFIG_KEY) or {}).get(key)
	return override or spec["email"]


def ensure_service_user(key):
	"""Create the default user and add missing roles. Never removes roles or changes other fields."""
	spec = SERVICE_USERS[key]
	email = spec["email"]
	for role in spec["roles"]:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": spec["first_name"],
				"user_type": "System User",
				"enabled": 1,
				"send_welcome_email": 0,
			}
		)
		user.flags.no_welcome_mail = True
		user.insert(ignore_permissions=True)
	present = {row.role for row in (user.get("roles") or [])}
	missing = [role for role in spec["roles"] if role not in present]
	if missing:
		user.add_roles(*missing)
	return email


@contextmanager
def run_as(key):
	"""Run a block as the service user and always restore the caller."""
	user = service_user(key)
	if not frappe.db.get_value("User", user, "enabled"):
		frappe.throw(
			_("Integration user {0} is missing or disabled. Run bench migrate or fix site config.").format(user),
			frappe.PermissionError,
		)
	actor = frappe.session.user
	frappe.set_user(user)
	try:
		yield user
	finally:
		frappe.set_user(actor)
