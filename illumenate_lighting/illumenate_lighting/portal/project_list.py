# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""The portal projects list (FLOW-3) and schedule version families (FLOW-9).

``list_projects`` searches, filters, sorts and pages on the server through the
project permission query, then adds per project: the number of schedules
(version families, not every version), the last activity, the owning company,
the next step taken from its schedules and whether the viewer may archive it.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.access import can_edit_project, schedule_query_conditions

PROJECT = "ilL-Project"
SCHEDULE = "ilL-Project-Fixture-Schedule"
PAGE_SIZE = 20
STATUS_FILTERS = {
	"active": {"status": ["!=", "ARCHIVED"]},
	"archived": {"status": "ARCHIVED"},
	"all": {},
}
SORTS = {"recent": "modified desc, name desc", "name": "project_name asc, name asc"}
# Most urgent first: the step a project shows is its most urgent schedule's.
SCHEDULE_STEPS = {
	"ISSUE": (0, "Order needs attention", "danger"),
	"QUOTED": (1, "Quote ready", "warning"),
	"READY": (2, "Ready to quote", "info"),
	"ORDER_REQUESTED": (3, "Order requested", "info"),
	"DRAFT": (4, "In progress", "secondary"),
	"ORDERED": (5, "Ordered", "success"),
	"CLOSED": (6, "Closed", "secondary"),
}
NO_SCHEDULE = (9, "Add a schedule", "secondary")


def options(status=None, sort=None, page=None):
	"""Normalise query-string options to supported values."""
	status = status if status in STATUS_FILTERS else "active"
	sort = sort if sort in SORTS else "recent"
	try:
		page = max(1, int(page or 1))
	except (TypeError, ValueError):
		page = 1
	return status, sort, page


def family(schedule):
	return schedule.get("version_parent") or schedule.name


def version_families(schedules):
	"""Group schedule versions: the latest of each family, with its earlier versions.

	Keeps the order families first appear in ``schedules``.
	"""
	families = {}
	for schedule in schedules:
		families.setdefault(family(schedule), []).append(schedule)
	grouped = []
	for versions in families.values():
		versions = sorted(versions, key=lambda row: row.get("version") or 1, reverse=True)
		grouped.append(frappe._dict(latest=versions[0], earlier=versions[1:]))
	return grouped


def next_step(latest_versions):
	_rank, label, tone = min(
		(SCHEDULE_STEPS.get(row.status, NO_SCHEDULE) for row in latest_versions), default=NO_SCHEDULE
	)
	return {"label": _(label), "tone": tone}


def _schedules_by_project(names, user):
	visibility = schedule_query_conditions(user)
	rows = frappe.db.sql(
		f"""
		SELECT name, ill_project, status, modified, version, version_parent
		FROM `tabilL-Project-Fixture-Schedule`
		WHERE ill_project IN %(names)s
		{"AND " + visibility if visibility else ""}
		""",
		{"names": tuple(names)},
		as_dict=True,
	)
	by_project = {}
	for row in rows:
		by_project.setdefault(row.ill_project, []).append(row)
	return by_project


def list_projects(user=None, search=None, status=None, sort=None, page=None, page_size=PAGE_SIZE):
	user = user or frappe.session.user
	status, sort, page = options(status, sort, page)
	query = str(search or "").strip()[:140]
	or_filters = None
	if query:
		like = f"%{query}%"
		or_filters = {"project_name": ["like", like], "customer": ["like", like], "name": ["like", like]}
	rows = frappe.get_list(
		PROJECT,
		filters=STATUS_FILTERS[status],
		or_filters=or_filters,
		fields=[
			"name",
			"project_name",
			"customer",
			"owner_customer",
			"status",
			"is_private",
			"modified",
			"owner",
		],
		order_by=SORTS[sort],
		limit_start=(page - 1) * page_size,
		limit_page_length=page_size + 1,
	)
	has_more = len(rows) > page_size
	rows = rows[:page_size]
	if rows:
		schedules = _schedules_by_project([row.name for row in rows], user)
		companies = dict(
			frappe.get_all(
				"Customer",
				filters={"name": ["in", sorted({row.owner_customer for row in rows if row.owner_customer})]},
				fields=["name", "customer_name"],
				as_list=True,
			)
		)
	for row in rows:
		latest = [group.latest for group in version_families(schedules.get(row.name, []))]
		row.schedule_count = len(latest)
		row.last_activity = max([row.modified, *(schedule.modified for schedule in latest)], key=str)
		row.company_name = companies.get(row.owner_customer) or row.owner_customer
		row.next_step = next_step(latest)
		row.can_edit = can_edit_project(frappe.get_doc(PROJECT, row.name), user)
	return {
		"projects": rows,
		"page": page,
		"has_more": has_more,
		"status_filter": status,
		"sort": sort,
		"search": query,
	}
