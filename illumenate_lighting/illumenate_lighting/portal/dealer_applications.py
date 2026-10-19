# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Dealer applications from the public dealer-access page (FLOW-5).

Visitors and signed-in users without a company apply on one form. Each
application becomes an ilL-Account-Request of type "Dealer application" and
rings the accounts team (DESK-1). Guests are anonymous, so their request has
no ``requested_by``: nobody but staff can read it, and staff approve it by
inviting the applicant to the company they set up.

The endpoint is open to guests, so it is rate limited and carries a honeypot
field that people never see; a filled honeypot gets the normal success reply
and creates nothing.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

INTAKE = "ilL-Account-Request"
REQUEST_TYPE = "Dealer application"
OPEN_STATES = ("Pending", "Information needed")
# field: (label, required, max length)
FIELDS = {
	"company": ("Company", True, 140),
	"full_name": ("Your name", True, 140),
	"email": ("Email", True, 140),
	"phone": ("Phone", False, 40),
	"website": ("Website", False, 240),
	"territory": ("Territory", False, 140),
	"message": ("Message", False, 4000),
}


def clean(values):
	"""(data, errors): trimmed application fields, and a message per invalid field."""
	data, errors = {}, {}
	for field, (label, required, limit) in FIELDS.items():
		value = str(values.get(field) or "").strip()
		if required and not value:
			errors[field] = _("{0} is required.").format(_(label))
		elif len(value) > limit:
			errors[field] = _("{0} is limited to {1} characters.").format(_(label), limit)
		if value:
			data[field] = value
	email = data.get("email")
	if email and "email" not in errors:
		if not frappe.utils.validate_email_address(email):
			errors["email"] = _("Enter a valid email address.")
		else:
			data["email"] = email.lower()
	return data, errors


def open_application(user=None):
	"""The signed-in user's pending dealer application, if any."""
	user = user or frappe.session.user
	if user == "Guest":
		return None
	rows = frappe.get_all(
		INTAKE,
		filters={"requested_by": user, "request_type": REQUEST_TYPE, "state": ["in", list(OPEN_STATES)]},
		fields=["name", "state", "creation"],
		order_by="creation desc",
		limit=1,
	)
	return rows[0] if rows else None


def prefill(user=None):
	"""What the form can fill in for a signed-in user: name, email, phone and company."""
	user = user or frappe.session.user
	if user == "Guest":
		return {}
	values = (
		frappe.db.get_value("User", user, ["full_name", "email", "mobile_no", "phone"], as_dict=True) or {}
	)
	result = {
		"full_name": values.get("full_name") or "",
		"email": values.get("email") or user,
		"phone": values.get("mobile_no") or values.get("phone") or "",
	}
	from illumenate_lighting.illumenate_lighting.portal.access import get_actor

	customer = get_actor(user).customer
	if customer:
		result["company"] = frappe.db.get_value("Customer", customer, "customer_name") or customer
	return result


def page_state(user=None):
	"""Which panel the dealer-access page shows: apply, pending or approved."""
	user = user or frappe.session.user
	if user == "Guest":
		return {"state": "apply", "is_guest": True, "prefill": {}, "application": None}
	from illumenate_lighting.illumenate_lighting.portal.access import can_view_catalog

	if can_view_catalog(user):
		return {"state": "approved", "is_guest": False, "prefill": {}, "application": None}
	application = open_application(user)
	if application:
		return {"state": "pending", "is_guest": False, "prefill": {}, "application": application}
	return {"state": "apply", "is_guest": False, "prefill": prefill(user), "application": None}


def _staff_note(data, guest):
	lines = [f"{_(FIELDS[field][0])}: {data[field]}" for field in FIELDS if data.get(field)]
	if guest:
		lines.append(
			_(
				"The applicant has no portal account. To approve, set up the company and send them a company invitation."
			)
		)
	return "\n".join(lines)


def notify(doc, data, guest):
	"""Assign the application in the accounts queue and ring the team (DESK-1)."""
	from illumenate_lighting.illumenate_lighting.portal import staff_notifications

	def work():
		staff_notifications.assign(doc, "accounts")
		applicant = _("{0} at {1}").format(data["full_name"], data["company"])
		subject = _("New dealer application {0} from {1}").format(doc.name, applicant)
		summary = _("{0} applied for dealer access in the portal.").format(applicant)
		message = staff_notifications.body(doc, summary, _staff_note(data, guest))
		return staff_notifications.notify_staff(
			"accounts", doc, subject, message, assignee=doc.get("assigned_to")
		)

	return staff_notifications._guarded(work, f"Dealer application routing failed for {doc.name}")


def submit(data):
	"""Record one application; resubmitting the same details returns the first one."""
	from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
		canonical_json,
		fingerprint,
	)

	user = frappe.session.user
	guest = user == "Guest"
	if not guest:
		existing = open_application(user)
		if existing:
			return {"success": True, "request": existing.name, "state": existing.state}
	digest = fingerprint({"type": REQUEST_TYPE, "data": data})
	key = fingerprint({"actor": user, "key": digest})
	old = frappe.db.get_value(INTAKE, {"request_key": key}, ["name", "state"], as_dict=True)
	if old:
		return _receipt(old, guest)
	doc = frappe.get_doc(
		{
			"doctype": INTAKE,
			"request_type": REQUEST_TYPE,
			# Never "Guest": every visitor shares that account, and requesters may read their requests.
			"requested_by": None if guest else user,
			"proposed_json": canonical_json(data),
			"request_key": key,
			"request_hash": digest,
			"state": "Pending",
		}
	)
	doc.flags.account_service = True
	doc.insert(ignore_permissions=True)
	notify(doc, data, guest)
	return _receipt(doc, guest)


def _receipt(doc, guest):
	# A guest learns nothing that tells a real application from a honeypot reply.
	return (
		{"success": True, "state": "Pending"}
		if guest
		else {
			"success": True,
			"request": doc.name,
			"state": doc.state,
		}
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60 * 60)
def apply(
	company=None,
	full_name=None,
	email=None,
	phone=None,
	website=None,
	territory=None,
	message=None,
	fax_number=None,
):
	"""Apply for dealer access. ``fax_number`` is the honeypot: people never see it."""
	if str(fax_number or "").strip():
		return {"success": True, "state": "Pending"}
	from illumenate_lighting.illumenate_lighting.portal.access import can_view_catalog

	if frappe.session.user != "Guest" and can_view_catalog():
		return {"success": False, "error": _("Your account already has dealer access.")}
	data, errors = clean(
		{
			"company": company,
			"full_name": full_name,
			"email": email,
			"phone": phone,
			"website": website,
			"territory": territory,
			"message": message,
		}
	)
	if errors:
		return {"success": False, "error": " ".join(errors.values()), "errors": errors}
	return submit(data)
