# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Design review requests, decisions and comments on top of portal/drawing_review.py (WP-4.2, WP-4.3).

"Request review" files an ``ilL-Document-Request`` of type **System Design Review** for the saved
revision (plan §14.2, H4.2). The request links the schedule, its project and the design, and names a
``technical_reviewer``: the next enabled ``ilL Applications Engineer`` in turn when Settings say
"Round Robin", or nobody when "Manual" (staff assign one in Desk). A revision with errors cannot be
sent for review.
"""

import json

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime

from illumenate_lighting.illumenate_lighting.system_design import (
	access,
	catalog,
	expansion,
	telemetry,
	verify,
)
from illumenate_lighting.illumenate_lighting.system_design.errors import DesignError
from illumenate_lighting.illumenate_lighting.system_design.settings import settings

DESIGN_DOCTYPE = "ilL-System-Design"
REQUEST_DOCTYPE = "ilL-Document-Request"
REQUEST_TYPE = "System Design Review"
REVIEWER_ROLE = "ilL Applications Engineer"
PRIORITIES = ("Normal", "High", "Rush")
REQUESTABLE = ("Draft", "Changes Requested")
OPEN_REQUEST = ("Draft", "Submitted", "In Progress", "Waiting on Customer")
# Gating checks the server re-computes that are always errors in the engine (plan §18.2).
SERVER_ERRORS = frozenset({"PSU_OVERLOAD", "VOLTAGE_MISMATCH", "TAPE_UNDERVOLTAGE"})
MAX_NOTE = 2000


# --- Pure helpers -------------------------------------------------------------------------------


def next_reviewer(reviewers, last):
	"""Round robin: the reviewer after ``last`` in name order, or the first one."""
	ordered = sorted(set(reviewers))
	if not ordered:
		return None
	if last in ordered:
		return ordered[(ordered.index(last) + 1) % len(ordered)]
	later = [name for name in ordered if last and name > last]
	return later[0] if later else ordered[0]


def overridden(design):
	"""``{(code, entityRef)}`` an Applications Engineer has overridden on this design."""
	return {
		(item.get("code"), item.get("entityRef"))
		for item in design.get("overrides") or []
		if item.get("kind") == "staff-override"
	}


def server_errors(messages, design):
	"""Codes of the server re-check that block a review request, less staff overrides."""
	skip = overridden(design)
	blocking = []
	for message in messages:
		code, _sep, ref = message.partition("|")
		if code in SERVER_ERRORS and (code, ref) not in skip:
			blocking.append(message)
	return blocking


def count(value, name):
	try:
		number = int(value or 0)
	except (TypeError, ValueError):
		raise DesignError("INVALID", _("{0} must be a whole number").format(name))
	if number < 0:
		raise DesignError("INVALID", _("{0} must be a whole number").format(name))
	return number


# --- Reviewers ----------------------------------------------------------------------------------


def reviewers():
	"""Enabled System Users holding the Applications Engineer role."""
	holders = frappe.get_all(
		"Has Role", filters={"role": REVIEWER_ROLE, "parenttype": "User"}, pluck="parent"
	)
	if not holders:
		return []
	return frappe.get_all(
		"User",
		filters={"name": ["in", sorted(set(holders))], "enabled": 1, "user_type": "System User"},
		pluck="name",
	)


def assign_reviewer(values):
	if (values.get("reviewer_assignment") or "Round Robin") != "Round Robin":
		return None
	last = frappe.get_all(
		REQUEST_DOCTYPE,
		filters={"request_type": REQUEST_TYPE, "technical_reviewer": ["is", "set"]},
		fields=["technical_reviewer"],
		order_by="creation desc",
		limit=1,
	)
	return next_reviewer(reviewers(), last[0].technical_reviewer if last else None)


# --- Request review (WP-4.2) --------------------------------------------------------------------


def _server_check(record, schedule_doc, values):
	payload = catalog.get_snapshot(record.catalog_snapshot)
	if payload is None:
		raise DesignError("NOT_FOUND", _("Catalog snapshot not found"))
	lines, _builds, _readiness = expansion.expand_schedule(schedule_doc, {})
	design = json.loads(record.design_json or "{}")
	result = verify.subset(
		design,
		[*payload["items"], *verify.dealer_items(lines)],
		payload.get("wires") or [],
		verify.vd_limits(values),
	)
	return server_errors(result["messages"], design)


def _description(record, schedule_doc, note):
	reasons = (record.get("review_required_reasons") or "").strip()
	parts = [
		_("System design {0}, revision {1}, for schedule {2}.").format(
			record.name, record.revision, schedule_doc.get("schedule_name") or schedule_doc.name
		),
		_("Review required before ordering: {0}").format(reasons.replace("\n", "; "))
		if record.get("review_required")
		else _("Optional review requested by the dealer."),
	]
	if note:
		parts.append(note)
	return "".join(f"<p>{frappe.utils.escape_html(part)}</p>" for part in parts)


def request_review(design, priority=None, due_date=None, note=None, error_count=None, warning_count=None):
	"""H6 ``request_review``: file the review request for a saved revision with no errors."""
	from illumenate_lighting.illumenate_lighting.system_design.designs import require_designer

	record = access.require_design(design)
	schedule_doc = access.require_edit(record.fixture_schedule)
	require_designer()
	frappe.db.get_value(DESIGN_DOCTYPE, record.name, "name", for_update=True)
	record.reload()
	if not record.is_current:
		raise DesignError("CONFLICT", _("A newer revision of this design exists; open it instead"))
	if record.status not in REQUESTABLE:
		raise DesignError(
			"CONFLICT", _("This revision is {0}; it cannot be sent for review").format(record.status)
		)
	errors, warnings = count(error_count, "error_count"), count(warning_count, "warning_count")
	if errors:
		raise DesignError("INVALID", _("Fix the errors on the Check step before requesting a review"))
	priority = priority or "Normal"
	if priority not in PRIORITIES:
		raise DesignError("INVALID", _("Choose a priority of Normal, High or Rush"))
	if due_date:
		try:
			due_date = getdate(due_date)
		except Exception:
			raise DesignError("INVALID", _("Enter the due date as YYYY-MM-DD"))
		if str(due_date) < str(getdate(now_datetime())):
			raise DesignError("INVALID", _("The due date cannot be in the past"))
	note = str(note or "").strip()[:MAX_NOTE]
	values = settings()
	blocking = _server_check(record, schedule_doc, values)
	if blocking:
		raise DesignError(
			"INVALID",
			_("ilLumenate's check found errors to fix first: {0}").format(", ".join(blocking[:5])),
		)
	request = _open_request(record)
	if request is None:
		request = _new_request(record, schedule_doc, priority, due_date, note, values)
	else:
		_resubmit(request, note)
	record.db_set(
		{
			"status": "In Review",
			"review_request": request.name,
			"error_count": errors,
			"warning_count": warnings,
		}
	)
	telemetry.record("review_requested", record.fixture_schedule, record.name, {"request": request.name})
	from illumenate_lighting.illumenate_lighting.system_design.designs import design_meta

	record.reload()
	return {"request": request.name, "reviewer": _reviewer_name(request), "design_meta": design_meta(record)}


def _reviewer_name(request):
	reviewer = frappe.db.get_value(REQUEST_DOCTYPE, request.name, "technical_reviewer")
	return frappe.utils.get_fullname(reviewer) if reviewer else None


def _open_request(record):
	"""The revision's request when changes were asked for and the dealer sends it back."""
	name = record.get("review_request")
	if not name or not frappe.db.exists(REQUEST_DOCTYPE, name):
		return None
	request = frappe.get_doc(REQUEST_DOCTYPE, name)
	return request if request.status in OPEN_REQUEST else None


