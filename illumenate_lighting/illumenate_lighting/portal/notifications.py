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


def notify_order_review(order, request):
	labels = {"APPROVED": "Order approved", "INFORMATION_NEEDED": "Order information requested",
		"CHANGES_PROPOSED": "Order revision ready for review", "REJECTED": "Order request needs correction",
		"WITHDRAWN": "Order request withdrawn", "SUBMITTED": "Order request received"}
	label = labels.get(request.state)
	if not label:
		return
	for user in order_recipients(order):
		notify_user(user, "notify_orders", f"{label}: {order.name}",
			f"<p>{label}.</p>" + _portal_link(f"/portal/orders/{order.name}", _("Review order")),
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

	name = frappe.utils.escape_html(schedule.schedule_name or schedule.name)
	link = _portal_link(f"/portal/schedules/{schedule.name}", _("View schedule"))

	if new_status == "QUOTED":
		preference = "notify_quotes"
		subject = _("Quote ready: {0}").format(name)
		body = _("<p>A quote is ready for your fixture schedule <strong>{0}</strong>.</p>").format(name)
	elif new_status == "ORDERED":
		preference = "notify_orders"
		subject = _("Order approved: {0}").format(name)
		body = _(
			"<p>Your order request for <strong>{0}</strong> has been approved and is now in progress.</p>"
		).format(name)
		if sales_order:
			link += _portal_link(f"/portal/orders/{sales_order}", _("View order"))
	elif new_status == "ISSUE":
		preference = "notify_orders"
		subject = _("Action needed on your order request: {0}").format(name)
		body = _(
			"<p>We were unable to complete the order request for <strong>{0}</strong>. "
			"Please reach out to <a href=\"mailto:sales@illumenate.lighting\">sales@illumenate.lighting</a> "
			"for more information if we have not already been in contact with you.</p>"
		).format(name)
	else:
		return

	for user in recipients:
		notify_user(
			user,
			preference,
			subject,
			body + link,
			reference_doctype=schedule.doctype,
			reference_name=schedule.name,
		)


def notify_shipment(delivery_note):
	"""Shipping update for every Sales Order the Delivery Note fulfils."""
	order_names = {i.against_sales_order for i in delivery_note.items if i.against_sales_order}
	if not order_names:
		return
	carrier = delivery_note.get("transporter_name")
	tracking = delivery_note.get("vehicle_no")
	detail = ""
	if carrier:
		detail += _("<p><strong>Carrier:</strong> {0}</p>").format(frappe.utils.escape_html(carrier))
	if tracking:
		detail += _("<p><strong>Tracking number:</strong> {0}</p>").format(frappe.utils.escape_html(tracking))

	for order_name in order_names:
		order = frappe.get_doc("Sales Order", order_name)
		returned = bool(delivery_note.get("is_return"))
		for recipient in order_recipients(order):
			notify_user(recipient, "notify_shipping",
				_("Return recorded for order {0}" if returned else "Shipment recorded for order {0}").format(order_name),
				_("<p>A return was recorded.</p>" if returned else "<p>A shipment was recorded.</p>")
				+ detail + _portal_link(f"/portal/orders/{order_name}", _("View fulfillment")),
				reference_doctype="Delivery Note", reference_name=delivery_note.name,
				event_key=f"{delivery_note.name}:{order_name}")


def on_delivery_note_submit(doc, method=None):
	notify_shipment(doc)
