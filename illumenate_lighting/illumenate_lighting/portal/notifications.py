# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Portal notifications.

Email is the only supported channel. Every customer-facing email goes through
:func:`notify_user`, which consults the user's ``ilL-Portal-User-Settings``
so the toggles on /portal/account actually gate what is sent.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.routes import portal_path

# Preference field on ilL-Portal-User-Settings -> default when no settings row.
PREFERENCE_DEFAULTS = {
	"notify_orders": True,
	"notify_quotes": True,
	"notify_drawings": True,
	"notify_shipping": True,
	"notify_marketing": False,
}

SYSTEM_USERS = ("Administrator", "Guest")


def wants_notification(user, preference):
	"""True when ``user`` should receive emails gated by ``preference``."""
	if not user or user in SYSTEM_USERS or preference not in PREFERENCE_DEFAULTS:
		return False
	if not frappe.db.exists("User", user) or not frappe.db.get_value("User", user, "enabled"):
		return False
	value = frappe.db.get_value("ilL-Portal-User-Settings", {"user": user}, preference)
	if value is None:
		return PREFERENCE_DEFAULTS[preference]
	return bool(int(value))


def notify_user(user, preference, subject, message, reference_doctype=None, reference_name=None, event_key=None):
	"""Record a preference-gated intent; email configuration and SMTP run later."""
	from illumenate_lighting.illumenate_lighting.portal.outbox import record

	return record(user, preference, subject, message, reference_doctype, reference_name, event_key)


def _portal_link(path, label):
	url = frappe.utils.get_url(path)
	return f'<p><a href="{url}">{frappe.utils.escape_html(label)}</a></p>'


def _schedule_label(order):
	"""The job name a buyer recognizes for an order: its fixture schedule's name, if any."""
	schedule = order.get("ill_fixture_schedule")
	if not schedule:
		return None
	return frappe.db.get_value("ilL-Project-Fixture-Schedule", schedule, "schedule_name") or None


def order_recipients(order):
	"""Use recorded buyers/purchasing contact; never assume the staff owner buys."""
	from illumenate_lighting.illumenate_lighting.portal.access import get_actor
	from illumenate_lighting.illumenate_lighting.portal.orders import load_accessible_sales_order

	candidates = {order.owner}
	intake = frappe.db.get_value("ilL-Order-Intake", {"sales_order": order.name},
		["requested_by", "acknowledged_by"], as_dict=True)
	if intake:
		candidates.update([intake.requested_by, intake.acknowledged_by])
	if order.get("contact_person"):
		from illumenate_lighting.illumenate_lighting.portal.accounts import require_owned

		contact = frappe.get_doc("Contact", order.contact_person)
		try:
			require_owned(contact, order.customer)
		except (frappe.PermissionError, frappe.ValidationError):
			pass
		else:
			candidates.add(contact.get("user"))
	return {user for user in candidates if user and get_actor(user).is_company_dealer_for(order.customer)
		and load_accessible_sales_order(order.name, user)}


# Subject label and email heading for each order review state.
ORDER_REVIEW_COPY = {
	"APPROVED": ("Order approved", "Your order is approved",
		"We approved order <strong>{0}</strong> and it's moving into production."),
	"INFORMATION_NEEDED": ("Order information requested", "We need a few details",
		"Before we can approve order <strong>{0}</strong>, we need a little more information."),
	"CHANGES_PROPOSED": ("Order revision ready for review", "Your revised order is ready",
		"We proposed changes to order <strong>{0}</strong>. Review them and approve or reply."),
	"REJECTED": ("Order request needs correction", "Your order request needs a correction",
		"We couldn't approve order <strong>{0}</strong> as submitted."),
	"WITHDRAWN": ("Order request withdrawn", "Your order request was withdrawn",
		"Order request <strong>{0}</strong> was withdrawn."),
	"SUBMITTED": ("Order request received", "We received your order request",
		"Thanks for order request <strong>{0}</strong>. We'll review it and let you know."),
}


