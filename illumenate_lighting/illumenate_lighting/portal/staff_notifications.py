"""Tell staff when a dealer submits something, and route it to an owner (DESK-1, DESK-2, DESK-3).

Every submission rings the Desk bell (Notification Log) for its assignee, or for
the whole team that handles the queue when nobody owns it yet, and can also
queue one email to the shared inbox through the portal outbox. New requests are
assigned from ilL-Portal-Routing-Settings: the queue's default assignee, else
the enabled staff user in its role with the fewest open items, and get a due
date from the queue's SLA hours.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.staff import CAPABILITIES

SETTINGS = "ilL-Portal-Routing-Settings"
NOTIFICATION_LOG = "Notification Log"

# queue: (DocType, capability, owner field, due field, due is a Date, label)
QUEUES = {
	"quotes": ("ilL-Quote-Request", "sales", "assigned_to", "due_date", True, "quote request"),
	"orders": ("ilL-Order-Intake", "sales", "assigned_to", "due_date", True, "order request"),
	"order_changes": ("ilL-Order-Change", "sales", "assigned_to", "due_date", True, "order change request"),
	"accounts": ("ilL-Account-Request", "accounts", "assigned_to", None, False, "account request"),
	"support": ("Issue", "support", "ill_support_owner", "ill_support_due", False, "support ticket"),
}
# Conversations also run on these; their replies go to the team that owns the record.
REPLY_ONLY = {
	"ilL-Document-Request": ("engineering", "assigned_to", "drawing request"),
	"ilL-Product-Verification-Request": ("sales", "assigned_to", "product verification"),
	"ilL-Quote-Offer": ("sales", None, "offer"),
}
OFFER_ACTIONS = {"ACCEPT": "accepted", "DECLINE": "declined", "REQUEST_REVISION": "asked to revise"}


def queue_for(doctype):
	return next((queue for queue, spec in QUEUES.items() if spec[0] == doctype), None)


def spec_for(doctype):
	"""(capability, owner field, label) for any DocType that carries a portal conversation."""
	queue = queue_for(doctype)
	if queue:
		_doctype, capability, owner, _due, _is_date, label = QUEUES[queue]
		return capability, owner, label
	return REPLY_ONLY.get(doctype, ("inbox", None, doctype))


def settings():
	try:
		return frappe.get_cached_doc(SETTINGS)
	except Exception:
		# Before the migration creates the Single, behave as if nothing is configured.
		return None


def route(queue):
	config = settings()
	return next((row for row in (config.get("routes") if config else None) or [] if row.queue == queue), None)


def _staff(users):
	if not users:
		return []
	return sorted(
		frappe.get_all(
			"User",
			filters={"name": ["in", sorted(set(users))], "enabled": 1, "user_type": "System User"},
			pluck="name",
		)
	)


def staff_users(roles):
	"""Enabled staff accounts holding any of ``roles``."""
	holders = frappe.get_all(
		"Has Role", filters={"role": ["in", sorted(roles)], "parenttype": "User"}, pluck="parent"
	)
	return [user for user in _staff(holders) if user != "Administrator"]


def _open_filters(queue):
	from illumenate_lighting.illumenate_lighting.portal.queues import QUEUES as STAFF_QUEUES

	return dict(STAFF_QUEUES[queue][3]) if queue in STAFF_QUEUES else {}


def pick_assignee(queue, exclude=None):
	"""The queue's default assignee, else the role member with the fewest open items."""
	doctype, capability, owner, *_rest = QUEUES[queue]
	row = route(queue)
	if row and row.default_assignee and _staff([row.default_assignee]):
		return row.default_assignee
	roles = {row.fallback_role} if row and row.fallback_role else CAPABILITIES[capability]
	candidates = [user for user in staff_users(roles) if user != exclude]
	return least_loaded(doctype, owner, candidates, _open_filters(queue))


def least_loaded(doctype, owner, candidates, open_filters):
	"""Round-robin by workload: the candidate owning the fewest open records of ``doctype``."""
	if not candidates:
		return None
	load = {user: 0 for user in candidates}
	for assignee in frappe.get_all(doctype, filters={**open_filters, owner: ["in", candidates]}, pluck=owner):
		if assignee in load:
			load[assignee] += 1
	# Fewest open items first; the name breaks ties so the choice is repeatable.
	return min(candidates, key=lambda user: (load[user], user))


def assign(doc, queue):
	"""Give a new request an owner and a due date when the queue is configured for them."""
	_doctype, _capability, owner, due, due_is_date, _label = QUEUES[queue]
	values = {}
	if not doc.get(owner):
		assignee = pick_assignee(queue)
		if assignee:
			values[owner] = assignee
	row = route(queue)
	if due and not doc.get(due) and row and (row.sla_hours or 0) > 0:
		deadline = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=row.sla_hours)
		values[due] = frappe.utils.getdate(deadline) if due_is_date else deadline
	if values:
		frappe.db.set_value(doc.doctype, doc.name, values, update_modified=False)
		doc.update(values)
	return values


def _title(doctype, name, field):
	return (frappe.db.get_value(doctype, name, field) if name else None) or name


def context_lines(doc):
	"""Customer, project and schedule for the notification body, when the record has them."""
	rows = []
	customer = doc.get("customer")
	if customer:
		rows.append((_("Customer"), _title("Customer", customer, "customer_name")))
	if doc.get("project"):
		rows.append((_("Project"), _title("ilL-Project", doc.project, "project_name")))
	if doc.get("schedule"):
		rows.append((_("Schedule"), _title("ilL-Project-Fixture-Schedule", doc.schedule, "schedule_name")))
	if doc.get("sales_order"):
		rows.append((_("Sales Order"), doc.sales_order))
	return rows


