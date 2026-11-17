"""Webflow notifications (plan 4.19, D83): approvals and failures; successes as a push only.

Each recipient gets a Notification Log (the Desk bell). Frappe emails it when the user's
Notification Settings allow it, and the Desk shows it as a browser notification
(``public/js/desk/webflow_alerts.js``) while ERPNext is open.

Site config ``webflow_notify_users``: the recipients, as a list of user emails, a JSON string of
one, or a comma-separated string (the Frappe Cloud editor stores text). Unset: nobody is
notified and a warning is logged once.

Successes (owner, 2026-11-08): a spec sheet generated, a push confirmed by Webflow. Only a
browser push (the realtime alert, no bell, no email), only to the person who started it: who
pressed the button, or who saved for an automatic push (``success_push``).
"""

import json
import re

import frappe
from frappe import _

USERS_KEY = "webflow_notify_users"
NOTIFICATION_LOG = "Notification Log"
PRODUCT = "ilL-Webflow-Product"
# An "Alert" log is never emailed by Frappe. A "Mention" log is emailed when the user's
# Notification Settings have email notifications on and Mentions ticked (the default).
LOG_TYPE = "Mention"
REALTIME_EVENT = "ill_webflow_alert"

_warned = False


def parse_users(value):
	"""Pure: user emails from a list, a JSON string of a list, or a comma-separated string.

	Blanks and repeats (ignoring case) are dropped; order is kept.
	"""
	if value is None:
		return []
	if isinstance(value, str):
		text = value.strip()
		if text.startswith(("[", '"')):
			try:
				value = json.loads(text)
			except ValueError:
				value = text.strip('[]"')
		else:
			value = text
	if isinstance(value, str):
		value = re.split(r"[,;\s]+", value)
	if not isinstance(value, (list, tuple)):
		return []
	users, seen = [], set()
	for item in value:
		user = str(item or "").strip().strip("\"'")
		if user and user.lower() not in seen:
			seen.add(user.lower())
			users.append(user)
	return users


def _warn_once():
	global _warned
	if not _warned:
		_warned = True
		frappe.logger("webflow").warning(
			f"Site config {USERS_KEY} is not set: Webflow approvals and failures notify nobody."
		)


def recipients():
	"""Enabled users named in site config, in config order."""
	wanted = parse_users(frappe.conf.get(USERS_KEY))
	if not wanted:
		_warn_once()
		return []
	rows = frappe.get_all(
		"User",
		filters={"enabled": 1},
		or_filters={"name": ["in", wanted], "email": ["in", wanted]},
		fields=["name", "email"],
	)
	by_key = {}
	for row in rows:
		for key in (row.get("name"), row.get("email")):
			if key:
				by_key.setdefault(key.lower(), row.get("name"))
	users = []
	for user in wanted:
		name = by_key.get(user.lower())
		if name and name not in users:
			users.append(name)
	return users


def _desk_route(document_type, document_name):
	return f"/desk/{frappe.scrub(document_type).replace('_', '-')}/{document_name}"


def notify(subject, message, document_type=PRODUCT, document_name=None, once=False):
	"""Bell, email (per Notification Settings) and browser notification for each recipient.

	Never raises: a notification problem must not undo the change that caused it. ``once``
	skips a user who already has a notification with this subject for this document.
	Returns the users notified.
	"""
	try:
		notified = []
		escape = frappe.utils.escape_html
		content = f"<p>{escape(message)}</p>"
		for user in recipients():
			if once and frappe.db.exists(
				NOTIFICATION_LOG,
				{
					"for_user": user,
					"document_type": document_type,
					"document_name": document_name,
					"subject": subject,
				},
			):
				continue
			frappe.get_doc(
				{
					"doctype": NOTIFICATION_LOG,
					"for_user": user,
					"from_user": frappe.session.user,
					"type": LOG_TYPE,
					"email_header": subject,
					"document_type": document_type,
					"document_name": document_name,
					"subject": subject,
					"email_content": content,
				}
			).insert(ignore_permissions=True)
			frappe.publish_realtime(
				REALTIME_EVENT,
				{
					"title": subject,
					"body": message,
					"route": _desk_route(document_type, document_name) if document_name else None,
				},
				user=user,
				after_commit=True,
			)
			notified.append(user)
		return notified
	except Exception:
		frappe.log_error(title=_("Webflow notification failed"))
		return []