def _new_request(record, schedule_doc, priority, due_date, note, values):
	reviewer = assign_reviewer(values)
	request = frappe.get_doc(
		{
			"doctype": REQUEST_DOCTYPE,
			"request_type": REQUEST_TYPE,
			"status": "Draft",
			"priority": priority,
			"requested_due_date": due_date or None,
			"project": schedule_doc.get("ill_project"),
			"fixture_schedule": schedule_doc.name,
			"reference_doctype": DESIGN_DOCTYPE,
			"reference_name": record.name,
			"fixture_or_product_text": _("System design revision {0}").format(record.revision),
			"description": _description(record, schedule_doc, note),
			"owner_customer": record.get("customer") or schedule_doc.get("customer"),
			"requester_customer": record.get("customer") or schedule_doc.get("customer"),
			"requester_user": frappe.session.user,
			"created_from_portal": 1,
			"technical_reviewer": reviewer,
			"assigned_to": reviewer,
			"portal_status_group": "Pending",
		}
	)
	# The designer, not the dealer, links the schedule and names the reviewer, which the portal request
	# rules reserve for staff; submitting below runs the normal Draft → Submitted checks and SLA.
	request.flags.ignore_validate = True
	request.insert(ignore_permissions=True)
	request.reload()
	request.status = "Submitted"
	request.save(ignore_permissions=True)
	return request


