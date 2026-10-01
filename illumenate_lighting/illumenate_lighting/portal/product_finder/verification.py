"""Server-derived verification requests, line state, and commercial gates."""

from datetime import timedelta

import frappe
from frappe.utils import get_datetime, now_datetime

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	canonical_json,
	fingerprint,
	string_list,
)
from illumenate_lighting.illumenate_lighting.portal.product_finder import sessions

DOCTYPE = "ilL-Product-Verification-Request"
OPEN = ("REQUESTED", "UNDER_REVIEW", "INFORMATION_NEEDED")
FINAL = ("VERIFIED", "NOT_FEASIBLE", "CANCELLED")
FIELDS = ("verification_status", "verification_reasons", "verification_request", "finder_session")
TRANSITIONS = {
	"REQUESTED": {"UNDER_REVIEW", "INFORMATION_NEEDED", "CANCELLED"},
	"UNDER_REVIEW": {"INFORMATION_NEEDED", "VERIFIED", "NOT_FEASIBLE", "CANCELLED"},
	"INFORMATION_NEEDED": {"UNDER_REVIEW", "VERIFIED", "NOT_FEASIBLE", "CANCELLED"},
	"VERIFIED": {"CANCELLED"},
	"NOT_FEASIBLE": {"CANCELLED"},
	"CANCELLED": set(),
}


def staff(user=None):
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	return allowed("sales", user) or allowed("engineering", user) or allowed("finder", user)


def can_access(doc, ptype="read", user=None):
	from illumenate_lighting.illumenate_lighting.portal.access import schedule_permission

	user = user or frappe.session.user
	if user == "Guest":
		return False
	if staff(user):
		return True
	readable = doc.requested_by == user or (
		doc.schedule
		and schedule_permission(frappe.get_doc("ilL-Project-Fixture-Schedule", doc.schedule), "read", user)
	)
	return bool(readable and (ptype in ("read", "select") or (ptype == "write" and doc.state in OPEN)))


def has_permission(doc, user=None, permission_type=None, ptype=None):
	kind = permission_type or ptype or "read"
	return can_access(doc, kind, user) if kind in ("read", "select") else staff(user)


def get_permission_query_conditions(user=None):
	from illumenate_lighting.illumenate_lighting.portal.access import schedule_permission

	user = user or frappe.session.user
	if user == "Guest":
		return "1=0"
	if staff(user):
		return ""
	names = [
		r.name
		for r in frappe.get_all("ilL-Project-Fixture-Schedule", fields=["*"])
		if schedule_permission(r, "read", user)
	]
	condition = f"`tab{DOCTYPE}`.requested_by = {frappe.db.escape(user)}"
	if names:
		condition += f" OR `tab{DOCTYPE}`.schedule IN (" + ",".join(frappe.db.escape(n) for n in names) + ")"
	return "(" + condition + ")"


def due_date():
	day = get_datetime(now_datetime()).date()
	remaining = 2
	while remaining:
		day += timedelta(days=1)
		if day.weekday() < 5:
			remaining -= 1
	return day


def reasons_for(product_name, answers):
	from illumenate_lighting.illumenate_lighting.portal.product_finder import (
		engine,
		facts,
		matcher,
		server_definition,
	)

	definition = server_definition.load()
	product = next((p for p in facts.load() if p["name"] == product_name), None)
	if product is None:
		frappe.throw("This product is unavailable. Choose a current catalog product.")
	needed = matcher.requirements(definition, engine.prune(definition, answers))
	return matcher.inspect_product(product, needed)[1]


def _reason_key(reasons):
	return canonical_json(sorted((r["question"], canonical_json(r["answer"]), r["reason"]) for r in reasons))


def _message(doc, text, event):
	if not text:
		return
	key = fingerprint({"verification": doc.name, "event": event})
	if frappe.db.exists("ilL-Portal-Message", {"request_key": key}):
		return
	message = frappe.get_doc(
		{
			"doctype": "ilL-Portal-Message",
			"reference_type": DOCTYPE,
			"reference_name": doc.name,
			"actor": frappe.session.user,
			"body": text,
			"visibility": "Customer",
			"action": "REPLY",
			"request_key": key,
			"request_hash": fingerprint(text),
		}
	)
	message.flags.conversation_service_write = True
	message.insert(ignore_permissions=True)


