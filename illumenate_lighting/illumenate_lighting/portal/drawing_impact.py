"""Drawing impact tracks physical scope, not price or commercial terms."""

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint

LINE_FIELDS = (
	"line_key",
	"line_id",
	"location",
	"qty",
	"uom",
	"conversion_factor",
	"item_code",
	"configured_fixture",
	"configured_tape_neon",
	"configured_led_sheet",
	"configured_group",
	"ill_configured_fixture",
	"ill_configured_tape_neon",
	"ill_configured_led_sheet",
	"ill_configured_group",
	"ill_bom",
	"ill_fixture_type",
	"ill_section_label",
)


def build_hash(doc):
	rows = doc.get("lines") if doc.doctype == "ilL-Project-Fixture-Schedule" else doc.get("items")
	return fingerprint(
		{"schema_version": 1, "lines": [{key: row.get(key) for key in LINE_FIELDS} for row in rows or []]}
	)


def request_build_hash(request):
	if request.get("sales_order"):
		return build_hash(frappe.get_doc("Sales Order", request.sales_order))
	if request.get("fixture_schedule"):
		return build_hash(frappe.get_doc("ilL-Project-Fixture-Schedule", request.fixture_schedule))
	return fingerprint(None)


def order_matches_schedule(order, schedule):
	"""A schedule-only approval covers unchanged, traceable commercial scope.

	Exploded historical/kit rows need an explicit order-linked drawing review;
	we cannot infer a single configured assembly from arbitrary components.
	"""
	lines = {row.name: row for row in schedule.get("lines") or []}
	links = ("configured_group", "configured_fixture", "configured_tape_neon", "configured_led_sheet")
	expected = {
		name
		for name, line in lines.items()
		if any(line.get(field) for field in links) or line.get("manufacturer_type") == "ACCESSORY"
	}
	seen = set()
	for row in order.get("items") or []:
		key = row.get("ill_schedule_line_id")
		line = lines.get(key)
		if not line or key in seen or float(row.qty or 0) != float(line.qty or 0):
			return False
		seen.add(key)
		if row.get("conversion_factor") not in (None, 0, 1):
			return False
		if (row.get("ill_fixture_type") or "") != (line.get("line_id") or "") or (
			row.get("ill_section_label") or ""
		) != (line.get("location") or ""):
			return False
		if any(row.get("ill_" + field) != line.get(field) for field in links):
			return False
		if not any(line.get(field) for field in links):
			if line.get("manufacturer_type") != "ACCESSORY" or row.item_code != line.get("accessory_item"):
				return False
		else:
			# Resolve immutable build pointers, not the Item's current default BOM.
			for field, doctype in (
				("configured_group", "ilL-Configured-Group"),
				("configured_fixture", "ilL-Configured-Fixture"),
				("configured_tape_neon", "ilL-Configured-Tape-Neon"),
				("configured_led_sheet", "ilL-Configured-LED-Sheet"),
			):
				if line.get(field):
					build = frappe.get_doc(doctype, line.get(field))
					if row.item_code != build.get("configured_item") or row.get("ill_bom") != build.get(
						"bom"
					):
						return False
	return bool(seen) and seen == expected


def _task(request, current_hash):
	key = fingerprint({"request": request.name, "build": current_hash})
	existing = frappe.db.get_value("Task", {"ill_drawing_impact_key": key}, "name")
	if existing:
		return existing
	request_type = frappe.get_doc("ilL-Request-Type", request.request_type)
	task = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": f"Drawing reapproval: {request.name}",
			"description": "The physical build changed. Review the new dimensions, materials and feeds, publish a revised drawing, and obtain a new named-reviewer decision before manufacturing release.",
			"project": request_type.task_project,
			"status": "Open",
			"ill_drawing_request": request.name,
			"ill_drawing_impact_key": key,
			"exp_end_date": str(request.sla_deadline)[:10] if request.sla_deadline else None,
		}
	).insert(ignore_permissions=True)
	if request.assigned_to:
		frappe.get_doc(
			{
				"doctype": "ToDo",
				"reference_type": "Task",
				"reference_name": task.name,
				"allocated_to": request.assigned_to,
				"assigned_by": frappe.session.user,
				"description": task.subject,
				"status": "Open",
				"date": task.exp_end_date,
			}
		).insert(ignore_permissions=True)
	return task.name


def refresh_request(request, *, material_change=False):
	"""Persist queue state; a failed preview does not release production."""
	from illumenate_lighting.illumenate_lighting.portal.drawing_review import _current

	frappe.db.sql("select name from `tabilL-Document-Request` where name=%s for update", request.name)
	current = request_build_hash(request)
	previous = request.get("ill_observed_build_hash")
	values = {"ill_observed_build_hash": current}
	if previous and previous != current and material_change:
		values["ill_impact_task"] = _task(request, current)
		values["ill_review_state"] = "Reapproval required"
		values["ill_next_action_by"] = "Staff"
	else:
		try:
			revision, checksum, current = _current(request)
		except frappe.ValidationError:
			values["ill_review_state"] = "Awaiting drawing"
		else:
			token = fingerprint(
				{"request": request.name, "revision": revision.name, "file": checksum, "build": current}
			)
			decision = frappe.db.get_value(
				"ilL-Drawing-Review",
				{"request": request.name, "revision_token": token, "reviewed_by": request.technical_reviewer},
				"decision",
			)
			values["ill_review_state"] = {
				"APPROVED": "Approved",
				"CHANGES_REQUESTED": "Changes requested",
			}.get(
				decision,
				"Reapproval required"
				if request.get("ill_review_state") == "Reapproval required"
				else "Awaiting approval",
			)
			if decision:
				values["ill_next_action_by"] = "None" if decision == "APPROVED" else "Staff"
	frappe.db.set_value(request.doctype, request.name, values, update_modified=False)


def on_build_update(doc, method=None):
	old = doc.get_doc_before_save()
	if not old or build_hash(old) == build_hash(doc):
		return
	field = "sales_order" if doc.doctype == "Sales Order" else "fixture_schedule"
	filters = {field: doc.name}
	if field == "sales_order" and doc.get("ill_fixture_schedule"):
		query = {"or_filters": {"sales_order": doc.name, "fixture_schedule": doc.ill_fixture_schedule}}
	else:
		query = {"filters": filters}
	for name in frappe.get_all("ilL-Document-Request", **query, pluck="name"):
		request = frappe.get_doc("ilL-Document-Request", name)
		if field == "sales_order" and not request.sales_order:
			frappe.db.set_value(
				request.doctype,
				request.name,
				{
					"ill_impact_task": _task(request, build_hash(doc)),
					"ill_review_state": "Reapproval required",
					"ill_next_action_by": "Staff",
				},
				update_modified=False,
			)
			continue
		if field == "fixture_schedule" and request.sales_order:
			continue
		if not request.get("ill_observed_build_hash"):
			request.ill_observed_build_hash = build_hash(old)
		refresh_request(request, material_change=True)