def notify_order_review(order, request):
	from illumenate_lighting.illumenate_lighting.email_templates import brand

	copy = ORDER_REVIEW_COPY.get(request.state)
	if not copy:
		return
	label, title, intro = copy
	escape = frappe.utils.escape_html
	message = request.get("customer_message") if request.state != "APPROVED" else None
	note = (
		f'Note from our team:<br><span style="white-space: pre-wrap">{escape(message)}</span>' if message else None
	)
	body = brand.portal_email(
		title,
		paragraphs=[intro.format(escape(order.name)), note],
		action=(_("Review the order"), frappe.utils.get_url(portal_path("order", order.name))),
		preference_note=_("order updates"),
	)
	for user in order_recipients(order):
		notify_user(user, "notify_orders", f"{label}: {order.name}", body,
			reference_doctype="Sales Order", reference_name=order.name,
			event_key=f"{request.name}:{request.state}:{request.modified}")


# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


def notify_schedule_status(schedule, new_status, sales_order=None):
	"""Order / quote lifecycle emails for a fixture schedule."""
	recipients = {schedule.owner}
	if sales_order:
		recipients = order_recipients(frappe.get_doc("Sales Order", sales_order))
	if new_status == "ORDERED":
		# The immutable approval event owns this notification, avoiding a second
		# send from schedule bookkeeping with a different reference/idempotency key.
		return
	recipients.discard(frappe.session.user)

	from illumenate_lighting.illumenate_lighting.email_templates import brand

	name = frappe.utils.escape_html(schedule.schedule_name or schedule.name)
	schedule_url = frappe.utils.get_url(portal_path("schedule", schedule.name))

	if new_status == "QUOTED":
		preference = "notify_quotes"
		subject = _("Quote ready: {0}").format(name)
		body = brand.portal_email(
			_("Your quote is ready"),
			paragraphs=[_(
				"We priced your fixture schedule <strong>{0}</strong>. Review the quote to accept it "
				"or ask for changes."
			).format(name)],
			action=(_("Review the quote"), schedule_url),
			preference_note=_("quote updates"),
		)
	elif new_status == "ORDERED":
		preference = "notify_orders"
		subject = _("Order approved: {0}").format(name)
		body = brand.portal_email(
			_("Your order is approved"),
			paragraphs=[_(
				"Your order request for <strong>{0}</strong> is approved and in progress."
			).format(name)],
			action=(_("View the order"), frappe.utils.get_url(portal_path("order", sales_order)))
			if sales_order else (_("View the schedule"), schedule_url),
			preference_note=_("order updates"),
		)
	elif new_status == "ISSUE":
		preference = "notify_orders"
		subject = _("Action needed on your order request: {0}").format(name)
		from illumenate_lighting.illumenate_lighting.portal.status import SALES_EMAIL

		body = brand.portal_email(
			_("Your order request needs attention"),
			paragraphs=[_(
				"We couldn't complete the order request for <strong>{0}</strong>. If we haven't been "
				'in touch yet, email <a href="mailto:{1}">{1}</a> and we\'ll sort it out with you.'
			).format(name, SALES_EMAIL)],
			action=(_("View the schedule"), schedule_url),
			preference_note=_("order updates"),
		)
	else:
		return

	for user in recipients:
		notify_user(
			user,
			preference,
			subject,
			body,
			reference_doctype=schedule.doctype,
			reference_name=schedule.name,
		)