def _open_request(product_name, session, reasons, schedule=None, line_key=None, message=None):
	filters = {
		"product": product_name,
		"finder_session": session.name,
		"schedule": schedule.name if schedule else ["is", "not set"],
		"state": ["in", OPEN],
	}
	name = frappe.db.get_value(DOCTYPE, filters, "name")
	if name:
		doc = frappe.get_doc(DOCTYPE, name, for_update=True)
	else:
		product = frappe.get_doc("ilL-Webflow-Product", product_name)
		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"state": "REQUESTED",
				"product": product_name,
				"product_title": product.product_name,
				"family": product.product_type,
				"finder_session": session.name,
				"schedule": schedule.name if schedule else None,
				"project": schedule.ill_project if schedule else None,
				"customer": schedule.customer if schedule else None,
				"requested_by": frappe.session.user,
				"due_date": due_date(),
				"message": message,
			}
		)
	doc.reasons = canonical_json(reasons)
	doc.answers_snapshot = session.quiz_answers
	keys = string_list(doc.get("line_keys") or [], field="line_keys")
	if line_key and line_key not in keys:
		keys.append(line_key)
	doc.line_keys = canonical_json(keys)
	doc.save(ignore_permissions=True)
	if message:
		_message(doc, message, fingerprint(message))
	if not name:
		_notify_staff(doc)
	return doc


def apply_to_line(schedule, line, product_name, finder_token):
	for field in FIELDS:
		line.set(field, None)
	if not finder_token:
		return
	session = sessions.get_owned(finder_token, for_update=True)
	line.finder_session = session.name
	reasons = reasons_for(product_name, sessions.decoded(session.quiz_answers))
	if not reasons:
		return
	line.verification_reasons = canonical_json(reasons)
	verified = frappe.get_all(
		DOCTYPE,
		filters={"product": product_name, "finder_session": session.name, "state": "VERIFIED"},
		fields=["name", "reasons"],
	)
	previous = next(
		(r for r in verified if _reason_key(sessions.decoded(r.reasons)) == _reason_key(reasons)), None
	)
	if previous:
		line.verification_status, line.verification_request = "Verified", previous.name
	else:
		doc = _open_request(product_name, session, reasons, schedule, line.get("line_key") or line.name)
		line.verification_status, line.verification_request = "Pending", doc.name


def request(token, product_slug=None, schedule=None, line_key=None, message=None):
	from illumenate_lighting.illumenate_lighting.portal.configuration import resolve_line, schedule_context

	session = sessions.get_owned(token, for_update=True)
	if message and (not isinstance(message, str) or len(message) > 4000):
		frappe.throw("Use at most 4,000 characters for your message")
	if not product_slug:
		# No product is known in the empty-results flow: create an honest support inquiry,
		# rather than associating a verification decision with an arbitrary product.
		issue = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": "Help finding a product",
				"raised_by": frappe.session.user,
				"description": frappe.utils.escape_html(
					(message or "Please help find a product for these answers.")
					+ "\n"
					+ canonical_json(sessions.decoded(session.quiz_answers))
				),
			}
		)
		issue.insert(ignore_permissions=True)
		return issue.name
	product = frappe.db.get_value(
		"ilL-Webflow-Product", {"product_slug": product_slug, "is_active": 1}, "name"
	)
	if not product:
		frappe.throw("Product unavailable")
	target = schedule_context(schedule, write=True, lock=True) if schedule else None
	if target and line_key:
		resolve_line(target, line_key)
	reasons = reasons_for(product, sessions.decoded(session.quiz_answers))
	doc = _open_request(product, session, reasons, target, line_key, message)
	return doc.name


def _notify_staff(doc):
	from illumenate_lighting.illumenate_lighting.portal.notifications import notify_user
	from illumenate_lighting.illumenate_lighting.portal.product_finder.content import SETTINGS

	role = frappe.db.get_single_value(SETTINGS, "verification_assignee_role") or "ilL Sales Review"
	for user in frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent"):
		if staff(user):
			notify_user(
				user,
				"notify_quotes",
				"Product verification requested",
				"A product verification request is ready for review.",
				DOCTYPE,
				doc.name,
				event_key=f"pvr:{doc.name}:requested:{user}",
			)


