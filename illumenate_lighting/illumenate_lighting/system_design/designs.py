# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Open, save, revise and copy ilL-System-Design records (WP-2.3, WP-2.4).

The document contract (validation and build hash) lives in :mod:`.design_schema` (WP-2.2).
"""

import json

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from illumenate_lighting.illumenate_lighting.system_design import (
	access,
	catalog,
	deliverables,
	expansion,
	gate,
	reconcile,
	telemetry,
	verify,
)
from illumenate_lighting.illumenate_lighting.system_design.design_schema import (
	build_hash,
	canonical_json,
	validate_design_json,
)
from illumenate_lighting.illumenate_lighting.system_design.errors import DesignError
from illumenate_lighting.illumenate_lighting.system_design.settings import is_enabled_for, settings

__all__ = [
	"build_hash",
	"canonical_json",
	"copy_design_to_version",
	"create_revision",
	"find_schedules",
	"open_design",
	"reconcile_design",
	"save_design",
	"validate_design_json",
	"verify_design",
]

DESIGN_DOCTYPE = "ilL-System-Design"
FIND_LIMIT = 20
MAX_DESIGN_BYTES = 5 * 1024 * 1024
SCHEMA_VERSION = 1
EDITABLE_STATUSES = ("Draft", "Changes Requested")
DMX_ZONE_METHODS = {"DMX512", "CRMX-wireless"}
PHASE_ZONE_METHODS = {"phase-forward", "phase-reverse"}
CLIENT_SETTINGS = (
	"vd_target_class2_pct",
	"vd_target_line_pct",
	"vd_target_landscape_pct",
	"wire_waste_pct",
	"max_watts_per_run_fallback",
	"group_threshold_qty",
	"default_distance_same_space_ft",
	"default_distance_adjacent_ft",
	"default_distance_other_level_ft",
	"plan_route_slack_pct",
	"nec_edition",
	"terms_text",
)


def require_designer():
	if not is_enabled_for():
		raise DesignError("FORBIDDEN", _("The System Designer is not available for your account yet"))


def _designs_exist():
	return bool(frappe.db.exists("DocType", DESIGN_DOCTYPE))


def permissions(doc):
	from illumenate_lighting.illumenate_lighting.portal.access import can_edit_schedule
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	return {
		"can_edit": bool(can_edit_schedule(doc) and not doc.get("is_locked")),
		"can_review": bool(allowed("design_review")),
		"can_view_pricing": "Can View Pricing" in frappe.get_roles(),
		# Engineering mode is always on for ilLumenate engineering staff (plan §7, WP-3.8).
		"can_engineer": bool(allowed("engineering") or allowed("design_review")),
	}


def open_design(schedule, design=None):
	"""Everything the designer needs to start on a schedule (H6 ``open_design``)."""
	doc = access.require_read(schedule)
	require_designer()
	values = settings()
	snapshot_hash = catalog.current_snapshot_hash()
	payload = catalog.get_snapshot(snapshot_hash) or {"items": []}
	kinds = {item["id"]: item["specs"]["kind"] for item in payload["items"]}
	lines, builds, readiness = expansion.expand_schedule(doc, kinds)
	record = access.require_design(design, doc.name) if design else current_design(doc)
	telemetry.record("opened", doc.name, record.name if record else None)
	return {
		"schedule": {
			"name": doc.name,
			"schedule_name": doc.get("schedule_name"),
			"version": doc.get("version") or 0,
			"is_locked": bool(doc.get("is_locked")),
			"status": doc.get("status"),
			"project": doc.get("ill_project"),
		},
		"lines": lines,
		"builds": builds,
		"design": stored_design(record) if record else None,
		"design_meta": design_meta(record) if record else None,
		"reconcile": reconcile_for(record, lines, builds) if record else None,
		"catalog_hash": snapshot_hash,
		"readiness": readiness,
		"review_requirement": gate.review_requirement(lines, builds, values),
		"permissions": permissions(doc),
		"settings": client_settings(values),
		"newer_version": newer_version(doc) if doc.get("is_locked") else None,
		"user": frappe.session.user,
		"title_block": title_block(doc),
		"deliverables": deliverables.list_deliverables(record) if record else [],
	}


def title_block(schedule_doc):
	"""What the riser title block names (plan §12.1): project, site, dealer and the dealer's logo."""
	project = None
	if schedule_doc.get("ill_project"):
		project = frappe.db.get_value(
			"ilL-Project",
			schedule_doc.get("ill_project"),
			["name", "project_name", "location", "customer"],
			as_dict=True,
		)
	customer = schedule_doc.get("customer") or (project.customer if project else None)
	name = logo = None
	if customer:
		name = frappe.db.get_value("Customer", customer, "customer_name")
		# The field arrives by patch, so a site that has not migrated yet has no logo.
		if frappe.get_meta("Customer").has_field("dealer_logo"):
			logo = frappe.db.get_value("Customer", customer, "dealer_logo")
	return {
		"project_name": (project.project_name if project else None)
		or schedule_doc.get("schedule_name")
		or "",
		"project_number": project.name if project else "",
		"site_address": (project.location if project else None) or "",
		"customer": name or customer or "",
		"dealer_logo": logo or None,
	}


