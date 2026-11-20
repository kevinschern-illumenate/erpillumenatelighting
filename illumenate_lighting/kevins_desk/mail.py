"""Phase 3: read the desk's Gmail mailboxes into ranked items and keep @Action / @Waiting / @Quote labels.

Per mailbox, the desk reads (metadata only, never bodies):
    * the inbox, by the mailbox's scope (ilL-Desk-Mailbox.scope): the last 21 days, unread only, or all of
      it; never the senders Kevin asked to skip (GitHub, Frappe Cloud, Vercel, Amazon, Intuit, LinkedIn,
      Google), and except for "All inbox" never promotions, social and forums
    * sent mail for the last 30 days
    * threads already labelled @Action or @Waiting (so labels can be cleared when a thread moves on)

Thread state, from the last message:
    reply    a customer / outside sender wrote last and the thread is in the inbox  -> @Action
    waiting  we wrote last and nobody answered for 3+ days                          -> @Waiting
    recent   we wrote last, under 3 days ago                                        -> no label
    none     the outside sender wrote last but the thread left the inbox (handled)  -> no label
Automated mail (List-Unsubscribe / List-Id / bulk precedence / Auto-Submitted / no-reply style senders /
the skipped domains) never becomes an item and loses @Action/@Waiting. @Quote is added to quote threads
and never removed. Nothing is archived, marked read, trashed or sent.
"""

import re
from datetime import UTC, datetime
from email.utils import getaddresses, parseaddr

import frappe

from illumenate_lighting.kevins_desk import mailboxes
from illumenate_lighting.kevins_desk.gmail import Gmail, GmailError
from illumenate_lighting.kevins_desk.pipeline import desk_url
from illumenate_lighting.kevins_desk.ranking import thread_stack

SKIP_DOMAINS = (
	"github.com",
	"frappe.cloud",
	"frappe.io",
	"vercel.com",
	"amazon.com",
	"intuit.com",
	"quickbooks.com",
	"linkedin.com",
	"google.com",
)
GENERIC_DOMAINS = {
	"gmail.com",
	"googlemail.com",
	"yahoo.com",
	"outlook.com",
	"hotmail.com",
	"live.com",
	"msn.com",
	"icloud.com",
	"me.com",
	"aol.com",
	"comcast.net",
	"att.net",
	"verizon.net",
	"sbcglobal.net",
	"protonmail.com",
	"proton.me",
}
AUTOMATED_SENDER = re.compile(
	r"^(no-?reply|do-?not-?reply|donotreply|notifications?|notify|mailer-daemon|postmaster|bounces?|alerts?|"
	r"automated|news(?:letter)?|marketing|updates?)\b",
	re.I,
)
SKIP_Q = " ".join(f"-from:{d}" for d in SKIP_DOMAINS)
NOISE_Q = "-category:promotions -category:social -category:forums"
# ilL-Desk-Mailbox.scope -> (inbox query, how many threads to read)
SCOPES = {
	"Recent (21 days)": (f"in:inbox newer_than:21d {NOISE_Q} {SKIP_Q}", 50),
	"Unread only": (f"in:inbox is:unread {NOISE_Q} {SKIP_Q}", 100),
	"All inbox": (f"in:inbox {SKIP_Q}", 100),
}
DEFAULT_SCOPE = "Recent (21 days)"
INBOX_Q = SCOPES[DEFAULT_SCOPE][0]
SENT_Q = "in:sent newer_than:30d"
WAIT_DAYS = 3
LATE = {"reply": 2, "waiting": 7}  # days before an item is flagged late
PER_QUERY = 50
DIRECTORY_TTL = 3600


def domain(address):
	return (address or "").rsplit("@", 1)[-1].lower()


def skipped_domain(address):
	d = domain(address)
	return any(d == s or d.endswith("." + s) for s in SKIP_DOMAINS)


def headers(message):
	return {h["name"].lower(): h["value"] for h in (message.get("payload") or {}).get("headers") or []}


def is_automated(message, address):
	h = headers(message)
	if "list-unsubscribe" in h or "list-id" in h:
		return True
	if h.get("precedence", "").lower() in ("bulk", "list", "junk"):
		return True
	if h.get("auto-submitted", "no").lower() != "no":
		return True
	return bool(AUTOMATED_SENDER.match(address.split("@")[0])) or skipped_domain(address)


