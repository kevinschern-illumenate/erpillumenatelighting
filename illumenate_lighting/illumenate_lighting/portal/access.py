# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal access policy.

One place for the actor context, named capability decisions and the list
predicates derived from them, so that a document-level ``has_permission``
answer and the list/query visibility for the same persona cannot disagree.

Personas (see docs/DEALER_PORTAL_ASSESSMENT_AND_IMPLEMENTATION_PLAN.md §9/§14):

- Internal (System Manager / Administrator): everything.
- Dealer linked to the project's owner company: read and mutate all of that
  company's projects and schedules, manage collaborators.
- Same-company non-dealer user: read company-visible (non-private) records
  only; no mutation unless they own the record or hold an EDIT invite.
- VIEW collaborator: read the invited project and its inherited schedules.
- EDIT collaborator: read + write the invited project and its inherited
  schedules, but no owner/admin operations (delete, privacy, collaborators).
- Guest: nothing.
"""

import frappe

# Resolved at call time (not by name) so tests that patch these helpers on
# the ill_project module see the same behaviour here.
from illumenate_lighting.illumenate_lighting.doctype.ill_project import (
	ill_project as _identity,
)

# Permission types that only disclose data. Anything else is treated as a
# mutation and requires an explicit mutation capability.
READ_PTYPES = frozenset({"read", "report", "print", "email", "export", "select"})

# Permission types reserved for the record owner / company admins / internal.
OWNER_PTYPES = frozenset({"delete", "cancel", "amend"})

PROJECT_TABLE = "`tabilL-Project`"
SCHEDULE_TABLE = "`tabilL-Project-Fixture-Schedule`"
COLLABORATOR_TABLE = "`tabilL-Child-Project-Collaborator`"

# Configured product records the portal may attach to a schedule line, mapped
# to the schedule-line field that references them.
CONFIGURED_RECORD_LINE_FIELDS = {
	"ilL-Configured-Group": "configured_group",
	"ilL-Configured-Fixture": "configured_fixture",
	"ilL-Configured-Tape-Neon": "configured_tape_neon",
	"ilL-Configured-LED-Sheet": "configured_led_sheet",
}

# How long a validated configured record stays attachable by the session that
# validated it. Long enough for a configure -> review -> save flow.
CONFIGURED_HANDOFF_TTL_SECONDS = 12 * 60 * 60


# ---------------------------------------------------------------------------
# Actor context
# ---------------------------------------------------------------------------


class Actor:
	"""Resolved identity facts for one user, computed once per decision."""

	__slots__ = ("customer", "is_dealer", "is_guest", "is_internal", "user")

	def __init__(self, user=None):
		self.user = user or frappe.session.user
		self.is_guest = self.user == "Guest" or not frappe.db.get_value("User", self.user, "enabled")
		self.is_internal = False if self.is_guest else _identity._is_internal_user(self.user)
		self.is_dealer = False if self.is_guest else _identity._is_dealer_user(self.user)
		self.customer = None if self.is_guest else _identity._get_user_customer(self.user)

	def is_company_dealer_for(self, owner_customer) -> bool:
		return bool(self.is_dealer and self.customer and self.customer == owner_customer)

	def is_company_member_of(self, owner_customer) -> bool:
		return bool(self.customer and self.customer == owner_customer)


def get_actor(user=None) -> Actor:
	return Actor(user)


def _is_read(ptype: str) -> bool:
	return ptype in READ_PTYPES


# ---------------------------------------------------------------------------
# Project capabilities
# ---------------------------------------------------------------------------


def _active_collaborator_level(project, user):
	for c in project.get("collaborators") or []:
		if c.user == user and c.is_active:
			return c.access_level
	return None


def project_permission(project, ptype="read", user=None) -> bool:
	"""Document-level decision for ``ilL-Project``.

	Read-like ptypes follow visibility; everything else requires a mutation
	capability. Company membership alone never grants a mutation.
	"""
	actor = get_actor(user)
	if actor.is_guest:
		return False
	if actor.is_internal:
		return True
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if allowed("sales", actor.user) and ptype in READ_PTYPES | {"write", "create"}:
		return True
	if project.owner == actor.user:
		return True

	level = _active_collaborator_level(project, actor.user)
	if level:
		if _is_read(ptype):
			return True
		if ptype in OWNER_PTYPES:
			return False
		return level == "EDIT"

	if actor.is_company_member_of(project.owner_customer):
		if actor.is_dealer:
			return True
		return _is_read(ptype) and not project.is_private

	return False


def can_read_project(project, user=None) -> bool:
	return project_permission(project, "read", user)


def can_edit_project(project, user=None) -> bool:
	return project_permission(project, "write", user)


def can_manage_project_collaborators(project, user=None) -> bool:
	"""Owner, internal users and Dealers of the owning company may manage
	collaborators and privacy. EDIT collaborators may not."""
	actor = get_actor(user)
	if actor.is_guest:
		return False
	if actor.is_internal or project.owner == actor.user:
		return True
	return actor.is_company_dealer_for(project.owner_customer)


# ---------------------------------------------------------------------------
# Catalog / pricing visibility
# ---------------------------------------------------------------------------


def can_view_catalog(user=None) -> bool:
	"""The product catalog (with MSRP) is for Dealers and internal users."""
	actor = get_actor(user)
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	return not actor.is_guest and (actor.is_internal or actor.is_dealer or any(allowed(capability, actor.user) for capability in ("sales", "engineering", "catalog")))


def require_catalog_access(user=None) -> None:
	if not can_view_catalog(user):
		frappe.throw(
			frappe._("The product catalog is available to dealers and ilLumenate staff."),
			frappe.PermissionError,
		)


def _project_visibility_sql(actor: Actor, table: str = PROJECT_TABLE):
	"""SQL predicate matching the projects ``actor`` may read.

	Returns ``None`` when the actor is unrestricted. Mirrors
	:func:`project_permission` for ``ptype="read"``.
	"""
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if actor.is_internal or allowed("sales", actor.user):
		return None
	if actor.is_guest:
		return "1=0"

	user = frappe.db.escape(actor.user)
	clauses = [
		f"{table}.owner = {user}",
		f"""{table}.name IN (
			SELECT parent FROM {COLLABORATOR_TABLE}
			WHERE user = {user} AND is_active = 1
		)""",
	]
	if actor.customer:
		customer = frappe.db.escape(actor.customer)
		if actor.is_dealer:
			clauses.append(f"{table}.owner_customer = {customer}")
		else:
			clauses.append(
				f"({table}.owner_customer = {customer} AND {table}.is_private = 0)"
			)
	return "(" + " OR ".join(clauses) + ")"


def project_query_conditions(user=None) -> str:
	actor = get_actor(user)
	return _project_visibility_sql(actor) or ""


# ---------------------------------------------------------------------------
# Schedule capabilities
# ---------------------------------------------------------------------------


def _project_owner_customer(project_name):
	if not project_name:
		return None
	return frappe.db.get_value("ilL-Project", project_name, "owner_customer")


def schedule_permission(schedule, ptype="read", user=None) -> bool:
	"""Document-level decision for ``ilL-Project-Fixture-Schedule``.

	Inherited schedules follow the project decision. Non-inherited schedules
	apply schedule-level privacy against ``schedule.customer``. Dealers of the
	owning company always have access through the project link.
	"""
	actor = get_actor(user)
	if actor.is_guest:
		return False
	if actor.is_internal:
		return True
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if allowed("sales", actor.user) and ptype in READ_PTYPES | {"write", "create"}:
		return True
	if schedule.owner == actor.user:
		return True

	if schedule.inherits_project_privacy and schedule.ill_project:
		project = frappe.get_doc("ilL-Project", schedule.ill_project)
		return project_permission(project, ptype, actor.user)

	if actor.is_dealer and actor.is_company_dealer_for(
		_project_owner_customer(schedule.ill_project)
	):
		return True

	if actor.is_company_member_of(schedule.customer):
		if actor.is_dealer:
			return True
		return _is_read(ptype) and not schedule.is_private

	return False


def can_read_schedule(schedule, user=None) -> bool:
	return schedule_permission(schedule, "read", user)


def can_edit_schedule(schedule, user=None) -> bool:
	return schedule_permission(schedule, "write", user)


def schedule_query_conditions(user=None) -> str:
	"""SQL predicate matching the schedules ``user`` may read. Mirrors
	:func:`schedule_permission` for ``ptype="read"``."""
	actor = get_actor(user)
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if actor.is_internal or allowed("sales", actor.user):
		return ""
	if actor.is_guest:
		return "1=0"

	user_sql = frappe.db.escape(actor.user)
	project_pred = _project_visibility_sql(actor, table="p")
	clauses = [
		f"{SCHEDULE_TABLE}.owner = {user_sql}",
		f"""(
			{SCHEDULE_TABLE}.inherits_project_privacy = 1
			AND {SCHEDULE_TABLE}.ill_project IN (
				SELECT p.name FROM {PROJECT_TABLE} p WHERE {project_pred}
			)
		)""",
	]
	if actor.customer:
		customer = frappe.db.escape(actor.customer)
		if actor.is_dealer:
			clauses.append(
				f"""(
				{SCHEDULE_TABLE}.inherits_project_privacy = 0
				AND (
					{SCHEDULE_TABLE}.customer = {customer}
					OR {SCHEDULE_TABLE}.ill_project IN (
						SELECT p.name FROM {PROJECT_TABLE} p WHERE p.owner_customer = {customer}
					)
				)
			)"""
			)
		else:
			clauses.append(
				f"""(
				{SCHEDULE_TABLE}.inherits_project_privacy = 0
				AND {SCHEDULE_TABLE}.is_private = 0
				AND {SCHEDULE_TABLE}.customer = {customer}
			)"""
			)
	return "(" + " OR ".join(clauses) + ")"


# ---------------------------------------------------------------------------
# Configured product provenance
# ---------------------------------------------------------------------------


def _handoff_key(doctype: str, name: str, user: str) -> str:
	return f"ill_cfg_handoff|{user}|{doctype}|{name}"


def register_configured_record_handoff(doctype: str, name: str, user=None) -> None:
	"""Record that ``user`` produced ``name`` through a validation endpoint in
	this session so it can later be attached to a schedule even though
	configured records are content-addressed and shared between users."""
	user = user or frappe.session.user
	if not name or user == "Guest":
		return
	frappe.cache().set_value(
		_handoff_key(doctype, name, user), 1, expires_in_sec=CONFIGURED_HANDOFF_TTL_SECONDS
	)


def has_configured_record_handoff(doctype: str, name: str, user=None) -> bool:
	user = user or frappe.session.user
	if not name or user == "Guest":
		return False
	return bool(frappe.cache().get_value(_handoff_key(doctype, name, user)))


def clear_configured_record_handoff(doctype: str, name: str, user=None) -> None:
	user = user or frappe.session.user
	if name:
		frappe.cache().delete_value(_handoff_key(doctype, name, user))


def can_read_configured_record(doctype: str, name: str, user=None) -> bool:
	"""A configured-record id is guessable, so knowing it is not authorisation.

	Access is proven by being internal, having created the record, having
	validated it in this session, or by it already sitting on a schedule the
	user may read.
	"""
	actor = get_actor(user)
	if actor.is_guest:
		return False
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if actor.is_internal or allowed("sales", actor.user) or allowed("engineering", actor.user):
		return True
	if not frappe.db.exists(doctype, name):
		return False
	if frappe.db.get_value(doctype, name, "owner") == actor.user:
		return True
	if has_configured_record_handoff(doctype, name, actor.user):
		return True

	line_fieldname = CONFIGURED_RECORD_LINE_FIELDS.get(doctype)
	if not line_fieldname:
		return False

	schedule_names = frappe.get_all(
		"ilL-Child-Fixture-Schedule-Line",
		filters={line_fieldname: name, "parenttype": "ilL-Project-Fixture-Schedule"},
		pluck="parent",
	)
	for schedule_name in set(schedule_names):
		if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
			continue
		schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)
		if schedule_permission(schedule, "read", actor.user):
			return True
	return False


def can_attach_configured_record(doctype: str, name: str, user=None) -> bool:
	"""Attaching a configured record to a schedule line requires the same
	provenance as reading it; the schedule write check is separate."""
	return can_read_configured_record(doctype, name, user)
