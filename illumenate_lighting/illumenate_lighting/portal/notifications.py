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


def notify_user(user, preference, subject, message, reference_doctype=None, reference_name=None):
	"""Send one preference-gated email. Never raises: notification failures
	must not roll back the business transaction that triggered them."""
	if not wants_notification(user, preference):
		return False
	try:
		frappe.sendmail(
			recipients=[user],
			subject=subject,
			message=message,
			reference_doctype=reference_doctype,
			reference_name=reference_name,
			delayed=True,
		)
		return True
	except Exception:
		frappe.log_error(
			title=f"Portal notification failed ({preference}) for {user}",
			message=frappe.get_traceback(),
		)
		return False


def _portal_link(path, label):
	url = frappe.utils.get_url(path)
	return f'<p><a href="{url}">{frappe.utils.escape_html(label)}</a></p>'


# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


def notify_schedule_status(schedule, new_status, sales_order=None):
	"""Order / quote lifecycle emails for a fixture schedule."""
	recipients = {schedule.owner}
	if sales_order:
		so_owner = frappe.db.get_value("Sales Order", sales_order, "owner")
		if so_owner:
			recipients.add(so_owner)
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
		owner = frappe.db.get_value("Sales Order", order_name, "owner")
		if not owner:
			continue
		notify_user(
			owner,
			"notify_shipping",
			_("Shipment on its way for order {0}").format(order_name),
			_("<p>Items from your order <strong>{0}</strong> have shipped.</p>").format(order_name)
			+ detail
			+ _portal_link(f"/portal/orders/{order_name}", _("Track your order")),
			reference_doctype="Delivery Note",
			reference_name=delivery_note.name,
		)


def on_delivery_note_submit(doc, method=None):
	notify_shipment(doc)