def propagate(request_doc):
	status = {"VERIFIED": "Verified", "NOT_FEASIBLE": "Not Feasible", "CANCELLED": None}.get(
		request_doc.state
	)
	parents = frappe.get_all(
		"ilL-Child-Fixture-Schedule-Line",
		filters={"verification_request": request_doc.name, "parenttype": "ilL-Project-Fixture-Schedule"},
		pluck="parent",
	)
	for name in set(parents):
		schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", name, for_update=True)
		for line in schedule.lines:
			if line.get("verification_request") == request_doc.name:
				line.verification_status = status
				values = {"verification_status": status}
				if request_doc.state == "CANCELLED":
					line.verification_request = line.verification_reasons = None
					values.update(verification_request=None, verification_reasons=None)
				frappe.db.set_value("ilL-Child-Fixture-Schedule-Line", line.name, values)
		# Like system lifecycle updates, only decision metadata changes. Full save would
		# reject locked versions or require the reviewer to own each configured build.
		frappe.db.set_value("ilL-Project-Fixture-Schedule", name, "modified", now_datetime())
		schedule.add_comment("Comment", f"Product verification {request_doc.name}: {request_doc.state}")
	from illumenate_lighting.illumenate_lighting.portal.notifications import notify_user

	notify_user(
		request_doc.requested_by,
		"notify_quotes",
		"Product verification updated",
		f"Your product verification is now {request_doc.state.replace('_', ' ').lower()}.",
		DOCTYPE,
		request_doc.name,
		event_key=f"pvr:{request_doc.name}:{request_doc.state}",
	)
	_message(
		request_doc, request_doc.resolution or "This verification request was cancelled.", request_doc.state
	)


def cancel_orphans(schedule, method=None):
	for row in frappe.get_all(
		DOCTYPE, filters={"schedule": schedule.name, "state": ["in", OPEN]}, fields=["name", "line_keys"]
	):
		linked = set(string_list(row.line_keys or [], field="line_keys"))
		keys = {
			r.get("line_key") or r.name for r in schedule.lines if r.get("verification_request") == row.name
		}
		if linked and not linked & keys:
			doc = frappe.get_doc(DOCTYPE, row.name)
			doc.state = "CANCELLED"
			doc.flags.finder_service_write = True
			doc.save(ignore_permissions=True)


def gate(schedule, stage):
	from illumenate_lighting.illumenate_lighting.portal.product_finder.content import SETTINGS

	if stage not in ("issue_quote", "order"):
		raise ValueError("Unknown verification stage")
	pending = [
		str(r.line_id or r.idx)
		for r in schedule.lines
		if r.get("verification_status") in ("Pending", "Not Feasible")
	]
	if not pending:
		return
	setting = (
		frappe.db.get_single_value(SETTINGS, "verification_gate")
		or "Before quote is issued and order is placed"
	)
	message = (
		"Verify or remove the lines that need verification before "
		+ ("issuing a quote" if stage == "issue_quote" else "placing an order")
		+ ": "
		+ ", ".join(pending)
	)
	if setting == "Warning only" or (setting == "Before order only" and stage == "issue_quote"):
		frappe.msgprint(message)
	else:
		frappe.throw(message, frappe.ValidationError)


def product_name(family, template=None, product_slug=None):
	from illumenate_lighting.illumenate_lighting.api.product_projection import (
		TEMPLATE_DOCTYPES,
		TEMPLATE_FIELDS,
	)

	if product_slug:
		row = frappe.db.get_value(
			"ilL-Webflow-Product",
			{"product_slug": product_slug, "is_active": 1},
			["name", TEMPLATE_FIELDS[family]],
			as_dict=True,
		)
		if not row or (template and row.get(TEMPLATE_FIELDS[family]) != template):
			frappe.throw("The selected product does not match this template")
		return row.name
	return frappe.db.get_value(TEMPLATE_DOCTYPES[family], template, "webflow_product")