def read_thread(thread, me, ours, now):
	"""The facts the desk needs from one thread. Pure.

	``me``: the mailbox and the desk owner's addresses; ``ours``: the company's email domains.
	"We wrote last" means one of ``me`` did, or a colleague did on a thread with someone outside (they
	answered the customer). A colleague writing last on an internal thread is asking us something.
	"""
	msgs = sorted(thread.get("messages") or [], key=lambda m: int(m.get("internalDate") or 0))
	if not msgs:
		return None
	last = msgs[-1]
	last_h = headers(last)
	name, sender = parseaddr(last_h.get("from", ""))
	sender = sender.lower()
	external = [(m, parseaddr(headers(m).get("from", ""))) for m in msgs]
	external = [(m, n, a.lower()) for m, (n, a) in external if domain(a) not in ours]
	last_ours = sender in me or (domain(sender) in ours and bool(external))
	if not last_ours:
		counterpart_name, counterpart = name, sender
	elif external:
		_, counterpart_name, counterpart = external[-1]
	else:  # we started it and nobody outside has answered: the counterpart is who we wrote to
		to = [(n, a.lower()) for n, a in getaddresses([last_h.get("to", ""), last_h.get("cc", "")]) if a]
		to = [p for p in to if p[1] not in me]
		outside = [p for p in to if domain(p[1]) not in ours] or to
		counterpart_name, counterpart = outside[0] if outside else ("", "")
	automated = (
		(not counterpart)
		or any(is_automated(m, a) for m, _, a in external)
		or (bool(counterpart) and is_automated({}, counterpart))
	)
	last_at = datetime.fromtimestamp(int(last.get("internalDate") or 0) / 1000, tz=UTC)
	age = (now - last_at).total_seconds() / 86400
	labels = {lb for m in msgs for lb in m.get("labelIds") or []}
	if not last_ours:
		state = "reply" if "INBOX" in labels else "none"
	else:
		state = "waiting" if age >= WAIT_DAYS else "recent"
	return {
		"id": thread["id"],
		"subject": (headers(msgs[0]).get("subject") or "").strip(),
		"snippet": last.get("snippet") or "",
		"counterpart": counterpart,
		"counterpart_name": (counterpart_name or "").strip().strip('"'),
		"last_at": last_at.isoformat(timespec="seconds"),
		"age_days": age,
		"state": state,
		"automated": automated,
		"labels": labels,
		"message_id": last.get("id"),
		"rfc_message_id": last_h.get("message-id"),
	}


def load_directory():
	"""Customer / supplier / lead by email and by (non-generic) domain. Cached for an hour."""
	cache = frappe.cache()
	hit = cache.get_value("kevins_desk:directory")
	if hit:
		return hit
	emails, domains = {}, {}
	ce, dl = frappe.qb.DocType("Contact Email"), frappe.qb.DocType("Dynamic Link")
	rows = (
		frappe.qb.from_(ce)
		.join(dl)
		.on((dl.parent == ce.parent) & (dl.parenttype == "Contact"))
		.select(ce.email_id, dl.link_doctype, dl.link_name)
		.where(dl.link_doctype.isin(["Customer", "Supplier"]))
		.limit(20000)
		.run(as_dict=True)
	)
	leads = frappe.get_all(
		"Lead",
		filters={"email_id": ["is", "set"], "status": ["!=", "Converted"]},
		fields=["name", "email_id", "company_name", "lead_name"],
		limit_page_length=5000,
	)
	for r in [*rows, *({"email_id": x.email_id, "link_doctype": "Lead", "link_name": x.name} for x in leads)]:
		address = (r.get("email_id") or "").strip().lower()
		if "@" not in address:
			continue
		entry = [r["link_doctype"], r["link_name"]]
		# a customer wins over a supplier or lead sharing the same address or domain
		if address not in emails or entry[0] == "Customer":
			emails[address] = entry
		d = domain(address)
		if d not in GENERIC_DOMAINS and (d not in domains or entry[0] == "Customer"):
			domains[d] = entry
	data = {"emails": emails, "domains": domains}
	cache.set_value("kevins_desk:directory", data, expires_in_sec=DIRECTORY_TTL)
	return data


def who(address, team, directory, ours):
	"""(who, link) for a counterpart: team / customer / supplier / lead / internal / unknown."""
	address = (address or "").lower()
	if address in team:
		return "team", None
	match = directory["emails"].get(address) or directory["domains"].get(domain(address))
	if domain(address) in ours:
		return "internal", None
	if match:
		return match[0].lower(), {"dt": match[0], "name": match[1], "url": desk_url(match[0], match[1])}
	return "unknown", None


