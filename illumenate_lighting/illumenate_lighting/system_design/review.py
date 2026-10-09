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
