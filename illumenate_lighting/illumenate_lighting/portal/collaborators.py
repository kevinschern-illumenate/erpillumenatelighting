# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Granular project collaborator changes (SEC-5).

Each call changes one row in place, so two managers editing at once cannot
erase each other's work. Only people already collaborating, or enabled Website
Users of the project's own company, can be given access directly; everyone
else goes through an emailed invitation they accept themselves. Removing
someone deactivates the row and keeps its history.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.access import (
	can_manage_project_collaborators,
	get_actor,
)

PROJECT = "ilL-Project"
ACCESS_LEVELS = ("VIEW", "EDIT")
STALE_MESSAGE = "This project changed since you opened it. Reload to see the latest collaborators."
OUTSIDER_MESSAGE = "Only people at this project's company can be added directly. Invite others by email."


def load(project_name, expected_modified=None, user=None):
	"""Lock the project for one collaborator change and confirm the caller manages it."""
	if not project_name or not frappe.db.exists(PROJECT, project_name):
		frappe.throw(_("Project not found"), frappe.DoesNotExistError)
	frappe.db.sql("select name from `tabilL-Project` where name=%s for update", project_name)
	project = frappe.get_doc(PROJECT, project_name)
	if not can_manage_project_collaborators(project, user or frappe.session.user):
		frappe.throw(
			_("You don't have permission to manage collaborators on this project"), frappe.PermissionError
		)
	if expected_modified and str(expected_modified) != str(project.modified):
		frappe.throw(_(STALE_MESSAGE))
	return project


def row_for(project, user):
	return next((row for row in project.get("collaborators") or [] if row.user == user), None)


def require_eligible(project, user):
	"""Active collaborators keep their row; anyone new must be a same-company Website User."""
	row = row_for(project, user)
	if row and row.is_active:
		return row
	if user == project.owner:
		frappe.throw(_("The project owner always has full access"))
	account = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True) if user else None
	if (
		not account
		or not account.enabled
		or account.user_type != "Website User"
		or not project.owner_customer
		or not get_actor(user).is_company_member_of(project.owner_customer)
	):
		frappe.throw(_(OUTSIDER_MESSAGE), frappe.PermissionError)
	return row


def _check_level(level):
	if level not in ACCESS_LEVELS:
		frappe.throw(_("Invalid access_level. Must be one of: {0}").format(", ".join(ACCESS_LEVELS)))


def apply_level(project, user, level):
	"""Add, reactivate or re-level one collaborator; returns True when anything changed."""
	_check_level(level)
	row = require_eligible(project, user)
	if row is None:
		project.append("collaborators", {"user": user, "access_level": level, "is_active": 1})
		return True
	if row.is_active and row.access_level == level:
		return False
	row.access_level, row.is_active = level, 1
	return True


def apply_deactivate(project, user):
	row = row_for(project, user)
	if not row or not row.is_active:
		return False
	row.is_active = 0
	return True


def _result(project, user):
	row = row_for(project, user)
	return {
		"success": True,
		"modified": str(project.modified),
		"collaborator": {
			"user": user,
			"access_level": row.access_level if row else None,
			"is_active": int(row.is_active or 0) if row else 0,
		},
	}


@frappe.whitelist(methods=["POST"])
def set_access_level(project, user, level, expected_modified=None):
	"""Give one same-company person VIEW or EDIT access, or change an existing collaborator's level."""
	doc = load(project, expected_modified)
	user = str(user or "").strip()
	if apply_level(doc, user, level):
		doc.save(ignore_permissions=True)
		doc.add_comment("Info", _("Collaborator {0} set to {1}").format(user, level))
	return _result(doc, user)


@frappe.whitelist(methods=["POST"])
def deactivate(project, user, expected_modified=None):
	"""Remove one collaborator's access; the inactive row keeps when and how they were added."""
	doc = load(project, expected_modified)
	if not row_for(doc, user):
		frappe.throw(_("Collaborator not found on this project"))
	if apply_deactivate(doc, user):
		doc.save(ignore_permissions=True)
		doc.add_comment("Info", _("Collaborator {0} removed").format(user))
	return _result(doc, user)


@frappe.whitelist(methods=["POST"])
def invite(project, email, first_name=None, last_name="", access_level="VIEW"):
	"""Invite anyone by email; access starts only when they accept as that email."""
	from illumenate_lighting.illumenate_lighting.portal import accounts

	_check_level(access_level)
	email = str(email or "").strip()
	return accounts.invite(email, first_name or email.split("@")[0], last_name or "", project, access_level)