def _resubmit(request, note):
	if note:
		request.add_comment("Comment", note)
	if request.status == "Waiting on Customer":
		frappe.db.set_value(REQUEST_DOCTYPE, request.name, "status", "In Progress")


# --- Comments (WP-4.3) --------------------------------------------------------------------------

COMMENT_DOCTYPE = "ilL-Child-Design-Comment"
COMMENT_VIEWS = ("Riser", "Presentation", "Plan", "3D", "Run", "Supply", "General")
MAX_COMMENT = 2000
MAX_ANCHOR = 500


def clean_anchor(value):
	"""A comment pin: ``{sheet, x, y}`` (fractions of the sheet) and/or ``{entityRef}``; ``None`` for none."""
	if value in (None, "", {}):
		return None
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			raise DesignError("INVALID", _("anchor must be valid JSON"))
	if not isinstance(value, dict):
		raise DesignError("INVALID", _("anchor must be an object"))
	anchor = {}
	for key in ("sheet", "entityRef"):
		if value.get(key) is not None:
			anchor[key] = str(value[key]).strip()[:80]
	for key in ("x", "y"):
		if value.get(key) is not None:
			number = value[key]
			if isinstance(number, bool) or not isinstance(number, (int, float)) or not 0 <= number <= 1:
				raise DesignError("INVALID", _("A pin must sit on the sheet"))
			anchor[key] = round(float(number), 4)
	if ("x" in anchor) != ("y" in anchor):
		raise DesignError("INVALID", _("A pin needs both x and y"))
	text = json.dumps(anchor, sort_keys=True, separators=(",", ":"))
	if len(text) > MAX_ANCHOR:
		raise DesignError("INVALID", _("anchor is too long"))
	return text if anchor else None


def _comment_row(row):
	return {
		"comment_id": row.comment_id,
		"view": row.view,
		"anchor": json.loads(row.anchor_json) if row.anchor_json else None,
		"body": row.body,
		"author": row.author,
		"author_name": frappe.utils.get_fullname(row.author) if row.author else None,
		"created_on": str(row.created_on),
		"resolved": bool(row.resolved),
		"resolved_by": row.resolved_by,
	}


def _may_comment(record):
	"""Applications Engineers and people who can edit the schedule talk on a design."""
	from illumenate_lighting.illumenate_lighting.portal.access import can_edit_schedule
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if allowed("design_review"):
		return True
	schedule_doc = frappe.get_doc(access.SCHEDULE_DOCTYPE, record.fixture_schedule)
	return bool(can_edit_schedule(schedule_doc))


def list_comments(design):
	record = access.require_design(design)
	return [_comment_row(row) for row in sorted(record.get("comments") or [], key=lambda row: row.idx)]


