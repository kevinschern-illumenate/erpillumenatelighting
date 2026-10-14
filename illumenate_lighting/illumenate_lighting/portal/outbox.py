"""Durable event/recipient ledger. Queue creation never performs SMTP I/O."""

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint

EVENT = "ilL-Portal-Event"
DELIVERY = "ilL-Portal-Delivery"
TERMINAL = ("SUPPRESSED", "SKIPPED", "DELIVERED")
INVITATION = "ilL-Portal-Invitation"
INVITATION_PREFERENCE = "invitation"


def reference_access(event, user):
	doctype, name = event.reference_type, event.reference_name
	if not frappe.db.exists(doctype, name):
		return False
	doc = frappe.get_doc(doctype, name)
	if doctype == "ilL-Portal-Message":
		from illumenate_lighting.illumenate_lighting.portal.conversations import has_permission, is_staff

		if doc.visibility != "Customer" or not has_permission(doc, "read", user):
			return False
		parent = frappe.get_doc(doc.reference_type, doc.reference_name)
		if is_staff(parent, doc.actor):
			return user in (parent.get("requester_user"), parent.get("raised_by"), parent.get("requested_by"))
		return user in (parent.get("assigned_to"), parent.get("ill_support_owner")) and is_staff(parent, user)
	if doctype in ("ilL-Order-Change", "ilL-Order-Intake"):
		from illumenate_lighting.illumenate_lighting.portal.files import _context_access

		return user == doc.requested_by and _context_access(doctype, name, "read", user)
	if doctype in ("ilL-Document-Request", "Issue", "ilL-Project-Fixture-Schedule"):
		from illumenate_lighting.illumenate_lighting.portal.files import _context_access

		return _context_access(doctype, name, "read", user)
	if doctype == "ilL-Quote-Offer":
		from illumenate_lighting.illumenate_lighting.portal.offers import can_read

		return can_read(doc, user)
	if doctype == "ilL-Quote-Request":
		from illumenate_lighting.illumenate_lighting.portal.quotes import has_permission

		return has_permission(doc, "read", user)
	if doctype in ("Sales Order", "Delivery Note"):
		from illumenate_lighting.illumenate_lighting.portal.notifications import order_recipients
		from illumenate_lighting.illumenate_lighting.portal.orders import load_accessible_sales_order

		orders = (
			{name}
			if doctype == "Sales Order"
			else {row.against_sales_order for row in doc.items if row.against_sales_order}
		)
		return (
			bool(orders)
			and all(load_accessible_sales_order(order, user) for order in orders)
			and any(user in order_recipients(frappe.get_doc("Sales Order", order)) for order in orders)
		)
	return False


def address(delivery):
	"""The account, or for an invitee without one, the bare email the message goes to."""
	return delivery.recipient or delivery.get("recipient_email")


def invitation_eligibility(event, email):
	"""Invitations are transactional: no preference gate, but only while still usable."""
	invite = frappe.db.get_value(
		INVITATION, event.reference_name, ["state", "email", "expires_on"], as_dict=True
	)
	if not invite or invite.state != "Pending":
		return "SKIPPED", "Invitation was used, revoked or replaced"
	if frappe.utils.get_datetime(invite.expires_on) <= frappe.utils.now_datetime():
		return "SKIPPED", "Invitation expired"
	if str(email or "").strip().lower() != str(invite.email or "").lower():
		return "SKIPPED", "Recipient is not the invited email"
	return "PENDING", "Awaiting Email Queue"


def eligibility(event, recipient):
	from illumenate_lighting.illumenate_lighting.portal.notifications import (
		PREFERENCE_DEFAULTS,
		wants_notification,
	)

	if event.preference == INVITATION_PREFERENCE and event.reference_type == INVITATION:
		return invitation_eligibility(event, recipient)
	if (
		not recipient
		or recipient in ("Guest", "Administrator")
		or not frappe.db.get_value("User", recipient, "enabled")
	):
		return "SKIPPED", "Recipient account is unavailable"
	if event.preference not in PREFERENCE_DEFAULTS:
		return "SKIPPED", "Unknown notification preference"
	if not wants_notification(recipient, event.preference):
		return "SUPPRESSED", "Recipient preference is disabled"
	if not reference_access(event, recipient):
		return "SKIPPED", "Recipient no longer has access to this event"
	return "PENDING", "Awaiting Email Queue"


def _ensure_event(preference, subject, message, reference_type, reference_name, revision):
	key = fingerprint(
		{
			"kind": preference,
			"reference": [reference_type, reference_name],
			"revision": None if revision is None else str(revision),
			"subject": subject,
			"message": message,
		}
	)
	event = frappe.get_doc(
		{
			"doctype": EVENT,
			"event_key": key,
			"reference_type": reference_type,
			"reference_name": reference_name,
			"preference": preference,
			"subject": subject,
			"message": message,
		}
	)
	event.flags.notification_service_write = True
	event.insert(ignore_permissions=True, ignore_if_duplicate=True)
	return key, event


def _ensure_delivery(key, event, recipient, user=None, email=None):
	delivery_key = fingerprint({"event": key, "recipient": recipient})
	if frappe.db.exists(DELIVERY, delivery_key):
		return frappe.db.get_value(DELIVERY, delivery_key, "state") not in ("SUPPRESSED", "SKIPPED")
	state, detail = eligibility(event, recipient)
	delivery = frappe.get_doc(
		{
			"doctype": DELIVERY,
			"delivery_key": delivery_key,
			"event": key,
			"recipient": user,
			"recipient_email": email,
			"state": state,
			"detail": detail,
		}
	)
	delivery.flags.notification_service_write = True
	delivery.insert(ignore_permissions=True, ignore_if_duplicate=True)
	return state == "PENDING"


