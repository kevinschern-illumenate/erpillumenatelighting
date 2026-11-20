# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Supplier email goes in and out through one shared purchasing mailbox.

The mailbox is ilL-Email-Settings > Purchasing Email Account, or, when that is blank, the
Email Account whose address is the Purchasing Contact Email (purchasing@ by default).
Until such an Email Account exists, everything here does nothing.

Outgoing (``force_purchasing_sender``): email about a purchasing document leaves from the
mailbox whoever sends it, so suppliers always see the purchasing address and their
replies land in the purchasing inbox. Two places, because mail reaches the queue two ways:

- ``on_communication_before_insert``: the email composer, RFQ "Send Supplier Emails",
  Notifications and ``frappe.core...communication.email.make`` all record a Communication
  first and send from its ``sender``. Changing it there also picks the mailbox's SMTP
  login, its signature and its Reply-To.
- ``use_purchasing_account`` (Email Queue before_insert): mail queued straight through
  ``frappe.sendmail`` (a Notification's own send, scripts) with another account's From.

A person's name is kept ("Reigine Yray <purchasing@…>"); automatic mail carries the
mailbox's name, which ``brand.rebrand_sender`` then turns into "ilLumenate Lighting".

Incoming (``link_purchasing_replies``): replies to email ERPNext sent already thread onto
their document through In-Reply-To. A new email arriving in the mailbox that names a
document number (PUR-ORD-2026-00059, ...) is linked to that document, and to the Supplier
the sender works for, before it is saved.
"""

import html
import json
import re
from email.utils import formataddr, parseaddr
from urllib.parse import quote

import frappe

from illumenate_lighting.illumenate_lighting.email_templates.settings import get_settings

# Email about these documents always goes to (or comes from) a supplier.
PURCHASING_DOCTYPES = (
	"Purchase Order",
	"Request for Quotation",
	"Supplier Quotation",
	"Purchase Receipt",
	"Purchase Invoice",
	"Supplier",
	"Subcontracting Order",
	"Subcontracting Receipt",
	"ilL-Inbound-Shipment",
)
# A Payment Entry is purchasing mail when it pays a supplier (remittance advice).
PAYMENT_ENTRY = "Payment Entry"

# Documents a new email can be linked to by naming them, most specific first.
LINKABLE_DOCTYPES = (
	"Purchase Order",
	"Request for Quotation",
	"Supplier Quotation",
	"Purchase Receipt",
	"Purchase Invoice",
	"ilL-Inbound-Shipment",
)

# Senders that are not a person: their mail carries the mailbox's own name.
AUTOMATED_USERS = ("Administrator", "Guest")

# A sender at one of these domains says nothing about which supplier they work for.
FREE_MAIL_DOMAINS = frozenset(
	{
		"gmail.com",
		"googlemail.com",
		"yahoo.com",
		"ymail.com",
		"outlook.com",
		"hotmail.com",
		"live.com",
		"msn.com",
		"icloud.com",
		"me.com",
		"mac.com",
		"aol.com",
		"proton.me",
		"protonmail.com",
		"gmx.com",
		"mail.com",
		"yandex.com",
		"zoho.com",
		"qq.com",
		"163.com",
		"126.com",
		"foxmail.com",
		"sina.com",
	}
)

# Document names look like PUR-ORD-2026-00059 or PUR-ORD-2026-00059-1 (amended).
_NAME_TOKEN = re.compile(r"(?<![\w-])([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+)(?![\w-])")
_TAG = re.compile(r"<[^>]+>")
_MAX_TOKENS = 25
_MAX_BODY = 50000

_UNSET = object()


def _log(title):
	frappe.log_error(title=f"ilL purchasing mail: {title}", message=frappe.get_traceback())


def _lower(value):
	return (value or "").strip().lower()


# ---------------------------------------------------------------------------
# The mailbox
# ---------------------------------------------------------------------------


def account():
	"""The purchasing Email Account as a dict (name, email_id, enable_outgoing, enable_incoming), or None.

	Read once per request or job.
	"""
	cached = getattr(frappe.local, "ill_purchasing_account", _UNSET)
	if cached is not _UNSET:
		return cached
	found = _find_account(get_settings())
	frappe.local.ill_purchasing_account = found
	return found


def _find_account(settings):
	fields = ["name", "email_id", "enable_outgoing", "enable_incoming"]
	name = (settings.get("purchasing_email_account") or "").strip()
	if name:
		row = frappe.db.get_value("Email Account", name, fields, as_dict=True)
	else:
		address = _lower(settings.get("purchasing_contact_email"))
		row = (
			frappe.db.get_value("Email Account", {"email_id": address}, fields, as_dict=True)
			if address
			else None
		)
	if not row or not row.get("email_id"):
		return None
	return {
		"name": row.get("name"),
		"email_id": _lower(row.get("email_id")),
		"enable_outgoing": int(row.get("enable_outgoing") or 0),
		"enable_incoming": int(row.get("enable_incoming") or 0),
	}


def sending_account():
	"""The mailbox when purchasing mail must leave from it, else None."""
	found = account()
	if not found or not found["enable_outgoing"]:
		return None
	if not int(get_settings().get("force_purchasing_sender") or 0):
		return None
	return found


def is_purchasing(doctype, name=None, doc=None):
	"""Is email about this document supplier email?"""
	if doctype in PURCHASING_DOCTYPES:
		return True
	if doctype == PAYMENT_ENTRY:
		if doc is not None and doc.get("party_type"):
			return doc.get("party_type") == "Supplier"
		return bool(name) and frappe.db.get_value(PAYMENT_ENTRY, name, "party_type") == "Supplier"
	return False


def _sender_name(name, address):
	"""The person's name for the From line, or None when the sender is not a person.

	"Info <info@…>" (a Notification naming its Email Account) and Administrator are not people.
	"""
	name = (name or "").strip()
	if name and name.lower() != _lower(address):
		if name in AUTOMATED_USERS or frappe.db.exists("Email Account", name):
			return None
		return name
	if not address:
		return None
	user = frappe.db.get_value("User", {"email": address}, ["name", "full_name"], as_dict=True)
	if user and user.get("name") not in AUTOMATED_USERS:
		return user.get("full_name") or None
	return None


# ---------------------------------------------------------------------------
# Outgoing
# ---------------------------------------------------------------------------


def use_purchasing_sender(doc):
	"""Communication before_insert: a sent email about a purchasing document comes from the mailbox."""
	if doc.get("communication_medium") != "Email" or (doc.get("sent_or_received") or "Sent") != "Sent":
		return False
	if not is_purchasing(doc.get("reference_doctype"), doc.get("reference_name")):
		return False
	mailbox = sending_account()
	if not mailbox:
		return False
	name, address = parseaddr(doc.get("sender") or "")
	if _lower(address) != mailbox["email_id"]:
		if not doc.get("sender_full_name"):
			doc.sender_full_name = _sender_name(name, address) or mailbox["name"]
		doc.sender = mailbox["email_id"]
	doc.email_account = mailbox["name"]
	return True


def use_purchasing_account(queue):
	"""Email Queue before_insert: purchasing mail queued under another account moves to the mailbox.

	Rewrites the queued message's From (and Reply-To, when it has one) so the supplier
	replies to the mailbox. The body is untouched.
	"""
	from illumenate_lighting.illumenate_lighting.email_templates.brand import replace_header

	if not is_purchasing(queue.get("reference_doctype"), queue.get("reference_name")):
		return False
	mailbox = sending_account()
	if not mailbox:
		return False
	name, address = parseaddr(queue.get("sender") or "")
	same_address = _lower(address) == mailbox["email_id"]
	if same_address and queue.get("email_account") == mailbox["name"]:
		return False
	queue.email_account = mailbox["name"]
	if same_address:
		return True
	sender = formataddr((_sender_name(name, address) or mailbox["name"], mailbox["email_id"]))
	queue.sender = sender
	message = replace_header(queue.get("message"), "From", sender)
	queue.message = replace_header(message, "Reply-To", mailbox["email_id"])
	return True


# ---------------------------------------------------------------------------
# Incoming
# ---------------------------------------------------------------------------


def name_tokens(text, limit=_MAX_TOKENS):
	"""Words shaped like document names (letters, hyphens, at least one digit), in order, once each."""
	seen, out = set(), []
	for match in _NAME_TOKEN.finditer(text or ""):
		token = match.group(1)
		key = token.lower()
		if key in seen or len(token) > 60 or not any(ch.isdigit() for ch in token):
			continue
		seen.add(key)
		out.append(token)
		if len(out) >= limit:
			break
	return out


def plain_text(content):
	return html.unescape(_TAG.sub(" ", (content or "")[:_MAX_BODY]))


def find_reference(subject, content):
	"""(doctype, name) of the first purchasing document the email names, subject before body.

	A cancelled document only wins when nothing else is named.
	"""
	tokens = name_tokens(subject)
	in_subject = {t.lower() for t in tokens}
	body = [t for t in name_tokens(plain_text(content)) if t.lower() not in in_subject]
	tokens = (tokens + body)[:_MAX_TOKENS]
	if not tokens:
		return None
	position = {t.lower(): i for i, t in enumerate(tokens)}
	best = None
	for priority, doctype in enumerate(LINKABLE_DOCTYPES):
		if not frappe.db.exists("DocType", doctype):
			continue
		for row in frappe.get_all(
			doctype,
			filters={"name": ["in", tokens]},
			fields=["name", "docstatus"],
			limit_page_length=0,
		):
			key = (int(row.get("docstatus") or 0) == 2, position.get(_lower(row.get("name")), 99), priority)
			if best is None or key < best[0]:
				best = (key, doctype, row.get("name"))
	return (best[1], best[2]) if best else None


def _domain(address):
	address = _lower(address)
	return address.rsplit("@", 1)[1] if "@" in address else ""


def supplier_for_address(address, own_domain=None):
	"""The one Supplier this sender works for, by exact address and then by company domain.

	Looks at Supplier email, Purchasing Email and the Contacts linked to suppliers. None
	when nobody matches, when two suppliers do, or for a colleague or a free-mail address
	that matches no one exactly.
	"""
	from illumenate_lighting.illumenate_lighting.email_templates.recipients import FIELD

	address = _lower(address)
	domain = _domain(address)
	if not domain or (own_domain and domain == own_domain):
		return None
	fields = ["name", "email_id"]
	if frappe.get_meta("Supplier").has_field(FIELD):
		fields.append(FIELD)
	suppliers = frappe.get_all("Supplier", filters={"disabled": 0}, fields=fields, limit_page_length=0)
	emails = {s.get("name"): {_lower(s.get(f)) for f in fields[1:]} - {""} for s in suppliers}

	exact = {name for name, found in emails.items() if address in found}
	if exact:
		return exact.pop() if len(exact) == 1 else None
	if domain in FREE_MAIL_DOMAINS:
		return None

	by_domain = {name for name, found in emails.items() if any(_domain(e) == domain for e in found)}
	contacts = frappe.get_all(
		"Contact Email",
		filters={"parenttype": "Contact", "email_id": ["like", f"%@{domain}"]},
		fields=["parent", "email_id"],
		limit_page_length=0,
	)
	parents = sorted({c.get("parent") for c in contacts if _domain(c.get("email_id")) == domain})
	if parents:
		active = set(emails)
		by_domain |= {
			link
			for link in frappe.get_all(
				"Dynamic Link",
				filters={"parenttype": "Contact", "parent": ["in", parents], "link_doctype": "Supplier"},
				pluck="link_name",
				limit_page_length=0,
			)
			if link in active
		}
	return by_domain.pop() if len(by_domain) == 1 else None


def link_inbound(doc):
	"""Communication before_insert: new mail in the mailbox gets its document and Supplier."""
	if doc.get("communication_medium") != "Email" or doc.get("sent_or_received") != "Received":
		return False
	mailbox = account()
	if not mailbox or doc.get("email_account") != mailbox["name"]:
		return False
	if not int(get_settings().get("link_purchasing_replies") or 0):
		return False
	changed = False
	if not (doc.get("reference_doctype") and doc.get("reference_name")):
		found = find_reference(doc.get("subject"), doc.get("content"))
		if found:
			doc.reference_doctype, doc.reference_name = found
			changed = True
	supplier = supplier_for_address(parseaddr(doc.get("sender") or "")[1], _domain(mailbox["email_id"]))
	if not supplier and doc.get("reference_doctype") and doc.get("reference_name"):
		if frappe.get_meta(doc.reference_doctype).has_field("supplier"):
			supplier = frappe.db.get_value(doc.reference_doctype, doc.reference_name, "supplier")
	if supplier:
		doc.add_link("Supplier", supplier)
		changed = True
	return changed


def on_communication_before_insert(doc, method=None):
	"""Communication before_insert hook: outgoing sender, incoming links. Never blocks an email."""
	try:
		if not use_purchasing_sender(doc):
			link_inbound(doc)
	except Exception:
		_log("communication")


# ---------------------------------------------------------------------------
# Desk
# ---------------------------------------------------------------------------


def unlinked_mail():
	"""Open email in the mailbox that no document claims: {count, route}, or None without a mailbox."""
	mailbox = account()
	if not mailbox or not mailbox["enable_incoming"]:
		return None
	filters = {
		"email_account": mailbox["name"],
		"sent_or_received": "Received",
		"communication_type": "Communication",
		"status": "Open",
		"reference_name": ["is", "not set"],
	}
	route = (
		f"/app/communication?email_account={quote(mailbox['name'])}"
		"&sent_or_received=Received&communication_type=Communication&status=Open"
		f"&reference_name={quote(json.dumps(['is', 'not set']))}"
	)
	return {"count": frappe.db.count("Communication", filters), "route": route}


def extend_bootinfo(bootinfo):
	"""Desk: the email composer picks the mailbox as From on purchasing documents."""
	try:
		if frappe.session.user == "Guest":
			return
		mailbox = sending_account()
		if mailbox:
			bootinfo.ill_purchasing_mail = {
				"email": mailbox["email_id"],
				"doctypes": list(PURCHASING_DOCTYPES),
				"payment_entry": PAYMENT_ENTRY,
			}
	except Exception:
		_log("boot")
