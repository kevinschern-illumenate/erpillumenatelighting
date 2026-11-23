"""The Done button on the One list and My ToDos.

* A ToDo is closed (status Closed), exactly as closing it in ERPNext would. Only the owner's own ToDos.
* A Gmail thread is hidden: an ilL-Desk-Done record keeps the thread and its last message. While that is
  still the thread's last message, mail.ingest drops the thread and takes @Action/@Waiting off it. A new
  message, theirs or ours, brings it back if it is owed again. Nothing else changes in Gmail.

Records not touched for KEEP_DAYS are pruned when a new one is added: by then the thread is past the
desk's 30-day window anyway. Deleting a record in ERPNext brings its thread back.
"""

import re

import frappe
from frappe.utils import add_days, now_datetime

DOCTYPE = "ilL-Desk-Done"
KEEP_DAYS = 60
GMAIL_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # Gmail thread and message ids
TODO_NAME = re.compile(r"^[A-Za-z0-9_-]{1,140}$")


def parse(item_id):
	"""("todo", name) or ("gmail", mailbox, thread_id) from a One-list item id; anything else is not found."""
	kind, _, rest = (item_id if isinstance(item_id, str) else "").partition(":")
	if kind == "ToDo" and TODO_NAME.match(rest):
		return ("todo", rest)
	if kind == "gmail":
		mailbox, _, thread_id = rest.rpartition(":")
		if "@" in mailbox and GMAIL_ID.match(thread_id):
			return ("gmail", mailbox.strip().lower(), thread_id)
	raise frappe.DoesNotExistError


def close_todo(name, owner):
	"""Close one of the owner's ToDos (already closed or cancelled: nothing to do)."""
	doc = frappe.get_doc("ToDo", name)
	if (doc.allocated_to or "").lower() != owner.lower():
		raise frappe.DoesNotExistError
	if doc.status == "Open":
		doc.status = "Closed"
		doc.save()


def hide_thread(mailbox, thread_id, message_id, title, mailboxes):
	"""Remember a thread as done at its current last message. mailboxes: the desk's own addresses."""
	if mailbox not in mailboxes or not GMAIL_ID.match(message_id if isinstance(message_id, str) else ""):
		raise frappe.DoesNotExistError
	title = (title if isinstance(title, str) else "").strip()[:140] or "(no subject)"
	frappe.db.delete(DOCTYPE, {"modified": ["<", add_days(now_datetime(), -KEEP_DAYS)]})
	name = frappe.db.get_value(DOCTYPE, {"mailbox": mailbox, "thread_id": thread_id})
	if name:
		frappe.db.set_value(DOCTYPE, name, {"message_id": message_id, "title": title})
	else:
		frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"mailbox": mailbox,
				"thread_id": thread_id,
				"message_id": message_id,
				"title": title,
			}
		).insert(ignore_permissions=True)


def marks():
	"""{(mailbox, thread_id): message_id} for every thread marked done ({} before the doctype exists)."""
	try:
		rows = frappe.get_all(DOCTYPE, fields=["mailbox", "thread_id", "message_id"], limit_page_length=0)
	except Exception:
		frappe.log_error(title="Kevin's Desk: couldn't read the done threads")
		return {}
	return {(r["mailbox"], r["thread_id"]): r["message_id"] for r in rows or []}