def client_settings(values):
	"""Settings the browser needs; the terms are sent as plain text (the client renders no HTML)."""
	result = {key: values[key] for key in CLIENT_SETTINGS}
	result["terms_text"] = frappe.utils.strip_html(result.get("terms_text") or "").strip()
	return result


def newer_version(schedule_doc):
	"""The newest version of a locked schedule, ``{name, version}``, when it is not this one."""
	root = _schedule_root(schedule_doc)
	rows = frappe.get_all(
		"ilL-Project-Fixture-Schedule",
		filters={"version_parent": root},
		fields=["name", "version"],
		order_by="version desc",
		limit=1,
	)
	if not rows or rows[0].name == schedule_doc.name:
		return None
	return {"name": rows[0].name, "version": rows[0].version or 0}


def find_schedules(query, limit=FIND_LIMIT):
	"""Schedules the user can read whose name, title or project matches ``query`` (≥ 2 characters)."""
	from illumenate_lighting.illumenate_lighting.portal.access import schedule_query_conditions

	if frappe.session.user == "Guest":
		raise DesignError("FORBIDDEN", _("Please log in to continue"))
	require_designer()
	text = str(query or "").strip()
	if len(text) < 2:
		raise DesignError("INVALID", _("Type at least two characters"))
	try:
		limit = max(1, min(int(limit or FIND_LIMIT), FIND_LIMIT))
	except (TypeError, ValueError):
		limit = FIND_LIMIT
	conditions = schedule_query_conditions()
	pattern = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
	table = "`tabilL-Project-Fixture-Schedule`"
	# ``conditions`` names the schedule table in full, so the query does not alias it.
	rows = frappe.db.sql(
		f"""
		select {table}.name, {table}.schedule_name, {table}.ill_project as project,
			proj.project_name, {table}.version
		from {table}
		left join `tabilL-Project` proj on proj.name = {table}.ill_project
		where ({table}.name like %(pattern)s or {table}.schedule_name like %(pattern)s
			or proj.project_name like %(pattern)s)
			{"and (" + conditions + ")" if conditions else ""}
		order by {table}.modified desc
		limit {limit}
		""",
		{"pattern": pattern},
		as_dict=True,
	)
	designed = set()
	if rows and _designs_exist():
		designed = set(
			frappe.get_all(
				DESIGN_DOCTYPE,
				filters={"fixture_schedule": ["in", [r["name"] for r in rows]]},
				pluck="fixture_schedule",
			)
		)
	return [
		{
			"name": row["name"],
			"schedule_name": row.get("schedule_name"),
			"project": row.get("project"),
			"project_name": row.get("project_name"),
			"version": row.get("version") or 0,
			"has_design": row["name"] in designed,
		}
		for row in rows
	]


# --- Saved designs and revisions (WP-2.4, H6) -----------------------------------------------------


def design_meta(record):
	return {
		"name": record.name,
		"revision": record.revision,
		"status": record.status,
		"modified": str(record.modified),
		"schedule_version": record.schedule_version,
		"is_current": bool(record.is_current),
		"terms_accepted": bool(record.get("terms_accepted_by")),
		# The Applications Engineer who approved this revision checks the riser (plan §12.1).
		"approved_by": frappe.utils.get_fullname(record.approved_by)
		if record.status == "Approved" and record.get("approved_by")
		else None,
	}


def stored_design(record):
	return json.loads(record.design_json)


def reconcile_for(record, lines, builds):
	"""H8.4 diff between a saved design and its schedule as it is now."""
	stored = json.loads(record.line_fingerprint_json or "{}")
	return reconcile.diff(stored, lines, builds, stored_design(record).get("runs") or [])


