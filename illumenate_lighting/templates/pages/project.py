# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.status import schedule_status_label
from illumenate_lighting.illumenate_lighting.portal.web_guard import require_login

no_cache = 1


def get_context(context):
	"""Get context for the project detail portal page."""
	require_login()

	# Get project name from path
	project_name = frappe.form_dict.get("project")

	# Handle new project creation
	if project_name == "new":
		return _get_new_project_context(context)

	if not project_name:
		frappe.throw("Project not specified", frappe.DoesNotExistError)

	# Get project with permission check
	if not frappe.db.exists("ilL-Project", project_name):
		frappe.throw("Project not found", frappe.DoesNotExistError)

	project = frappe.get_doc("ilL-Project", project_name)

	# Check permission
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		has_permission,
	)

	if not has_permission(project, "read", frappe.session.user):
		frappe.throw("You don't have permission to view this project", frappe.PermissionError)

	# Check if user can edit
	can_edit = has_permission(project, "write", frappe.session.user)

	# Get schedules for this project, limited to the ones this user may read
	# (a schedule can opt out of inherited project privacy).
	from illumenate_lighting.illumenate_lighting.portal.access import (
		schedule_query_conditions,
	)

	visibility = schedule_query_conditions(frappe.session.user)
	schedules = frappe.db.sql(
		f"""
		SELECT name, schedule_name, status, modified, version, is_locked, version_parent
		FROM `tabilL-Project-Fixture-Schedule`
		WHERE ill_project = %(project)s
		{"AND " + visibility if visibility else ""}
		ORDER BY version_parent ASC, version DESC
		""",
		{"project": project_name},
		as_dict=True,
	)

	# Line counts for every schedule in one grouped query
	counts = {}
	if schedules:
		counts = dict(
			frappe.db.sql(
				"""
				SELECT parent, COUNT(*) FROM `tabilL-Child-Fixture-Schedule-Line`
				WHERE parenttype = 'ilL-Project-Fixture-Schedule' AND parent IN %(names)s
				GROUP BY parent
				""",
				{"names": tuple(schedule.name for schedule in schedules)},
			)
		)
	for schedule in schedules:
		schedule.lines_count = counts.get(schedule.name, 0)

	# Pre-load contact details for project_manager (still a Contact field)
	contact_details = {}
	if project.get("project_manager"):
		try:
			contact = frappe.get_doc("Contact", project.get("project_manager"))
			contact_details["project_manager"] = {
				"first_name": contact.first_name,
				"last_name": contact.last_name,
				"company_name": contact.company_name,
			}
		except Exception:
			contact_details["project_manager"] = None

	# DESK-9: the end client and team are project parties of the owner company.
	from illumenate_lighting.illumenate_lighting.portal import project_parties

	context.project = project
	context.schedules = schedules
	# FLOW-9: the latest version of each schedule, earlier versions folded under it.
	from illumenate_lighting.illumenate_lighting.portal.project_list import version_families

	context.schedule_families = version_families(schedules)
	# System designs of these schedules (WP-4.5); None hides the Designs tab.
	from illumenate_lighting.illumenate_lighting.system_design.portal_pages import project_designs

	context.system_designs = project_designs(schedules)
	context.can_edit = can_edit
	context.schedule_status_class = schedule_status_class
	context.schedule_status_label = schedule_status_label
	from illumenate_lighting.illumenate_lighting.portal.status import (
		project_status_class,
		project_status_label,
	)

	context.project_status_label = project_status_label
	context.project_status_class = project_status_class
	context.title = project.project_name
	context.no_cache = 1
	context.frappe = frappe  # Make frappe available in template
	context.contact_details = contact_details  # Pre-loaded contact details (project_manager)
	context.party_labels = project_parties.project_labels(project)
	context.party_options = project_parties.picker_options(project) if can_edit else {}
	# FLOW-8: the end client and owner company by name. A legacy end client that is a
	# Customer other than the owner company stays read-only; a party end client can change.
	context.customer_label = project_parties.end_client_label(project)
	context.end_client_editable = bool(
		project.get("end_client_party") or project.customer == project.get("owner_customer")
	)
	context.owner_company_label = _customer_label(project.get("owner_customer"))
	context.can_create_parties = _can_create_parties()

	return context


def schedule_status_class(status):
	"""Return CSS class for schedule status badge (shared vocabulary)."""
	from illumenate_lighting.illumenate_lighting.portal.status import (
		schedule_status_class as _status_class,
	)

	return _status_class(status)


def _get_new_project_context(context):
	"""Get context for creating a new project."""
	from illumenate_lighting.illumenate_lighting.api.portal import (
		get_allowed_customers_for_project,
	)
	from illumenate_lighting.illumenate_lighting.portal import project_parties
	from illumenate_lighting.illumenate_lighting.portal.project_owner import (
		can_set_owner_company,
		dealer_companies,
	)

	# Get allowed customers for the dropdown
	allowed_result = get_allowed_customers_for_project()

	context.is_new = True
	context.user_customer = allowed_result.get("user_customer")
	context.allowed_customers = allowed_result.get("allowed_customers", [])
	context.title = _("Create Project")
	context.no_cache = 1
	# REL-5: sales staff name the dealer company that owns the project; dealers own theirs.
	context.can_set_owner_company = can_set_owner_company()
	context.dealer_companies = dealer_companies() if context.can_set_owner_company else []
	# FLOW-5: without a company there is nothing to create a project for yet.
	context.needs_company = not context.can_set_owner_company and not context.user_customer
	context.owner_company_label = _customer_label(context.user_customer, context.allowed_customers)
	context.can_create_parties = _can_create_parties()
	# DESK-9: a dealer picks from their company's parties; staff load them once they pick the owner.
	context.party_options = (
		{} if context.needs_company or context.can_set_owner_company else project_parties.picker_options()
	)

	return context


def _customer_label(customer, options=()):
	if not customer:
		return None
	label = next((option["label"] for option in options if option["value"] == customer), None)
	return label or frappe.db.get_value("Customer", customer, "customer_name") or customer


def _can_create_parties():
	"""create_party and create_contact accept dealers and internal users only."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_is_dealer_user,
		_is_internal_user,
	)

	user = frappe.session.user
	return bool(_is_dealer_user(user) or _is_internal_user(user))