def record(user, preference, subject, message, reference_type, reference_name, event_key=None):
	"""Commit intent alongside the business record, independent of email setup."""
	if not user or not reference_type or not reference_name:
		return False
	# `modified` comes back as a datetime, which the canonical JSON fingerprint rejects.
	revision = event_key or frappe.db.get_value(reference_type, reference_name, "modified")
	key, event = _ensure_event(preference, subject, message, reference_type, reference_name, revision)
	return _ensure_delivery(key, event, user, user=user)


def record_invitation(invitation, email, subject, message, event_key):
	"""Queue an invitation email to an address that may not have an account yet."""
	email = str(email or "").strip().lower()
	if not invitation or not email:
		return False
	key, event = _ensure_event(INVITATION_PREFERENCE, subject, message, INVITATION, invitation, event_key)
	user = email if frappe.db.exists("User", email) else None
	return _ensure_delivery(key, event, email, user=user, email=email)


def _state(delivery, state, detail, **values):
	frappe.db.set_value(DELIVERY, delivery.name, {"state": state, "detail": detail, **values})
	delivery.state = state


def reconcile(delivery):
	if not delivery.email_queue or delivery.state in TERMINAL:
		return
	if not frappe.db.exists("Email Queue", delivery.email_queue):
		_state(
			delivery, "FAILED", "Email Queue record is missing. Inspect before retrying; delivery is unknown."
		)
		return
	queue = frappe.get_doc("Email Queue", delivery.email_queue)
	recipient = next((row for row in queue.recipients if row.recipient == address(delivery)), None)
	if recipient and recipient.status == "Sent":
		_state(
			delivery,
			"DELIVERED",
			"Accepted by SMTP; inbox delivery is not verified",
			sent_on=frappe.utils.now(),
		)
	elif queue.status == "Error":
		_state(delivery, "FAILED", "Email Queue failed; use its native retry after correcting email setup")
	else:
		_state(delivery, "QUEUED", "Waiting for native Email Queue delivery")


def dispatch_one(name):
	frappe.db.sql("select name from `tabilL-Portal-Delivery` where name=%s for update", name)
	delivery = frappe.get_doc(DELIVERY, name)
	if delivery.state in TERMINAL:
		return
	if delivery.email_queue:
		reconcile(delivery)
		return
	event = frappe.get_doc(EVENT, delivery.event)
	state, detail = eligibility(event, address(delivery))
	if state != "PENDING":
		_state(delivery, state, detail)
		return
	frappe.db.savepoint("portal_email_queue")
	try:
		queue = frappe.sendmail(
			recipients=[address(delivery)],
			subject=event.subject,
			message=event.message,
			reference_doctype=DELIVERY,
			reference_name=delivery.name,
			delayed=True,
			now=False,
			queue_separately=False,
			add_unsubscribe_link=False,
		)
		if not queue or not queue.name:
			raise ValueError("Email Queue did not create a record")
		_state(
			delivery,
			"QUEUED",
			"Waiting for native Email Queue delivery",
			email_queue=queue.name,
			attempts=int(delivery.attempts or 0) + 1,
		)
	except Exception:
		frappe.db.rollback(save_point="portal_email_queue")
		_state(
			delivery,
			"FAILED",
			"Could not create Email Queue. Correct email setup, then retry.",
			attempts=int(delivery.attempts or 0) + 1,
		)
		frappe.log_error(title="Portal notification queue failed", message=frappe.get_traceback())


def dispatch():
	# Bounded polling also recovers process termination before queue creation.
	for name in frappe.get_all(
		DELIVERY,
		filters={"state": ["in", ["PENDING", "QUEUED"]]},
		pluck="name",
		order_by="modified asc",
		limit_page_length=100,
	):
		dispatch_one(name)
		frappe.db.commit()


@frappe.whitelist(methods=["POST"])
def retry(name):
	from illumenate_lighting.illumenate_lighting.portal.staff import require

	# Only integration staff may queue retries. A linked SMTP attempt is never
	# duplicated: its retry belongs to native Email Queue with existing evidence.
	require("integration")
	frappe.db.sql("select name from `tabilL-Portal-Delivery` where name=%s for update", name)
	delivery = frappe.get_doc(DELIVERY, name)
	if delivery.email_queue:
		frappe.throw("Inspect and retry the existing Email Queue record; no replacement will be created")
	if delivery.state != "FAILED":
		frappe.throw("Only failed queue creation can be retried here")
	_state(delivery, "PENDING", "Staff requested retry")
	return {"success": True}


def before_send(queue):
	"""Recheck preferences/access immediately before native SMTP, including retries."""
	if queue.reference_doctype != DELIVERY:
		return True
	if not frappe.db.exists(DELIVERY, queue.reference_name):
		queue.db_set({"status": "Error", "error": "Portal delivery ledger is missing"})
		return False
	delivery = frappe.get_doc(DELIVERY, queue.reference_name)
	if delivery.state == "DELIVERED":
		return False
	event = frappe.get_doc(EVENT, delivery.event)
	state, detail = eligibility(event, address(delivery))
	if delivery.state in ("SUPPRESSED", "SKIPPED") or state != "PENDING":
		queue.db_set({"status": "Error", "error": "Portal notification suppressed: " + detail})
		_state(delivery, state if state != "PENDING" else delivery.state, detail)
		frappe.db.commit()
		return False
	_state(delivery, "QUEUED", "Native Email Queue is attempting delivery")
	return True