def add_comment(design, body=None, view=None, anchor=None):
	record = access.require_design(design)
	if not _may_comment(record):
		raise DesignError("FORBIDDEN", _("You can view this design but not comment on it"))
	body = str(body or "").strip()
	if not body or len(body) > MAX_COMMENT:
		raise DesignError("INVALID", _("Write a comment of up to 2000 characters"))
	view = view or "General"
	if view not in COMMENT_VIEWS:
		raise DesignError("INVALID", _("Unknown view"))
	import secrets

	row = frappe.get_doc(
		{
			"doctype": COMMENT_DOCTYPE,
			"parent": record.name,
			"parenttype": DESIGN_DOCTYPE,
			"parentfield": "comments",
			"idx": len(record.get("comments") or []) + 1,
			"comment_id": secrets.token_hex(6),
			"view": view,
			"anchor_json": clean_anchor(anchor),
			"body": body,
			"author": frappe.session.user,
			"created_on": now_datetime(),
		}
	)
	# Comments leave the design as it is, so an open editor can still save.
	row.db_insert()
	return _comment_row(row)


def resolve_comment(design, comment_id=None, resolved=1):
	record = access.require_design(design)
	if not _may_comment(record):
		raise DesignError("FORBIDDEN", _("You can view this design but not comment on it"))
	row = next((row for row in record.get("comments") or [] if row.comment_id == comment_id), None)
	if row is None:
		raise DesignError("NOT_FOUND", _("Comment not found"))
	done = str(resolved) not in ("0", "false", "False", "")
	frappe.db.set_value(
		COMMENT_DOCTYPE,
		row.name,
		{
			"resolved": int(done),
			"resolved_by": frappe.session.user if done else None,
			"resolved_on": now_datetime() if done else None,
		},
		update_modified=False,
	)
	row.update({"resolved": int(done), "resolved_by": frappe.session.user if done else None})
	return _comment_row(row)


# --- Reviewer mode: overrides and decisions (WP-4.3) ---------------------------------------------

DECISIONS = {"Approved": "APPROVED", "Changes Requested": "CHANGES_REQUESTED"}
DELIVERABLE_TYPE = "System design riser"


def _in_review(design):
	access.require_reviewer()
	record = access.require_design(design)
	frappe.db.get_value(DESIGN_DOCTYPE, record.name, "name", for_update=True)
	record.reload()
	if record.status != "In Review" or not record.is_current:
		raise DesignError("CONFLICT", _("This revision is not waiting for review"))
	return record


def add_override(overrides, code, entity_ref, reason, by, at):
	"""Pure: ``overrides`` with an Applications Engineer override of one error (replacing any earlier one)."""
	reason = str(reason or "").strip()
	if len(reason) < 3:
		raise DesignError("INVALID", _("Give a reason for the override"))
	if not code or not entity_ref:
		raise DesignError("INVALID", _("Choose the check to override"))
	kept = [
		item
		for item in overrides or []
		if not (item.get("code") == code and item.get("entityRef") == entity_ref)
	]
	kept.append(
		{
			"code": str(code)[:140],
			"entityRef": str(entity_ref)[:140],
			"kind": "staff-override",
			"reason": reason[:1000],
			"by": by,
			"at": at,
		}
	)
	return kept


def override_check(design, code=None, entity_ref=None, reason=None):
	"""An Applications Engineer accepts an error on a design in review (plan §11.5)."""
	from illumenate_lighting.illumenate_lighting.system_design.design_schema import build_hash, canonical_json

	record = _in_review(design)
	stored = json.loads(record.design_json or "{}")
	at = now_datetime().strftime("%Y-%m-%dT%H:%M:%S.000Z")
	stored["overrides"] = add_override(
		stored.get("overrides"), code, entity_ref, reason, frappe.session.user, at
	)
	record.db_set({"design_json": canonical_json(stored), "build_hash": build_hash(stored)})
	from illumenate_lighting.illumenate_lighting.system_design.designs import design_meta

	record.reload()
	return {
		"overrides": stored["overrides"],
		"build_hash": record.build_hash,
		"design_meta": design_meta(record),
	}


