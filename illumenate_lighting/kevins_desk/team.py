"""The team Kevin unblocks and delegates to. Users are found by the part before "@", as in
command_center_sync.ROLES, so no address is hard-coded."""

import frappe

# key (user prefix) -> (first name, what they own: used for "delegate" suggestions)
TEAM = {
	"jay": ("Jay", "sales calls, standard quotes, dealer relationships"),
	"charlotte": ("Charlotte", "invoicing, payments, AP/AR, QBO"),
	"ryanb": ("Ryan", "production, warehouse, shipping, purchasing, vendors"),
	"reigine": ("Regina", "branding, sales docs, eblasts, spec sheet layout"),
}


def resolve():
	"""{email: {"key", "name", "owns"}} for the team members who have an enabled user."""
	out = {}
	for key, (name, owns) in TEAM.items():
		email = frappe.db.get_value("User", {"name": ["like", key + "@%"], "enabled": 1}, "name")
		if email:
			out[email.lower()] = {"key": key, "name": name, "owns": owns}
	return out
