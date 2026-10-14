# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""What needs the signed-in dealer's attention, for the portal overview (FLOW-1).

``for_user`` returns one ordered list of action items. Each item carries a
title, a line of context, an optional due date with a readable label, a deep
link and a tone. Sources run in this order: offers awaiting a response, order
requests waiting on the buyer, drawings to approve or answer, other requests
and tickets waiting on the customer, draft schedules with lines to configure,
and invitations the user sent that nobody accepted yet.

Staff accounts see only what is theirs personally (drawings they review,
invitations they sent, schedules they own); everything company-scoped belongs
to dealers.
"""

from urllib.parse import quote

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.access import get_actor

OFFER = "ilL-Quote-Offer"
INTAKE_ACTIONS = {
	"INFORMATION_NEEDED": "Answer questions on order request {0}",
	"CHANGES_PROPOSED": "Review proposed changes to order request {0}",
}
SCHEDULE = "ilL-Project-Fixture-Schedule"
SCHEDULE_LINE = "ilL-Child-Fixture-Schedule-Line"
LINE_FIELDS = [
	"parent",
	"manufacturer_type",
	"product_type",
	"configured_group",
	"variant_selections",
	"configured_tape_neon",
	"configured_led_sheet",
	"configured_fixture",
	"driver_template",
	"accessory_item",
]
PER_SOURCE = 10
LIMIT = 25


def _path(*parts):
	return "/" + "/".join(quote(str(part), safe="") if index else part for index, part in enumerate(parts))


def item(kind, title, link, context=None, due=None, due_label=None, tone="warning"):
	return {
		"kind": kind,
		"title": title,
		"context": context,
		"due": str(due) if due else None,
		"due_label": due_label,
		"link": link,
		"tone": tone,
	}


def days_until(value, today):
	return frappe.utils.date_diff(frappe.utils.getdate(value), frappe.utils.getdate(today))


def expiry_label(value, today):
	"""A readable expiry: Expires today, Expires tomorrow, Expires in N days or Expired."""
	days = days_until(value, today)
	if days < 0:
		return _("Expired")
	if days == 0:
		return _("Expires today")
	if days == 1:
		return _("Expires tomorrow")
	return _("Expires in {0} days").format(days)


def offers(actor, today):
	"""Issued offers still open for a response, soonest expiry first."""
	if actor.is_internal or not (actor.is_dealer and actor.customer):
		return []
	from illumenate_lighting.illumenate_lighting.portal.offers import can_read

	rows = frappe.get_all(
		OFFER,
		filters={"customer": actor.customer, "state": "ISSUED", "valid_until": [">=", today]},
		fields=["name", "customer", "quotation", "schedule", "valid_until"],
		order_by="valid_until asc, name asc",
		limit_page_length=PER_SOURCE,
	)
	rows = [row for row in rows if can_read(row, actor.user)]
	names = (
		{
			row.name: row.schedule_name
			for row in frappe.get_all(
				SCHEDULE,
				filters={"name": ["in", [row.schedule for row in rows]]},
				fields=["name", "schedule_name"],
			)
		}
		if rows
		else {}
	)
	return [
		item(
			"offer",
			_("Respond to quote {0}").format(row.name),
			_path("portal", "quotes", row.name),
			context=names.get(row.schedule) or row.schedule,
			due=row.valid_until,
			due_label=expiry_label(row.valid_until, today) if row.valid_until else None,
			tone="danger" if row.valid_until and days_until(row.valid_until, today) <= 2 else "warning",
		)
		for row in rows
	]


def orders(actor, order_rows):
	"""Order requests whose next step is the buyer's, from the /portal/orders read model."""
	if actor.is_internal:
		return []
	items = []
	for order in order_rows or []:
		state = order.get("intake_state")
		if state not in INTAKE_ACTIONS and not order.get("needs_action"):
			continue
		title = _(INTAKE_ACTIONS.get(state, "Confirm order request {0}")).format(order.name)
		items.append(
			item(
				"order",
				title,
				_path("portal", "orders", order.name),
				context=order.get("po_no") and _("PO {0}").format(order.po_no),
			)
		)
	return items[:PER_SOURCE]


def drawings(actor):
	"""Drawings this user must approve, and drawing requests waiting on the customer."""
	fields = ["name", "request_type", "fixture_or_product_text", "sla_deadline"]
	review = frappe.get_list(
		"ilL-Document-Request",
		filters={
			"hide_from_portal": 0,
			"technical_reviewer": actor.user,
			"ill_review_state": "Awaiting approval",
		},
		fields=fields,
		order_by="modified desc",
		limit_page_length=PER_SOURCE,
	)
	items = [
		item(
			"drawing",
			_("Approve drawing {0}").format(row.name),
			_path("portal", "drawings", row.name),
			context=row.fixture_or_product_text or row.request_type,
		)
		for row in review
	]
	if actor.is_internal:
		return items
	seen = {row.name for row in review}
	waiting = frappe.get_list(
		"ilL-Document-Request",
		filters={"hide_from_portal": 0, "status": "Waiting on Customer"},
		fields=fields,
		order_by="modified desc",
		limit_page_length=PER_SOURCE,
	)
	items += [
		item(
			"drawing",
			_("Answer questions on drawing request {0}").format(row.name),
			_path("portal", "drawings", row.name),
			context=row.fixture_or_product_text or row.request_type,
		)
		for row in waiting
		if row.name not in seen
	]
	return items[:PER_SOURCE]