def _riser_pdf(record):
	"""The newest riser PDF kept on this design build, as ``(row, bytes)``."""
	rows = [
		row
		for row in record.get("deliverables") or []
		if row.kind == "Riser PDF" and row.build_hash == record.build_hash
	]
	if not rows:
		raise DesignError(
			"INVALID", _("Draw the riser on the Views step and keep its PDF on this revision first")
		)
	row = max(rows, key=lambda item: (str(item.created_on or ""), item.idx))
	name = frappe.db.get_value("File", {"file_url": row.file, "is_private": 1}, "name")
	if not name:
		raise DesignError("INVALID", _("The riser PDF is missing; export it again"))
	return row, frappe.get_doc("File", name).get_content()


def _publish(request, record, row, content):
	"""Publish the riser PDF on the request so ``drawing_review`` fingerprints this design build."""
	import hashlib

	digest = hashlib.sha256(content).hexdigest()
	published = [item for item in request.deliverables or [] if item.is_published_to_portal]
	for item in published:
		if item.published_file_sha256 == digest and item.published_build_hash == record.build_hash:
			return
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": row.file.rsplit("/", 1)[-1],
			"content": content,
			"is_private": 1,
			"attached_to_doctype": REQUEST_DOCTYPE,
			"attached_to_name": request.name,
		}
	)
	file.flags.ignore_permissions = True
	file.insert()
	request.append(
		"deliverables",
		{
			"deliverable_type": DELIVERABLE_TYPE,
			"file": file.file_url,
			"version": f"{record.revision}.{len(published) + 1}",
			"notes": _("Riser of system design {0}, revision {1}").format(record.name, record.revision),
			"is_published_to_portal": 1,
		},
	)
	request.save(ignore_permissions=True)
	request.reload()


def review_decide(design, decision=None, note=None):
	"""H6 ``review_decide``: the assigned reviewer approves the revision or asks for changes."""
	from illumenate_lighting.illumenate_lighting.portal import drawing_review
	from illumenate_lighting.illumenate_lighting.system_design.designs import design_meta

	if decision not in DECISIONS:
		raise DesignError("INVALID", _("Choose Approved or Changes Requested"))
	note = str(note or "").strip()[:MAX_NOTE]
	if decision == "Changes Requested" and not note:
		raise DesignError("INVALID", _("Describe the changes you need"))
	record = _in_review(design)
	if not record.review_request or not frappe.db.exists(REQUEST_DOCTYPE, record.review_request):
		raise DesignError("CONFLICT", _("This revision has no review request"))
	request = frappe.get_doc(REQUEST_DOCTYPE, record.review_request)
	if request.get("technical_reviewer") != frappe.session.user:
		raise DesignError("FORBIDDEN", _("Only the assigned reviewer can decide on this design"))
	row, content = _riser_pdf(record)
	_publish(request, record, row, content)
	current = drawing_review.detail(request)
	if not current or not current.get("available"):
		raise DesignError("CONFLICT", (current or {}).get("message") or _("The riser could not be published"))
	outcome = drawing_review.decide(request.name, current["revision_token"], DECISIONS[decision], note)
	approved = decision == "Approved"
	record.db_set(
		{
			"status": decision,
			"approved_review": outcome["review"] if approved else None,
			"approved_by": frappe.session.user if approved else None,
			"approved_on": now_datetime() if approved else None,
		}
	)
	request.reload()
	request.status = "Completed" if approved else "Waiting on Customer"
	if note:
		request.add_comment("Comment", note)
	request.save(ignore_permissions=True)
	telemetry.record("review_decided", record.fixture_schedule, record.name, {"decision": decision})
	record.reload()
	return {"review": outcome["review"], "status": decision, "design_meta": design_meta(record)}
