"""Revision-specific technical decisions, checked separately at production release."""

import hashlib

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint
from illumenate_lighting.illumenate_lighting.doctype.ill_document_request.ill_document_request import (
	has_permission,
)


def _current(request):
	published = [row for row in request.deliverables or [] if row.is_published_to_portal]
	if not published:
		frappe.throw("No published drawing revision is available")
	revision = max(published, key=lambda row: (str(row.published_on or ""), row.idx))
	file_name = frappe.db.get_value("File", {"file_url": revision.file, "is_private": 1}, "name")
	if not file_name:
		frappe.throw("Drawing review requires a private registered file")
	file = frappe.get_doc("File", file_name)
	if file.attached_to_doctype != request.doctype or file.attached_to_name != request.name:
		frappe.throw("Drawing revision must belong to this request")
	sha256 = hashlib.sha256(file.get_content()).hexdigest()
	from illumenate_lighting.illumenate_lighting.portal.drawing_impact import request_build_hash

	current_hash = request_build_hash(request)
	if not revision.get("published_build_hash") or revision.published_build_hash != current_hash:
		frappe.throw(
			"The drawing predates this physical build. Engineering must publish a new revision before review."
		)
	if revision.get("published_file_sha256") != sha256:
		frappe.throw("Published drawing bytes changed. Engineering must publish a new revision.")
	return revision, sha256, current_hash


def detail(request):
	if not has_permission(request, "read", frappe.session.user):
		return None
	try:
		revision, checksum, build_hash = _current(request)
	except frappe.ValidationError:
		return {"available": False, "message": "A published private drawing is required before review."}
	token = fingerprint(
		{"request": request.name, "revision": revision.name, "file": checksum, "build": build_hash}
	)
	decision = frappe.db.get_value(
		"ilL-Drawing-Review",
		{"request": request.name, "revision_token": token},
		["name", "decision", "reviewed_by", "reviewed_on", "note"],
		as_dict=True,
	)
	return {
		"available": True,
		"revision": revision.name,
		"version": revision.version,
		"revision_token": token,
		"decision": decision,
		"can_review": request.get("technical_reviewer") == frappe.session.user and not decision,
	}


@frappe.whitelist(methods=["POST"])
def decide(request_name, revision_token, decision, note=None):
	request = frappe.get_doc("ilL-Document-Request", request_name)
	if (
		not has_permission(request, "read", frappe.session.user)
		or request.get("technical_reviewer") != frappe.session.user
	):
		frappe.throw("Only the named reviewer with current project access may decide", frappe.PermissionError)
	frappe.db.sql("select name from `tabilL-Document-Request` where name=%s for update", request_name)
	request.reload()
	if (
		not has_permission(request, "read", frappe.session.user)
		or request.technical_reviewer != frappe.session.user
	):
		frappe.throw("Drawing review access was revoked", frappe.PermissionError)
	current = detail(request)
	if not current or not current.get("available") or current["revision_token"] != revision_token:
		frappe.throw("The drawing or build changed. Reload the latest revision.")
	if decision not in ("APPROVED", "CHANGES_REQUESTED") or (
		decision == "CHANGES_REQUESTED" and not (note or "").strip()
	):
		frappe.throw("Choose a decision and describe any required changes")
	if current.get("decision"):
		if (
			current["decision"].decision != decision
			or (current["decision"].note or "") != (note or "").strip()
		):
			frappe.throw("A decision already exists for this revision; staff must publish a new revision")
		return {"success": True, "review": current["decision"].name, "already_existed": True}
	revision, checksum, build_hash = _current(request)
	review = frappe.get_doc(
		{
			"doctype": "ilL-Drawing-Review",
			"request": request.name,
			"revision": revision.name,
			"revision_token": revision_token,
			"file_sha256": checksum,
			"build_hash": build_hash,
			"decision": decision,
			"reviewed_by": frappe.session.user,
			"reviewed_on": frappe.utils.now(),
			"note": (note or "").strip(),
		}
	).insert(ignore_permissions=True)
	from illumenate_lighting.illumenate_lighting.portal.drawing_impact import refresh_request

	refresh_request(request)
	return {"success": True, "review": review.name}


def before_work_order_submit(work_order, method=None):
	"""A pending drawing never blocks SO approval; it blocks WO release here."""
	if not work_order.sales_order:
		return
	if not frappe.has_permission("Work Order", "submit", doc=work_order):
		frappe.throw("Manufacturing release permission required", frappe.PermissionError)
	schedule = frappe.db.get_value("Sales Order", work_order.sales_order, "ill_fixture_schedule")
	requests = frappe.get_all(
		"ilL-Document-Request",
		filters={"required_for_manufacturing": 1},
		or_filters={"sales_order": work_order.sales_order, "fixture_schedule": schedule}
		if schedule
		else {"sales_order": work_order.sales_order},
		pluck="name",
	)
	for name in requests:
		request = frappe.get_doc("ilL-Document-Request", name)
		if request.sales_order and request.sales_order != work_order.sales_order:
			frappe.throw(
				f"Drawing request {name} belongs to another order revision; Engineering must review this order"
			)
		if not request.sales_order and request.fixture_schedule:
			from illumenate_lighting.illumenate_lighting.portal.drawing_impact import order_matches_schedule

			if not order_matches_schedule(
				frappe.get_doc("Sales Order", work_order.sales_order),
				frappe.get_doc("ilL-Project-Fixture-Schedule", request.fixture_schedule),
			):
				frappe.throw(
					f"Manufacturing is on hold: {name} covers the schedule. Link a drawing review to this changed order and obtain approval."
				)
		revision, checksum, build_hash = _current(request)
		token = fingerprint(
			{"request": name, "revision": revision.name, "file": checksum, "build": build_hash}
		)
		approved = frappe.db.exists(
			"ilL-Drawing-Review",
			{
				"request": name,
				"revision_token": token,
				"decision": "APPROVED",
				"reviewed_by": request.technical_reviewer,
			},
		)
		if not approved:
			frappe.throw(
				f"Manufacturing is on hold: drawing request {name} requires approval of its current revision"
			)
