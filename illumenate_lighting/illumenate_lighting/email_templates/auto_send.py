# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Order confirmation (Sales Order submit) and shipment notice (Delivery Note submit).

These two are app code rather than Frappe Notifications because the dealer portal
already emails portal users for the same events (``portal/notifications.py``), and a
Notification cannot tell whether its recipient is one of them. So:

* the portal keeps emailing its users (respecting their notification toggles), and
* this sends the richer Email Template to the document's ``contact_email`` (or the
  Customer's purchasing contact), minus any address the portal already covers for this
  order, unless ilL-Email-Settings says to email portal users too.

Both are off until enabled in ilL-Email-Settings. The doc event only queues a job after
the commit (doc events never send mail themselves); the job renders as the person who
submitted, sends through ``frappe.core.doctype.communication.email.make`` so the email
shows in the document's timeline, and skips a document that already has a Communication
from the same template, so a retry or a second submit never double-sends.
"""

import frappe

from illumenate_lighting.illumenate_lighting.email_templates.library import BY_SLUG
from illumenate_lighting.illumenate_lighting.email_templates.settings import get_settings

JOBS = {
	"Sales Order": ("auto_send_order_confirmation", "so_confirmation"),
	"Delivery Note": ("auto_send_shipped", "dn_shipped"),
}


def on_sales_order_submit(doc, method=None):
	queue_for(doc)


def on_delivery_note_submit(doc, method=None):
	if doc.get("is_return"):
		return
	queue_for(doc)


def queue_for(doc):
	"""Queue the email for ``doc`` when its switch is on. Never raises into the submit."""
	try:
		setting, _slug = JOBS[doc.doctype]
		if not get_settings().get(setting):
			return
		frappe.enqueue(
			"illumenate_lighting.illumenate_lighting.email_templates.auto_send.send",
			queue="short",
			enqueue_after_commit=True,
			job_id=f"ill-email::{doc.doctype}::{doc.name}",
			deduplicate=True,
			doctype=doc.doctype,
			name=doc.name,
		)
	except Exception:
		frappe.log_error(title=f"ilL email: could not queue {doc.doctype} {doc.name}")


def send(doctype, name):
	"""Background job: render the template and send it. Returns the recipients, or [] when skipped."""
	from frappe.core.doctype.communication.email import make

	setting, slug = JOBS[doctype]
	settings = get_settings()
	template = BY_SLUG[slug]
	if not settings.get(setting) or not frappe.db.exists("Email Template", template.name):
		return []
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus != 1 or (doctype == "Delivery Note" and doc.get("is_return")):
		return []
	if already_sent(doctype, name, template.name):
		return []
	recipients = customer_recipients(doc, include_portal=bool(settings.get("include_portal_recipients")))
	if not recipients:
		doc.add_comment("Info", f"{template.name} not emailed: no customer email outside the dealer portal.")
		return []
	email = frappe.get_doc("Email Template", template.name).get_formatted_email(doc.as_dict())
	print_format = template.attach if settings.get("attach_pdf") else None
	if print_format and not frappe.db.exists("Print Format", print_format):
		print_format = None
	make(
		doctype=doctype,
		name=name,
		subject=email["subject"],
		content=email["message"],
		recipients=", ".join(recipients),
		bcc=settings.get("bcc_email") or None,
		sender=_sender(settings),
		send_email=True,
		print_format=print_format,
		email_template=template.name,
		communication_type="Automated Message",
	)
	return recipients


def already_sent(doctype, name, template_name):
	return bool(
		frappe.db.exists(
			"Communication",
			{
				"reference_doctype": doctype,
				"reference_name": name,
				"email_template": template_name,
				"sent_or_received": "Sent",
			},
		)
	)


def _sender(settings):
	account = settings.get("email_account")
	if not account:
		return None
	return frappe.db.get_value("Email Account", account, "email_id") or None


def customer_recipients(doc, include_portal=False):
	"""contact_email, else the Customer's purchasing contact; minus addresses the portal emails for this order."""
	candidates = []
	if doc.get("contact_email"):
		candidates.append(doc.contact_email)
	else:
		contact = (
			frappe.db.get_value("Customer", doc.get("customer"), "ill_purchasing_contact")
			if _has_purchasing_contact()
			else None
		)
		if contact:
			email = frappe.db.get_value("Contact", contact, "email_id")
			if email:
				candidates.append(email)
	seen, recipients = set(), []
	for email in candidates:
		key = email.strip().lower()
		if key and key not in seen:
			seen.add(key)
			recipients.append(email.strip())
	if include_portal or not recipients:
		return recipients
	covered = portal_addresses(doc)
	return [email for email in recipients if email.lower() not in covered]


def _has_purchasing_contact():
	return bool(frappe.get_meta("Customer").has_field("ill_purchasing_contact"))


def portal_addresses(doc):
	"""Lower-cased emails of the portal users ``portal/notifications.py`` emails for this document."""
	from illumenate_lighting.illumenate_lighting.portal.notifications import order_recipients

	if doc.doctype == "Sales Order":
		orders = [doc.name]
	else:
		orders = sorted(
			{row.against_sales_order for row in doc.get("items") or [] if row.get("against_sales_order")}
		)
	users = set()
	for order in orders:
		try:
			users |= set(order_recipients(frappe.get_doc("Sales Order", order)))
		except Exception:
			frappe.log_error(title=f"ilL email: portal recipients for {order}")
	if not users:
		return set()
	emails = frappe.get_all("User", filters={"name": ["in", list(users)]}, pluck="email")
	return {e.lower() for e in emails if e} | {u.lower() for u in users}
