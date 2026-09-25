"""Durable quote intake, separate from issuance of a commercial offer."""

import json

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json, fingerprint
from illumenate_lighting.illumenate_lighting.portal.access import can_edit_schedule, can_read_schedule

REQUEST_DOCTYPE = "ilL-Quote-Request"
LINE_FIELDS = (
	"name",
	"line_key",
	"line_id",
	"location",
	"qty",
	"notes",
	"manufacturer_type",
	"product_type",
	"fixture_template",
	"configured_group",
	"configured_fixture",
	"configured_tape_neon",
	"configured_led_sheet",
	"accessory_item",
	"manufacturer_name",
	"fixture_model_number",
	"spec_sheet",
	"trim_info",
	"housing_model_number",
	"driver_model_number",
	"lamp_info",
	"dimming_protocol",
	"input_voltage",
	"other_finish",
)


def _snapshot(schedule):
	from illumenate_lighting.illumenate_lighting.portal.line_documents import active

	return {
		"schema_version": 1,
		"schedule": schedule.name,
		"project": schedule.ill_project,
		"customer": schedule.customer,
		"lines": [
			{
				**{key: line.get(key) for key in LINE_FIELDS},
				"documents": active(schedule.name, line),
				"sellable": line.manufacturer_type != "OTHER",
			}
			for line in schedule.lines
		],
	}


@frappe.whitelist(methods=["POST"])
@atomic_build
def request_quote(
	schedule_name,
	idempotency_key=None,
	expected_modified=None,
	notes=None,
	contact=None,
	requested_date=None,
	file_ids=None,
):
	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)
	if not can_edit_schedule(schedule):
		frappe.throw(_("You cannot request a quote for this schedule"), frappe.PermissionError)
	frappe.db.sql(
		"select name from `tabilL-Project-Fixture-Schedule` where name=%s for update", schedule_name
	)
	schedule.reload()
	if not can_edit_schedule(schedule):
		frappe.throw(_("You cannot request a quote for this schedule"), frappe.PermissionError)
	snapshot = _snapshot(schedule)
	snapshot["notes"] = (notes or "").strip()
	if len(snapshot["notes"]) > 4000 or len(contact or "") > 240:
		frappe.throw("Use up to 4,000 characters for notes and 240 for contact instructions")
	files = json.loads(file_ids) if isinstance(file_ids, str) else (file_ids or [])
	if not isinstance(files, list) or len(files) > 10 or any(not isinstance(value, str) for value in files):
		frappe.throw("Choose at most 10 uploaded reference files")
	snapshot["contact"] = (contact or "").strip()
	snapshot["requested_date"] = str(frappe.utils.getdate(requested_date)) if requested_date else None
	if snapshot["requested_date"] and snapshot["requested_date"] < frappe.utils.nowdate():
		frappe.throw("Requested timing cannot be in the past")
	snapshot["files"] = sorted(set(files))
	request_hash = fingerprint(snapshot)
	key = fingerprint(
		{"schedule": schedule.name, "actor": frappe.session.user, "key": idempotency_key or request_hash}
	)
	existing = frappe.db.get_value(
		REQUEST_DOCTYPE, {"idempotency_key": key}, ["name", "request_hash", "state"], as_dict=True
	)
	if existing:
		if existing.request_hash != request_hash:
			frappe.throw(_("This request key was already used with different content."))
		return {
			"success": True,
			"request_name": existing.name,
			"state": existing.state,
			"already_existed": True,
		}
	if expected_modified and str(schedule.modified) != str(expected_modified):
		frappe.throw(_("The schedule changed. Reload and review before requesting a quote."))
	if schedule.is_locked or schedule.status not in ("DRAFT", "READY"):
		frappe.throw(_("Use an editable DRAFT or READY schedule to request a quote."))
	if not schedule.lines:
		frappe.throw(_("Add at least one line before requesting a quote."))
	from illumenate_lighting.illumenate_lighting.portal.offers import commercial_customer

	request = frappe.get_doc(
		{
			"doctype": REQUEST_DOCTYPE,
			"schedule": schedule.name,
			"project": schedule.ill_project,
			"customer": commercial_customer(schedule),
			"requested_by": frappe.session.user,
			"state": "REQUESTED",
			"request_snapshot": canonical_json(snapshot),
			"request_hash": request_hash,
			"idempotency_key": key,
			"notes": snapshot["notes"],
		}
	).insert(ignore_permissions=True)
	from illumenate_lighting.illumenate_lighting.portal.files import finalize_files

	finalize_files(files, REQUEST_DOCTYPE, request.name, allow_unbound=True)
	schedule.add_comment("Info", _("Quote request received: {0}").format(request.name))
	return {"success": True, "request_name": request.name, "state": request.state, "already_existed": False}


def detail(name):
	from illumenate_lighting.illumenate_lighting.portal.files import list_files

	doc = frappe.get_doc(REQUEST_DOCTYPE, name)
	if not has_permission(doc):
		frappe.throw("Quote request unavailable", frappe.PermissionError)
	return {
		"name": doc.name,
		"schedule": doc.schedule,
		"state": doc.state,
		"requested_by": doc.requested_by,
		"due_date": doc.due_date,
		"snapshot": json.loads(doc.request_snapshot),
		"files": list_files(REQUEST_DOCTYPE, doc.name),
	}


def list_requests(page=1, page_size=20):
	from illumenate_lighting.illumenate_lighting.portal.conversations import _pagination

	page, page_size = _pagination(page, page_size)
	# Use the same scoped predicate as native lists without requiring website users to enter Desk.
	condition = get_permission_query_conditions()
	return frappe.db.sql(
		f"""select name, schedule, state, creation from `tabilL-Quote-Request`
		where {condition or "1=1"} order by creation desc, name desc limit %s offset %s""",
		(page_size + 1, (page - 1) * page_size),
		as_dict=True,
	)


def has_permission(doc, ptype="read", user=None):
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	user = user or frappe.session.user
	if user == "Guest" or not frappe.db.get_value("User", user, "enabled"):
		return False
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return True
	if allowed("sales", user):
		return ptype in ("read", "select", "print", "report", "write")
	if ptype not in ("read", "select", "print"):
		return False
	return can_read_schedule(frappe.get_doc("ilL-Project-Fixture-Schedule", doc.schedule), user)


def get_permission_query_conditions(user=None):
	from illumenate_lighting.illumenate_lighting.portal.access import schedule_query_conditions
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if allowed("sales", user):
		return ""
	condition = schedule_query_conditions(user)
	return f"`tabilL-Quote-Request`.schedule in (select name from `tabilL-Project-Fixture-Schedule` where {condition or '1=1'})"