def current_design(schedule_doc):
	"""The current revision for the schedule's version, or ``None``."""
	if not _designs_exist():
		return None
	names = frappe.get_all(
		DESIGN_DOCTYPE,
		filters={
			"fixture_schedule": schedule_doc.name,
			"schedule_version": schedule_doc.get("version") or 0,
			"is_current": 1,
		},
		order_by="modified desc",
		limit=1,
		pluck="name",
	)
	return frappe.get_doc(DESIGN_DOCTYPE, names[0]) if names else None


def next_revision(revision):
	"""A → B … Z → AA → AB (spreadsheet columns)."""
	value = 0
	for char in (revision or "").upper():
		if not "A" <= char <= "Z":
			raise ValueError(f"Not a revision letter: {revision}")
		value = value * 26 + (ord(char) - 64)
	value += 1
	letters = ""
	while value:
		value, rest = divmod(value - 1, 26)
		letters = chr(65 + rest) + letters
	return letters


def parse_design(design_json):
	"""Parse and size-check the posted design (≤ 5 MB of UTF-8)."""
	raw = design_json if isinstance(design_json, str) else json.dumps(design_json or None)
	if len(raw.encode("utf-8")) > MAX_DESIGN_BYTES:
		raise DesignError("INVALID", _("This design is larger than 5 MB; remove saved views and try again"))
	try:
		design = json.loads(raw)
	except ValueError:
		raise DesignError("INVALID", _("The design is not valid JSON"))
	return design


def design_summary(design, lines, builds, values):
	"""Stored totals and the D4 / D8 flags. Errors and warnings arrive with server verify (WP-3)."""
	total, protocols = gate.load_profile(lines, builds)
	methods = {zone.get("method") for zone in design.get("zones") or []}
	uses_dmx = bool(protocols & gate.DMX_PROTOCOLS or methods & DMX_ZONE_METHODS)
	uses_phase = bool(protocols & gate.PHASE_PROTOCOLS or methods & PHASE_ZONE_METHODS)
	reasons = gate.reasons_from(total, protocols | methods, values) if gate.gate_enabled(values) else []
	runs = design.get("runs") or []
	site = design.get("site") or {}
	return {
		"runs": len(runs),
		"spaces": len(site.get("spaces") or []),
		"cabinets": len(site.get("cabinets") or []),
		"zones": len(design.get("zones") or []),
		"total_connected_w": round(total, 1),
		"uses_dmx": uses_dmx,
		"uses_phase_dimming": uses_phase,
		"has_dealer_data": any((run.get("source") or {}).get("kind") == "third-party" for run in runs),
		"review_required": bool(reasons),
		"review_reasons": reasons,
	}


def _check_design(design, schedule_doc, values):
	problems = validate_design_json(design, values)
	if problems:
		raise DesignError(
			"INVALID", _("The design did not pass validation: {0}").format("; ".join(problems[:5]))
		)
	ref = design["schedule"]
	if ref["name"] != schedule_doc.name:
		raise DesignError("INVALID", _("This design belongs to a different schedule"))
	if ref["version"] != (schedule_doc.get("version") or 0):
		raise DesignError(
			"CONFLICT",
			_("The schedule changed since this design was opened; reopen it to bring in the changes"),
		)
	if not frappe.db.exists(catalog.SNAPSHOT_DOCTYPE, design["catalogSnapshotHash"]):
		raise DesignError("INVALID", _("The design uses a catalog this server does not know; reopen it"))


def _apply(record, design, schedule_doc, lines, builds, values):
	summary = design_summary(design, lines, builds, values)
	record.update(
		{
			"design_json": canonical_json(design),
			"design_schema_version": design["schemaVersion"],
			"engine_version": design["engineVersion"],
			"catalog_snapshot": design["catalogSnapshotHash"],
			"build_hash": build_hash(design),
			"line_fingerprint_json": canonical_json(reconcile.fingerprints(lines, builds)),
			"result_summary_json": canonical_json(summary),
			"total_connected_w": summary["total_connected_w"],
			"uses_dmx": int(summary["uses_dmx"]),
			"uses_phase_dimming": int(summary["uses_phase_dimming"]),
			"has_dealer_data": int(summary["has_dealer_data"]),
			"review_required": int(summary["review_required"]),
			"review_required_reasons": "\n".join(
				f"{reason['code']}: {reason['detail']}" for reason in summary["review_reasons"]
			),
		}
	)
	return summary