def who(doc):
	if doc.get("customer"):
		return _title("Customer", doc.customer, "customer_name")
	user = doc.get("requested_by") or doc.get("raised_by") or doc.get("owner")
	return (frappe.db.get_value("User", user, "full_name") if user else None) or user or _("a dealer")


def desk_url(doc):
	return frappe.utils.get_url(f"/app/{doc.doctype.lower().replace(' ', '-')}/{doc.name}")


def body(doc, summary, note=None):
	escape = frappe.utils.escape_html
	parts = [f"<p>{escape(summary)}</p>"]
	lines = context_lines(doc)
	if lines:
		parts.append(
			"<ul>"
			+ "".join(f"<li><strong>{escape(label)}:</strong> {escape(value)}</li>" for label, value in lines)
			+ "</ul>"
		)
	if note:
		parts.append(f'<p style="white-space: pre-wrap">{escape(note)}</p>')
	parts.append(f'<p><a href="{desk_url(doc)}">{escape(_("Open in Desk"))}</a></p>')
	return "".join(parts)


def notify_staff(capability, doc, subject, message, assignee=None, event="submitted", once=True, inbox=True):
	"""Bell the assignee (or the whole team) and optionally queue one shared-inbox email.

	Idempotent per (DocType, name, event): a retried submission rings nobody twice.
	Replies pass ``once=False``: each new message rings again under the same subject.
	"""
	recipients = _staff([assignee]) if assignee else []
	if not recipients:
		recipients = staff_users(CAPABILITIES[capability])
	for user in recipients:
		if user == frappe.session.user:
			continue
		if once and frappe.db.exists(
			NOTIFICATION_LOG,
			{"for_user": user, "document_type": doc.doctype, "document_name": doc.name, "subject": subject},
		):
			continue
		frappe.get_doc(
			{
				"doctype": NOTIFICATION_LOG,
				"for_user": user,
				"from_user": frappe.session.user,
				"type": "Alert",
				"document_type": doc.doctype,
				"document_name": doc.name,
				"subject": subject,
				"email_content": message,
			}
		).insert(ignore_permissions=True)
	config = settings()
	inbox_on = True if config is None else bool(config.get("email_staff_inbox"))
	if inbox and inbox_on:
		from illumenate_lighting.illumenate_lighting.portal.outbox import record_staff_inbox
		from illumenate_lighting.illumenate_lighting.portal.status import SALES_EMAIL

		address = (config.get("staff_inbox_email") if config else None) or SALES_EMAIL
		record_staff_inbox(address, subject, message, doc.doctype, doc.name, event)
	return recipients


def _guarded(work, title):
	"""Routing must never undo a dealer's submission; failures are logged for staff instead."""
	frappe.db.savepoint("portal_staff_routing")
	try:
		return work()
	except Exception:
		frappe.db.rollback(save_point="portal_staff_routing")
		frappe.log_error(title=title, message=frappe.get_traceback(), defer_insert=True)
		return None


def submitted(doc):
	"""Call right after a portal flow inserts a request: assign it, then tell staff."""

	def work():
		queue = queue_for(doc.doctype)
		_doctype, capability, owner, _due, _is_date, label = QUEUES[queue]
		assign(doc, queue)
		kind = doc.get("request_type")
		if queue == "order_changes" and kind:
			label = _("{0} request").format(str(kind).lower())
		elif queue == "accounts" and kind:
			label = _("account request ({0})").format(kind)
		subject = _("New {0} {1} from {2}").format(label, doc.name, who(doc))
		summary = _("{0} submitted {1} {2} in the portal.").format(who(doc), label, doc.name)
		note = doc.get("note") or doc.get("notes")
		return notify_staff(capability, doc, subject, body(doc, summary, note), assignee=doc.get(owner))

	return _guarded(work, f"Portal staff routing failed for {doc.doctype} {doc.name}")


def offer_response(offer, request, action):
	"""Tell Sales a buyer accepted, declined or asked to revise an offer."""

	def work():
		verb = OFFER_ACTIONS.get(action, action.lower())
		subject = _("{0} {1} offer {2}").format(who(request), verb, offer.name)
		summary = _("{0} {1} offer {2} for quote request {3}.").format(
			who(request), verb, offer.name, request.name
		)
		return notify_staff(
			"sales",
			offer,
			subject,
			body(request, summary, offer.get("response_note")),
			assignee=request.get("assigned_to"),
			event=f"response:{action}",
		)

	return _guarded(work, f"Portal staff routing failed for offer {offer.name}")


def reply(doc, message, assignee=None):
	"""Bell the owner of a record a dealer replied on; with no owner, tell the team (DESK-3).

	Only unowned replies go to the shared inbox: an owner already gets their own email.
	"""

	def work():
		capability, _owner, label = spec_for(doc.doctype)
		subject = _("New reply on {0} {1} from {2}").format(label, doc.name, who(doc))
		return notify_staff(
			capability,
			doc,
			subject,
			body(doc, subject, message.body),
			assignee=assignee,
			event=f"reply:{message.name}",
			once=False,
			inbox=not assignee,
		)

	return _guarded(work, f"Portal reply routing failed for {doc.doctype} {doc.name}")