def notify_shipment(delivery_note):
	"""Shipping update for every Sales Order the Delivery Note fulfils."""
	order_names = {i.against_sales_order for i in delivery_note.items if i.against_sales_order}
	if not order_names:
		return
	from illumenate_lighting.illumenate_lighting.email_templates import brand
	from illumenate_lighting.illumenate_lighting.portal.shipment_tracking import tracking

	shipment = tracking(delivery_note)
	escape = frappe.utils.escape_html
	returned = bool(delivery_note.get("is_return"))
	number = _tracking_links(shipment, brand) or None
	posted = frappe.utils.format_date(delivery_note.get("posting_date")) if delivery_note.get("posting_date") else None

	for order_name in order_names:
		order = frappe.get_doc("Sales Order", order_name)
		order_url = frappe.utils.get_url(portal_path("order", order_name))
		job = _schedule_label(order)
		named = f"<strong>{escape(job)}</strong> ({escape(order_name)})" if job else f"<strong>{escape(order_name)}</strong>"
		if returned:
			title = _("We received your return")
			intro = _("We recorded a return against your order {0}.").format(named)
		elif (order.get("per_delivered") or 0) >= 100:
			title = _("Your order is on the way")
			intro = _("Your order {0} has shipped.").format(named)
		else:
			title = _("Part of your order is on the way")
			intro = _("Part of your order {0} has shipped. We'll email you when the rest goes out.").format(named)
		details = [
			(_("Your PO"), escape(order.get("po_no")) if order.get("po_no") else None),
			(_("Carrier"), escape(shipment["carrier"]) if shipment["carrier"] else None),
			(_("Tracking"), number),
			(_("Returned") if returned else _("Shipped"), escape(posted) if posted else None),
		]
		if shipment["url"] and not returned:
			action, secondary = (_("Track shipment"), shipment["url"]), (_("View the order"), order_url)
		else:
			action, secondary = (_("View the order"), order_url), None
		body = brand.portal_email(
			title, paragraphs=[intro], details=details, action=action, secondary=secondary,
			preference_note=_("shipping updates"),
		)
		for recipient in order_recipients(order):
			notify_user(recipient, "notify_shipping",
				_("Return received for order {0}" if returned else "Your order has shipped: {0}").format(order_name),
				body,
				reference_doctype="Delivery Note", reference_name=delivery_note.name,
				event_key=f"{delivery_note.name}:{order_name}")


def _tracking_links(shipment, brand):
	"""Every tracking number, linked where the carrier has a tracking page, one per line."""
	escape = frappe.utils.escape_html
	links = []
	for package in shipment.get("packages") or []:
		if not package.get("number"):
			continue
		number = escape(package["number"])
		if package.get("url"):
			number = f'<a href="{escape(package["url"])}" style="color: {brand.COLORS["blue"]}">{number}</a>'
		links.append(number)
	return "<br>".join(links)


def notify_delivered(delivery_note, shipment_name=None):
	"""Delivered email for every Sales Order the Delivery Note fulfils (EasyPost tracker event)."""
	order_names = {i.against_sales_order for i in delivery_note.items if i.against_sales_order}
	if not order_names or delivery_note.get("is_return"):
		return
	from illumenate_lighting.illumenate_lighting.email_templates import brand
	from illumenate_lighting.illumenate_lighting.portal.shipment_tracking import tracking

	shipment = tracking(delivery_note)
	escape = frappe.utils.escape_html
	for order_name in order_names:
		order = frappe.get_doc("Sales Order", order_name)
		order_url = frappe.utils.get_url(portal_path("order", order_name))
		job = _schedule_label(order)
		named = f"<strong>{escape(job)}</strong> ({escape(order_name)})" if job else f"<strong>{escape(order_name)}</strong>"
		details = [
			(_("Your PO"), escape(order.get("po_no")) if order.get("po_no") else None),
			(_("Carrier"), escape(shipment["carrier"]) if shipment["carrier"] else None),
			(_("Tracking"), _tracking_links(shipment, brand) or None),
		]
		body = brand.portal_email(
			_("Your shipment was delivered"),
			paragraphs=[_("The carrier reports a shipment for your order {0} as delivered.").format(named)],
			details=details,
			action=(_("View the order"), order_url),
			preference_note=_("shipping updates"),
		)
		for recipient in order_recipients(order):
			notify_user(recipient, "notify_shipping",
				_("Delivered: {0}").format(order_name),
				body,
				reference_doctype="Delivery Note", reference_name=delivery_note.name,
				event_key=f"{shipment_name or delivery_note.name}:{order_name}:delivered")


def on_delivery_note_submit(doc, method=None):
	notify_shipment(doc)