def _locked_for_edit(record, expected_modified):
	"""Lock the row, then refuse stale, superseded or submitted revisions."""
	current = frappe.db.get_value(DESIGN_DOCTYPE, record.name, "modified", for_update=True)
	if not expected_modified:
		raise DesignError("INVALID", _("expected_modified is required when saving an existing design"))
	try:
		stale = get_datetime(expected_modified) != get_datetime(current)
	except Exception:
		raise DesignError("INVALID", _("expected_modified is not a valid timestamp"))
	if stale:
		raise DesignError(
			"CONFLICT", _("Someone else saved this design after you opened it; reload to see their changes")
		)
	if not record.is_current:
		raise DesignError("CONFLICT", _("A newer revision of this design exists; open it instead"))
	if record.status not in EDITABLE_STATUSES:
		raise DesignError(
			"LOCKED", _("This revision is {0}; create a new revision to change it").format(_(record.status))
		)


def save_design(
	schedule, design_json, design_name=None, expected_modified=None, reconciled=False, terms_accepted=False
):
	"""Create or update the current design of a schedule version (H6 ``save_design``).

	When the schedule changed since the last save, the client must apply the H8.4 diff and say so
	with ``reconciled``; otherwise the save is a ``CONFLICT`` and the stored fingerprints stay put.
	A revision is saved only once someone accepted the terms on it (``terms_accepted``, H9).
	"""
	schedule_doc = access.require_edit(schedule)
	require_designer()
	design = parse_design(design_json)
	values = settings()
	_check_design(design, schedule_doc, values)
	lines, builds, _readiness = expansion.expand_schedule(schedule_doc, {})
	if design_name:
		record = access.require_design(design_name, schedule_doc.name)
		_locked_for_edit(record, expected_modified)
		if record.schedule_version != (schedule_doc.get("version") or 0):
			raise DesignError("CONFLICT", _("This design is for an earlier schedule version"))
		if not _truthy(reconciled) and not reconcile_for(record, lines, builds)["in_sync"]:
			raise DesignError(
				"CONFLICT", _("The schedule changed since this design was saved; review the changes first")
			)
	else:
		existing = current_design(schedule_doc)
		if existing:
			raise DesignError(
				"CONFLICT",
				_("This schedule already has a design ({0}); open it instead").format(existing.name),
			)
		record = frappe.new_doc(DESIGN_DOCTYPE)
		record.update(
			{
				"title": _("{0} design").format(schedule_doc.get("schedule_name") or schedule_doc.name),
				"fixture_schedule": schedule_doc.name,
				"schedule_version": schedule_doc.get("version") or 0,
				"ill_project": schedule_doc.get("ill_project"),
				"customer": schedule_doc.get("customer"),
				"status": "Draft",
				"revision": "A",
				"is_current": 1,
			}
		)
	_accept_terms(record, terms_accepted)
	summary = _apply(record, design, schedule_doc, lines, builds, values)
	record.flags.ignore_permissions = True
	if record.is_new():
		record.insert()
	else:
		record.save()
	telemetry.record("saved", record.fixture_schedule, record.name, {"revision": record.revision})
	return {
		"name": record.name,
		"revision": record.revision,
		"modified": str(record.modified),
		"build_hash": record.build_hash,
		"summary": summary,
	}


def _truthy(value):
	return value in (True, 1, "1", "true", "True")


def _accept_terms(record, terms_accepted):
	"""Record the first acceptance of the terms on this revision (``terms_accepted_by/on``)."""
	if record.get("terms_accepted_by"):
		return
	if not _truthy(terms_accepted):
		raise DesignError("INVALID", _("Accept the System Designer terms before saving"))
	record.terms_accepted_by = frappe.session.user
	record.terms_accepted_on = now_datetime()


REVISION_RESET = (
	"review_request",
	"approved_review",
	"approved_by",
	"approved_on",
	"terms_accepted_by",
	"terms_accepted_on",
)


def create_revision(design, note=None):
	"""Start the next revision as a Draft copy; the old one stops being current (H6)."""
	record = access.require_design(design)
	access.require_edit(record.fixture_schedule)
	require_designer()
	frappe.db.get_value(DESIGN_DOCTYPE, record.name, "name", for_update=True)
	if not frappe.db.get_value(DESIGN_DOCTYPE, record.name, "is_current"):
		raise DesignError("CONFLICT", _("A newer revision of this design exists; open it instead"))
	revision = frappe.copy_doc(record)
	revision.update(
		{
			"revision": next_revision(record.revision),
			"revision_parent": record.name,
			"status": "Draft",
			"is_current": 1,
			"deliverables": [],
			"shares": [],
			"comments": [],
			**{field: None for field in REVISION_RESET},
		}
	)
	record.db_set("is_current", 0)
	revision.flags.ignore_permissions = True
	revision.insert()
	text = str(note or "").strip()
	if text:
		revision.add_comment("Comment", text[:1000])
	return {"name": revision.name, "revision": revision.revision}