def waiting_on_customer(actor):
	"""Support tickets, quote requests, order changes and verifications whose next step is the customer's."""
	if actor.is_internal:
		return []
	from illumenate_lighting.illumenate_lighting.portal.support import _conditions

	conditions, params = _conditions(actor.user)
	where = " AND ".join(
		[*conditions, "ill_next_action_by = 'Customer'", "status not in ('Closed', 'Resolved')"]
	)
	tickets = frappe.db.sql(
		f"select name, subject from `tabIssue` where {where} order by modified desc limit {PER_SOURCE}",
		params,
		as_dict=True,
	)
	items = [
		item(
			"support",
			_("Reply to support ticket {0}").format(row.name),
			_path("portal", "support", row.name),
			context=row.subject,
		)
		for row in tickets
	]
	for row in frappe.get_list(
		"ilL-Quote-Request",
		filters={"state": "INFORMATION_NEEDED"},
		fields=["name", "schedule", "due_date"],
		order_by="modified desc",
		limit_page_length=PER_SOURCE,
	):
		items.append(
			item(
				"quote_request",
				_("Answer questions on quote request {0}").format(row.name),
				_path("portal", "quote-requests", row.name),
				context=row.schedule,
			)
		)
	for row in frappe.get_list(
		"ilL-Order-Change",
		filters={"state": "INFORMATION_NEEDED"},
		fields=["name", "sales_order", "request_type"],
		order_by="modified desc",
		limit_page_length=PER_SOURCE,
	):
		items.append(
			item(
				"order_change",
				_("Answer questions on {0} request {1}").format(
					_(str(row.request_type or "change").lower()), row.name
				),
				_path("portal", "orders", row.sales_order),
				context=row.sales_order,
			)
		)
	for row in frappe.get_list(
		"ilL-Product-Verification-Request",
		filters={"state": "INFORMATION_NEEDED"},
		fields=["name", "product_title"],
		order_by="modified desc",
		limit_page_length=PER_SOURCE,
	):
		items.append(
			item(
				"verification",
				_("Answer questions on product verification {0}").format(row.name),
				_path("portal", "product-verification", row.name),
				context=row.product_title,
			)
		)
	return items


def schedules(actor):
	"""Draft schedules with ilLumenate lines that still need configuring."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		is_unconfigured,
	)

	filters = {"status": "DRAFT", "is_locked": 0}
	if actor.is_internal:
		filters["owner"] = actor.user
	rows = frappe.get_list(
		SCHEDULE,
		filters=filters,
		fields=["name", "schedule_name", "ill_project"],
		order_by="modified desc",
		limit_page_length=50,
	)
	if not rows:
		return []
	pending = {}
	for line in frappe.get_all(
		SCHEDULE_LINE,
		filters={"parenttype": SCHEDULE, "parent": ["in", [row.name for row in rows]]},
		fields=LINE_FIELDS,
	):
		if is_unconfigured(line):
			pending[line.parent] = pending.get(line.parent, 0) + 1
	items = []
	for row in rows:
		count = pending.get(row.name)
		if not count:
			continue
		title = (_("Configure 1 line in {0}") if count == 1 else _("Configure {1} lines in {0}")).format(
			row.schedule_name or row.name, count
		)
		items.append(item("schedule", title, _path("portal", "schedules", row.name), tone="info"))
	return items[:PER_SOURCE]


def invitations(actor, today):
	"""Invitations this user sent that are still pending."""
	rows = frappe.get_all(
		"ilL-Portal-Invitation",
		filters={"invited_by": actor.user, "state": "Pending"},
		fields=["name", "email", "project", "expires_on"],
		order_by="expires_on asc",
		limit_page_length=PER_SOURCE,
	)
	items = []
	for row in rows:
		expired = row.expires_on and days_until(row.expires_on, today) < 0
		link = _path("portal", "projects", row.project, "collaborators") if row.project else "/portal/account"
		items.append(
			item(
				"invitation",
				_("{0} has not accepted your invitation").format(row.email),
				link,
				context=_("Resend it from the invitations list") if expired else None,
				due=row.expires_on,
				due_label=expiry_label(row.expires_on, today) if row.expires_on else None,
				tone="danger" if expired else "info",
			)
		)
	return items


def _safely(source, *args):
	"""One failing source must not take the whole overview down."""
	try:
		return source(*args)
	except Exception:
		frappe.log_error(
			title=f"Portal action center: {source.__name__} failed",
			message=frappe.get_traceback(),
			defer_insert=True,
		)
		return []


def for_user(user=None, order_rows=None):
	"""Ordered action items for the overview; ``order_rows`` reuses an already loaded orders list."""
	actor = get_actor(user)
	if actor.is_guest:
		return []
	today = frappe.utils.nowdate()
	items = []
	items += _safely(offers, actor, today)
	items += _safely(orders, actor, order_rows)
	items += _safely(drawings, actor)
	items += _safely(waiting_on_customer, actor)
	items += _safely(schedules, actor)
	items += _safely(invitations, actor, today)
	return items[:LIMIT]


def greeting(now=None):
	hour = (now or frappe.utils.now_datetime()).hour
	if hour < 12:
		return _("Good morning")
	if hour < 18:
		return _("Good afternoon")
	return _("Good evening")