def product_label(product):
	"""'kit-ra02 (Rainier [RC] Extrusion Kit)': the linked template's Display Name, else the
	product's name (owner, 2026-11-12). Never raises."""
	try:
		from illumenate_lighting.illumenate_lighting.webflow_product_rules import linked_template

		doc = frappe.get_doc(PRODUCT, product)
		doctype, template = linked_template(doc)
		name = None
		if doctype and template:
			name = frappe.db.get_value(doctype, template, "display_name")
		name = name or doc.get("product_name")
		return f"{product} ({name})" if name and name != product else product
	except Exception:
		return product


def approval_requested(approval):
	"""A new or changed pending approval (plan 4.19 Q5, Q6)."""
	requested_by = approval.get("requested_by") or frappe.session.user
	return notify(
		_("Webflow approval needed: {0} {1}").format(
			approval.get("action"), product_label(approval.get("product"))
		),
		_("{0}. Requested by {1}. Open the Webflow Product to approve or reject it.").format(
			approval.get("summary"), requested_by
		),
		PRODUCT,
		approval.get("product"),
	)


def publication_failed(job, reason=None):
	"""A publication job that ended FAILED; once per job."""
	product, brand = job.get("product"), job.get("brand")
	reason = reason or job.get("last_error") or _("Publication failed")
	return notify(
		_("Webflow sync failed: {0} ({1}, job {2})").format(product, brand, job.get("name")),
		_("{0} on {1} ({2}, attempt {3}): {4}").format(
			job.get("operation") or _("Sync"), brand, product, job.get("attempts") or 1, reason
		),
		PRODUCT,
		product,
		once=True,
	)


def auto_push_failed(product, brand, reason, saved_by=None):
	"""An automatic push that could not be requested (not ready, refused): notify at once.

	Failures after the job was requested are the job's (``publication_failed``), so one failure
	is never notified twice.
	"""
	saved = _(" Last saved by {0}.").format(saved_by) if saved_by else ""
	return notify(
		_("Webflow automatic push failed: {0} ({1})").format(product, brand),
		_("{0} on {1}: {2}.{3} Fix it, then save the product or press Sync to Webflow.").format(
			product, brand, str(reason or _("the push could not be requested")).rstrip("."), saved
		),
		PRODUCT,
		product,
	)


# Users who never get a success push (no person behind them).
NO_PUSH_USERS = ("Guest", "Administrator")


def success_push(user, title, body, document_type=None, document_name=None):
	"""A success as a browser push only, to one user (owner, 2026-11-08). Never raises."""
	try:
		from illumenate_lighting.illumenate_lighting.webflow_auto_push import SERVICE_USER

		if not user or user in NO_PUSH_USERS or user == SERVICE_USER:
			return False
		frappe.publish_realtime(
			REALTIME_EVENT,
			{
				"title": title,
				"body": body,
				"indicator": "green",
				"route": _desk_route(document_type, document_name) if document_name else None,
			},
			user=user,
			after_commit=True,
		)
		return True
	except Exception:
		frappe.log_error(title=_("Webflow success push failed"))
		return False


def push_title(product, operation, status):
	"""Pure: the success push's title, from what Webflow now shows (owner, 2026-11-08: worded
	apart from the page's own "Webflow sync finished.")."""
	if operation == "RETIRE":
		return _("{0} was removed from Webflow").format(product)
	if status in ("Published", "Discontinued"):
		return _("{0} is live on Webflow").format(product)
	if status == "Archived":
		return _("{0} is archived on Webflow").format(product)
	if status == "Webflow Draft":
		return _("{0} is updated on Webflow (hidden)").format(product)
	return _("{0} is updated on Webflow").format(product)


def publication_succeeded(job):
	"""A publication job that Webflow confirmed: push to who started it."""
	product, brand = job.get("product"), job.get("brand")
	return success_push(
		job.get("started_by") or job.get("requested_by"),
		push_title(product, job.get("operation"), job.get("effective_status")),
		_("{0} ({1}) went through.").format(product, brand),
		PRODUCT,
		product,
	)


def spec_sheet_generated(user, template_doctype, template_id):
	"""A spec sheet generated from the template's Generate Spec button."""
	return success_push(
		user,
		_("Spec sheet generated: {0}").format(template_id),
		_("The new spec sheet for {0} is attached to the template.").format(template_id),
		template_doctype,
		template_id,
	)


def spec_sheets_regenerated(user, done, failed):
	"""One push when a bulk regeneration ends."""
	return success_push(
		user,
		_("Spec sheet regeneration finished"),
		_("{0} generated, {1} failed.").format(done, failed),
	)