# --- Reconcile and copy forward (WP-2.5, H6, H8.4) ------------------------------------------------


def reconcile_design(design):
	"""The H8.4 diff for a saved design against its schedule now."""
	record = access.require_design(design)
	require_designer()
	schedule_doc = access.require_read(record.fixture_schedule)
	lines, builds, _readiness = expansion.expand_schedule(schedule_doc, {})
	return reconcile_for(record, lines, builds)


def verify_design(design, client=None):
	"""Re-check a saved design's gating subset on the server (H6 ``verify_design``, plan §18.2).

	``client`` is the designer's own subset (``verifySubset``); without it the server answer is returned
	with no comparison. The outcome is stored on the design for its reviewer.
	"""
	record = access.require_design(design)
	require_designer()
	schedule_doc = access.require_read(record.fixture_schedule)
	if client is not None and not isinstance(client, dict):
		raise DesignError("INVALID", _("client must be the designer's check subset"))
	payload = catalog.get_snapshot(record.catalog_snapshot)
	if payload is None:
		raise DesignError("NOT_FOUND", _("Catalog snapshot not found"))
	values = settings()
	lines, _builds, _readiness = expansion.expand_schedule(schedule_doc, {})
	server = verify.subset(
		stored_design(record),
		[*payload["items"], *verify.dealer_items(lines)],
		payload.get("wires") or [],
		verify.vd_limits(values),
		gate={
			"watts": values.review_gate_watts,
			"dmx": bool(values.review_gate_dmx),
			"phase_dimming": bool(values.review_gate_phase_dimming),
		},
	)
	mismatches = verify.compare(client, server) if client is not None else []
	outcome = {
		"ok": not mismatches,
		"build_hash": record.build_hash,
		"verified_on": str(now_datetime()),
		"compared": client is not None,
		"mismatches": mismatches,
		"summary": server,
	}
	record.db_set("verification_json", canonical_json(outcome), update_modified=False)
	return {"ok": outcome["ok"], "mismatches": mismatches, "summary": server}


def _schedule_root(schedule_doc):
	return schedule_doc.get("version_parent") or schedule_doc.name


def copy_design_to_version(design, target_schedule):
	"""Start a design on another version of the same schedule (H6 ``copy_design_to_version``).

	The copy keeps the source's line fingerprints, so opening it shows the H8.4 diff to apply.
	"""
	record = access.require_design(design)
	source_schedule = access.require_read(record.fixture_schedule)
	target = access.require_edit(target_schedule)
	require_designer()
	if target.name == source_schedule.name:
		raise DesignError("INVALID", _("Choose a different version of this schedule"))
	if _schedule_root(target) != _schedule_root(source_schedule):
		raise DesignError("INVALID", _("A design can only be copied to another version of the same schedule"))
	existing = current_design(target)
	if existing:
		raise DesignError(
			"CONFLICT",
			_("That schedule version already has a design ({0}); open it instead").format(existing.name),
		)
	body = stored_design(record)
	body["schedule"] = {"name": target.name, "version": target.get("version") or 0}
	copy = frappe.new_doc(DESIGN_DOCTYPE)
	copy.update(
		{
			"title": _("{0} design").format(target.get("schedule_name") or target.name),
			"fixture_schedule": target.name,
			"schedule_version": target.get("version") or 0,
			"ill_project": target.get("ill_project"),
			"customer": target.get("customer"),
			"status": "Draft",
			"revision": "A",
			"revision_parent": record.name,
			"is_current": 1,
			"design_json": canonical_json(body),
			"design_schema_version": record.design_schema_version,
			"engine_version": record.engine_version,
			"catalog_snapshot": record.catalog_snapshot,
			"build_hash": build_hash(body),
			"line_fingerprint_json": record.line_fingerprint_json,
			"result_summary_json": record.result_summary_json,
			**{field: record.get(field) for field in COPIED_FLAGS},
		}
	)
	copy.flags.ignore_permissions = True
	copy.insert()
	return {"name": copy.name}


COPIED_FLAGS = (
	"total_connected_w",
	"uses_dmx",
	"uses_phase_dimming",
	"has_dealer_data",
	"review_required",
	"review_required_reasons",
)