def gmail_url(mailbox, thread_id):
	return f"https://mail.google.com/mail/?authuser={mailbox}#all/{thread_id}"


def to_item(info, mailbox, team, directory, ours):
	kind, link = who(info["counterpart"], team, directory, ours)
	title = info["subject"] or "(no subject)"
	stack, hat, topic = thread_stack({"title": title, "snippet": info["snippet"], "who": kind})
	days = int(info["age_days"])
	party = (
		(team.get(info["counterpart"]) or {}).get("name")
		or (link and link["name"])
		or info["counterpart_name"]
	)
	return {
		"id": f"gmail:{mailbox}:{info['id']}",
		"dt": "Gmail",
		"name": info["id"],
		"kind": info["state"],
		"mailbox": mailbox,
		"title": title,
		"party": party or info["counterpart"],
		"party_link": link,
		"who": kind,
		"email": info["counterpart"],
		"date": info["last_at"][:10],
		"last_at": info["last_at"],
		"age_days": days,
		"snippet": info["snippet"][:200],
		"amount": None,
		"status": "Needs reply" if info["state"] == "reply" else f"Waiting {days}d",
		"flag": "late" if info["age_days"] >= LATE[info["state"]] else None,
		"url": gmail_url(mailbox, info["id"]),
		"hat": hat,
		"stack": stack,
		"topic": topic,
		"message_id": info["message_id"],
		"rfc_message_id": info["rfc_message_id"],
	}


def wanted_labels(info, topic):
	if info["automated"] or info["state"] not in ("reply", "waiting"):
		return set()
	want = {"@Action"} if info["state"] == "reply" else {"@Waiting"}
	if topic == "quote":
		want.add("@Quote")
	return want


def ingest(gm, mailbox, me, ours, team, directory, now, scope=DEFAULT_SCOPE):
	"""Items for one mailbox, and how many threads had labels changed."""
	label_ids = gm.ensure_labels()
	names = {v: k for k, v in label_ids.items()}
	inbox_q, inbox_limit = SCOPES.get(scope) or SCOPES[DEFAULT_SCOPE]
	ids = gm.thread_ids(inbox_q, limit=inbox_limit) + gm.thread_ids(SENT_Q, limit=PER_QUERY)
	for name in ("@Action", "@Waiting"):
		ids += gm.thread_ids(label_ids=[label_ids[name]], limit=PER_QUERY)
	items, changed = [], 0
	for thread in gm.threads(ids):
		info = read_thread(thread, me, ours, now)
		if not info:
			continue
		item = (
			None
			if info["automated"] or info["state"] not in ("reply", "waiting")
			else to_item(info, mailbox, team, directory, ours)
		)
		have = {names[lb] for lb in info["labels"] if lb in names}
		want = wanted_labels(info, item and item["topic"])
		add = sorted(want - have)
		remove = sorted(({"@Action", "@Waiting"} - want) & have)
		if add or remove:
			try:
				gm.modify_thread(info["id"], add=add, remove=remove)
				changed += 1
			except GmailError:
				frappe.log_error(title=f"Kevin's Desk: labelling a {mailbox} thread failed")
		if item:
			items.append(item)
	return items, changed


def build(owner, team, now=None):
	"""Threads from every connected mailbox, and each mailbox's state (no tokens in the output)."""
	now = now or datetime.now(UTC)
	rows = mailboxes.rows()
	ours = {domain(owner)} | {domain(r["mailbox"]) for r in rows}
	out = {"mailboxes": [], "threads": []}
	directory = None
	for row in rows:
		st = mailboxes.status(row, owner)
		entry = {k: st.get(k) for k in ("mailbox", "label", "state", "error", "redirect_uri")}
		if st["state"] == "connected":
			try:
				gm = Gmail(st["auth_header"])
				actual = (gm.call("GET", "/profile").get("emailAddress") or "").lower()
				if actual != row["mailbox"]:
					entry.update(
						state="wrong_account", error=f"Connected as {actual}; reconnect as {row['mailbox']}"
					)
				else:
					directory = directory or load_directory()
					me = {row["mailbox"], owner.lower()}
					threads, changed = ingest(
						gm, row["mailbox"], me, ours, team, directory, now, row.get("scope") or DEFAULT_SCOPE
					)
					out["threads"] += threads
					entry.update(threads=len(threads), labels_changed=changed)
			except Exception as e:
				frappe.log_error(title=f"Kevin's Desk: Gmail {row['mailbox']} failed")
				entry.update(state="error", error=str(e)[:200])
		out["mailboxes"].append(entry)
	return out
