# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""The schedule page's commercial thread and guided next step (FLOW-2).

``thread`` gathers what happened after the schedule left the drawing board:
its quote requests (state, assigned staff, last customer-visible message), the
offers issued for it and the resulting order, each only when the viewer may
open it. ``progress`` turns the schedule status plus that thread into a
stepper, and ``next_step`` picks the one primary action for the current state.
"""

from urllib.parse import quote

import frappe
from frappe import _

QUOTE_REQUEST = "ilL-Quote-Request"
OFFER = "ilL-Quote-Offer"
MESSAGE = "ilL-Portal-Message"
OPEN_REQUEST_STATES = ("REQUESTED", "UNDER_REVIEW", "INFORMATION_NEEDED")
STEPS = (
	("build", "Build"),
	("ready", "Ready"),
	("quote_requested", "Quote requested"),
	("quoted", "Quoted"),
	("order_requested", "Order requested"),
	("ordered", "Ordered"),
)
STATUS_STEPS = {
	"DRAFT": "build",
	"READY": "ready",
	"QUOTED": "quoted",
	"ORDER_REQUESTED": "order_requested",
	"ISSUE": "order_requested",
	"ORDERED": "ordered",
	"CLOSED": "ordered",
}


def _link(*parts):
	return "/" + "/".join(quote(str(part), safe="") if index else part for index, part in enumerate(parts))


def _full_name(user):
	return (frappe.db.get_value("User", user, "full_name") if user else None) or user


def _last_message(request_name):
	rows = frappe.get_all(
		MESSAGE,
		filters={"reference_type": QUOTE_REQUEST, "reference_name": request_name, "visibility": "Customer"},
		fields=["body", "creation"],
		order_by="creation desc",
		limit_page_length=1,
	)
	if not rows:
		return None
	body = frappe.utils.strip_html(rows[0].body or "").strip()
	return body[:140] + ("…" if len(body) > 140 else "")


def requests_for(schedule_name):
	from illumenate_lighting.illumenate_lighting.portal.quotes import REQUEST_LABELS

	rows = frappe.get_all(
		QUOTE_REQUEST,
		filters={"schedule": schedule_name, "state": ["!=", "DRAFT"]},
		fields=["name", "state", "assigned_to", "creation"],
		order_by="creation desc",
		limit_page_length=5,
	)
	for row in rows:
		row.status_label, row.status_class = REQUEST_LABELS.get(row.state, (row.state, "secondary"))
		row.status_label = _(row.status_label)
		row.assigned_name = _full_name(row.assigned_to)
		row.last_message = _last_message(row.name)
		row.link = _link("portal", "quote-requests", row.name)
		row.is_open = row.state in OPEN_REQUEST_STATES
	return rows


def offers_for(schedule_name, user):
	from illumenate_lighting.illumenate_lighting.portal.offers import can_read, offer_status

	today = frappe.utils.nowdate()
	rows = frappe.get_all(
		OFFER,
		filters={"schedule": schedule_name},
		fields=["name", "customer", "quotation", "schedule", "state", "valid_until", "issued_on"],
		order_by="creation desc",
		limit_page_length=5,
	)
	visible = []
	for row in rows:
		if not can_read(row, user):
			continue
		label, row.status_class = offer_status(row.state, row.valid_until, today)
		row.status_label = _(label)
		row.is_open = row.state == "ISSUED" and not (row.valid_until and str(row.valid_until) < str(today))
		row.link = _link("portal", "quotes", row.name)
		visible.append(row)
	return visible


def order_for(schedule, user):
	from illumenate_lighting.illumenate_lighting.portal.orders import load_accessible_sales_order
	from illumenate_lighting.illumenate_lighting.portal.status import (
		derive_order_portal_status,
		order_status_class,
		order_status_label,
	)

	order = load_accessible_sales_order(schedule.get("sales_order"), user)
	if not order:
		return None
	key = derive_order_portal_status(
		order.docstatus, order.status, order.get("per_delivered"), order.get("per_billed")
	)
	return frappe._dict(
		name=order.name,
		link=_link("portal", "orders", order.name),
		status_label=order_status_label(key),
		status_class=order_status_class(key),
		is_request=order.docstatus == 0,
	)


def thread(schedule, user=None):
	user = user or frappe.session.user
	return frappe._dict(
		requests=requests_for(schedule.name),
		offers=offers_for(schedule.name, user),
		order=order_for(schedule, user),
	)


def current_step(status, commercial):
	step = STATUS_STEPS.get(status, "build")
	if step == "ready" and any(row.is_open for row in commercial.requests):
		return "quote_requested"
	return step


def progress(status, commercial):
	"""One entry per step with done / current / upcoming state."""
	current = current_step(status, commercial)
	keys = [key for key, _label in STEPS]
	position = keys.index(current)
	return [
		{
			"key": key,
			"label": _(label),
			"state": "done" if index < position else ("current" if index == position else "upcoming"),
			"problem": key == current and status == "ISSUE",
		}
		for index, (key, label) in enumerate(STEPS)
	]


def next_step(schedule, commercial, *, can_edit, can_create_order, unconfigured):
	"""The page's one primary action, plus an optional secondary one.

	Each action is a dict with ``label`` and either ``href`` (a link) or
	``action`` (a page function), and ``disabled_reason`` when it cannot run yet.
	"""
	status = schedule.status
	locked = bool(schedule.get("is_locked"))
	open_request = next((row for row in commercial.requests if row.is_open), None)
	open_offer = next((row for row in commercial.offers if row.is_open), None)
	primary = secondary = None
	if status == "DRAFT" and can_edit and not locked:
		primary = {"label": _("Mark ready"), "action": "ready"}
		if unconfigured:
			primary["disabled_reason"] = _("Configure these lines first: {0}").format(", ".join(unconfigured))
	elif status == "READY":
		if open_request:
			primary = {"label": _("View quote request"), "href": open_request.link}
		elif can_edit and not locked:
			primary = {"label": _("Request quote"), "action": "quote"}
		if can_create_order:
			secondary = {"label": _("Order directly"), "action": "order"}
	elif status == "QUOTED" and open_offer:
		primary = {"label": _("Review quote"), "href": open_offer.link}
	elif status in ("ORDER_REQUESTED", "ORDERED", "ISSUE") and commercial.order:
		primary = {"label": _("View order"), "href": commercial.order.link}
	return {"primary": primary, "secondary": secondary}


def unconfigured_lines(lines):
	"""(label, anchor key) for each line still waiting on its configuration."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		is_unconfigured,
	)

	return [
		(
			line.get("line_id") or _("Row {0}").format(line.get("idx")),
			line.get("line_key") or line.get("name"),
		)
		for line in lines or []
		if is_unconfigured(line)
	]
