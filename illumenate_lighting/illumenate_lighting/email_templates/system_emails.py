# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Account and sign-in email settings: welcome and reset templates, link lifetime, 2FA scope.

Run once by ``patches/apply_email_branding.py``. Each step can be re-run from the bench
console; templates are only overwritten when ``overwrite=True`` (staff edit the wording).

	bench --site <site> execute illumenate_lighting.illumenate_lighting.email_templates.system_emails.apply
"""

import pathlib

import frappe

EMAIL_TEMPLATE = "Email Template"
SYSTEM_SETTINGS = "System Settings"
ROLE = "Role"

# 72 hours: dealers often open the welcome email a day later. Frappe uses one setting for
# both the welcome (set your password) and the password reset link.
LINK_LIFETIME_SECONDS = 72 * 3600

APP_NAME = "ilLumenate Lighting"

BODIES = pathlib.Path(__file__).resolve().parents[2] / "templates" / "emails"

# (Email Template name, subject, body file, System Settings field)
SYSTEM_TEMPLATES = (
	(
		"ilL - Welcome",
		"{% if ill_is_staff(user) %}Your ilLumenate Lighting account is ready"
		"{% else %}Your ilLumenate dealer portal account is ready{% endif %}",
		"ill_welcome_body.html",
		"welcome_email_template",
	),
	(
		"ilL - Password reset",
		"Reset your ilLumenate password",
		"ill_password_reset_body.html",
		"reset_password_template",
	),
)

# Roles that never get two-factor: everyone (All), visitors (Guest).
NOT_STAFF_ROLES = ("All", "Guest")


def body(filename):
	"""The shipped body text, without its leading {# ... #} comment."""
	text = (BODIES / filename).read_text(encoding="utf-8")
	if text.startswith("{#"):
		text = text[text.index("#}") + 2 :].lstrip("\n")
	return text


def ensure_templates(overwrite=False):
	"""Create the welcome and reset Email Templates; returns the names created or rewritten."""
	changed = []
	for name, subject, filename, _field in SYSTEM_TEMPLATES:
		exists = frappe.db.exists(EMAIL_TEMPLATE, name)
		if exists and not overwrite:
			continue
		doc = frappe.get_doc(EMAIL_TEMPLATE, name) if exists else frappe.new_doc(EMAIL_TEMPLATE)
		if not exists:
			doc.name = name
		doc.update({"subject": subject, "use_html": 1, "response_html": body(filename)})
		doc.save(ignore_permissions=True) if exists else doc.insert(ignore_permissions=True)
		changed.append(name)
	return changed


def apply_settings():
	"""Point System Settings at the templates, set the link lifetime and the app name."""
	values = {field: name for name, _s, _f, field in SYSTEM_TEMPLATES}
	values["reset_password_link_expiry_duration"] = LINK_LIFETIME_SECONDS
	values["app_name"] = APP_NAME
	for field, value in values.items():
		frappe.db.set_single_value(SYSTEM_SETTINGS, field, value)
	return values


def staff_only_two_factor():
	"""Require two-factor for staff (any role with Desk access), not for portal users.

	Frappe asks for a code when any of a user's roles has Two Factor Auth ticked. "All" is on
	every user, dealers included, so it is cleared; every Desk role is ticked instead. Only
	System Users can hold a Desk role, so portal users sign in with their password alone.
	Returns the roles that changed.
	"""
	changed = []
	if frappe.db.get_value(ROLE, "All", "two_factor_auth"):
		frappe.db.set_value(ROLE, "All", "two_factor_auth", 0)
		changed.append("All")
	staff_roles = frappe.get_all(
		ROLE,
		filters={"desk_access": 1, "two_factor_auth": 0, "name": ["not in", NOT_STAFF_ROLES]},
		pluck="name",
	)
	for role in staff_roles:
		frappe.db.set_value(ROLE, role, "two_factor_auth", 1)
	return changed + staff_roles


def apply(overwrite_templates=False):
	result = {
		"templates": ensure_templates(overwrite=overwrite_templates),
		"settings": apply_settings(),
		"two_factor_roles": staff_only_two_factor(),
	}
	frappe.clear_cache()
	return result
