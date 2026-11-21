"""Phase 2: the pipeline widgets and the desk owner's ToDos.

Pipeline records come through the Command Center gateway (``cc.gateway``), so they are exactly what the
Command Center shows this user. ToDos are the owner's own records and are read directly (the gateway's
ToDo columns leave out tags, priority and the linked record).

Every item has one shape, which Phase 3 merges with Gmail threads and ranks:
    {id, dt, name, title, party, date, amount, status, flag, url, hat, stack}
``stack`` is the priority-stack level (1 customer blocked / order at risk ... 7 admin); ``flag`` is
"late", "today" or None.
"""

import html
import re
from datetime import timedelta
from urllib.parse import quote

import frappe
from frappe.utils import add_days, getdate, nowdate

from illumenate_lighting.kevins_desk.cc import gateway

LIMIT = 25
OPEN_SO = ["To Deliver and Bill", "To Deliver"]
OPEN_PO = ["To Receive and Bill", "To Receive"]
TAG_LINE = re.compile(r"\[(ad-hoc|email|review|cleanup|meeting)\] Owners:.*$", re.S)
GMAIL = re.compile(r'href="(https://mail\.google\.com[^"]+)"')
FIRST_P = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
TAGS = re.compile(r"<[^>]+>")


def desk_url(dt, name):
	if dt == "HD Ticket":
		return "/helpdesk/tickets/" + quote(str(name), safe="")
	return f"/desk/{dt.lower().replace(' ', '-')}/{quote(str(name), safe='')}"


def iso(value):
	return str(value)[:10] if value else None


def week_end(today):
	"""Sunday of this week (weeks start Monday, as in System Settings)."""
	return today + timedelta(days=6 - today.weekday())


def item(dt, row, *, title, party=None, date_field=None, amount=None, stack, hat, flag=None):
	return {
		"id": f"{dt}:{row['name']}",
		"dt": dt,
		"name": row["name"],
		"title": title,
		"party": party,
		"date": iso(row.get(date_field)) if date_field else None,
		"amount": float(amount) if amount is not None else None,
		"status": row.get("status"),
		"flag": flag,
		"url": desk_url(dt, row["name"]),
		"hat": hat,
		"stack": stack,
	}


def listing(dt, filters, order_by, limit=LIMIT):
	"""Rows, total and column names from the gateway's list action."""
	message = gateway("list", dt=dt, filters=filters, order_by=order_by, limit=limit) or {}
	columns = {c.get("fieldname") for c in message.get("columns") or []}
	return message.get("rows") or [], int(message.get("total") or 0), columns


def widget(key, label, stack, dt, items, total=None, error=None):
	return {
		"key": key,
		"label": label,
		"stack": stack,
		"dt": dt,
		"items": items,
		"total": len(items) if total is None else total,
		"error": error,
	}


# ---------------- pipeline (gateway) ----------------


def orders(today):
	"""Open sales orders due by Sunday: late ones are 'order at risk' (stack 1), the rest converting (3)."""
	rows, total, _ = listing(
		"Sales Order",
		{"status": ["in", OPEN_SO], "delivery_date": ["<=", str(week_end(today))]},
		"delivery_date asc",
		limit=50,
	)
	late, week = [], []
	for r in rows:
		due = getdate(r.get("delivery_date")) if r.get("delivery_date") else None
		is_late = bool(due and due < today)
		it = item(
			"Sales Order",
			r,
			title=r["name"],
			party=r.get("customer"),
			date_field="delivery_date",
			amount=r.get("grand_total"),
			stack=1 if is_late else 3,
			hat="sales" if is_late else "ops",
			flag="late" if is_late else ("today" if due == today else None),
		)
		(late if is_late else week).append(it)
	more = max(0, total - len(rows))
	return (
		widget("so_late", "Sales orders past delivery date", 1, "Sales Order", late),
		widget("so_week", "Sales orders to deliver this week", 3, "Sales Order", week, len(week) + more),
	)


def purchase_orders(today):
	"""Open POs past their ETA (the team-kept ill_eta, else Required By), as in the gateway's po_late."""
	for field in ("ill_eta", "schedule_date"):
		rows, total, columns = listing(
			"Purchase Order", {"status": ["in", OPEN_PO], field: ["<", str(today)]}, f"{field} asc"
		)
		if field in columns:  # the gateway drops filters on columns it doesn't have
			break
	else:
		return widget(
			"po_late",
			"Purchase orders past their date",
			1,
			"Purchase Order",
			[],
			error="No ETA column on this site",
		)
	items = [
		item(
			"Purchase Order",
			r,
			title=r["name"],
			party=r.get("supplier"),
			date_field=field,
			amount=r.get("grand_total"),
			stack=1,
			hat="ops",
			flag="late",
		)
		for r in rows
	]
	return widget("po_late", "Purchase orders past their date", 1, "Purchase Order", items, total)


def quotes(today):
	"""Quotations still Open more than 3 days after their date (new sales, stack 2)."""
	rows, total, _ = listing(
		"Quotation",
		{"status": "Open", "transaction_date": ["<", str(add_days(today, -3))]},
		"transaction_date asc",
	)
	items = [
		item(
			"Quotation",
			r,
			title=r["name"],
			party=r.get("party_name"),
			date_field="transaction_date",
			amount=r.get("grand_total"),
			stack=2,
			hat="sales",
		)
		for r in rows
	]
	return widget("quotes_open", "Quotations open more than 3 days", 2, "Quotation", items, total)


def tickets():
	"""Help desk tickets waiting on us (status Open: the customer wrote last), oldest first (stack 4)."""
	rows, total, _ = listing("HD Ticket", {"status": "Open"}, "modified asc")
	items = [
		item(
			"HD Ticket",
			r,
			title=r.get("subject") or r["name"],
			party=r.get("ticket_type"),
			date_field="modified",
			stack=4,
			hat="sales",
		)
		for r in rows
	]
	return widget("tickets", "Open tickets", 4, "HD Ticket", items, total)


# ---------------- the owner's ToDos (direct) ----------------


def todo_title(description):
	raw = description or ""
	first = FIRST_P.search(raw)
	text = TAGS.sub(" ", first.group(1) if first else raw)
	text = TAG_LINE.sub("", html.unescape(" ".join(text.split()))).strip()
	return (text[:157] + "...") if len(text) > 160 else (text or "(no description)")


def todos(user, today):
	rows = frappe.get_list(
		"ToDo",
		filters={"allocated_to": user, "status": "Open"},
		fields=[
			"name",
			"description",
			"date",
			"priority",
			"reference_type",
			"reference_name",
			"_user_tags",
			"assigned_by",
		],
		order_by="date asc",
		limit_page_length=200,
	)
	out = []
	for r in rows:
		due = getdate(r["date"]) if r.get("date") else None
		bucket = (
			"undated" if not due else "overdue" if due < today else "today" if due == today else "upcoming"
		)
		gmail = GMAIL.search(r.get("description") or "")
		tags = [t for t in (r.get("_user_tags") or "").split(",") if t]
		it = item(
			"ToDo",
			{"name": r["name"], "date": r.get("date"), "status": "Open"},
			title=todo_title(r.get("description")),
			date_field="date",
			stack=7,
			hat=None,
			flag={"overdue": "late", "today": "today"}.get(bucket),
		)
		it.update(
			{
				"bucket": bucket,
				"priority": r.get("priority"),
				"assigned_by": r.get("assigned_by"),
				"tags": tags,
				"gmail": html.unescape(gmail.group(1)) if gmail else None,
				"ref": {
					"dt": r["reference_type"],
					"name": r["reference_name"],
					"url": desk_url(r["reference_type"], r["reference_name"]),
				}
				if r.get("reference_type") and r.get("reference_name")
				else None,
			}
		)
		out.append(it)
	order = {"overdue": 0, "today": 1, "upcoming": 2, "undated": 3}
	out.sort(key=lambda x: (order[x["bucket"]], x["date"] or "9999", x["name"]))
	return out


# ---------------- assembly ----------------


def safely(label, build):
	"""One widget failing (a missing doctype, a permission change) must not blank the page."""
	try:
		return build()
	except Exception:
		frappe.log_error(title=f"Kevin's Desk: {label} failed")
		return None


def build(user, today=None):
	today = getdate(today or nowdate())
	widgets = []
	so = safely("sales orders", lambda: orders(today))
	if so:
		widgets += list(so)
	else:
		widgets.append(
			widget("so_late", "Sales orders past delivery date", 1, "Sales Order", [], error="Couldn't load")
		)
	for key, label, stack, dt, fn in (
		("po_late", "Purchase orders past their date", 1, "Purchase Order", lambda: purchase_orders(today)),
		("quotes_open", "Quotations open more than 3 days", 2, "Quotation", lambda: quotes(today)),
		("tickets", "Open tickets", 4, "HD Ticket", tickets),
	):
		widgets.append(safely(label, fn) or widget(key, label, stack, dt, [], error="Couldn't load"))
	widgets.sort(key=lambda w: w["stack"])
	my_todos = safely("ToDos", lambda: todos(user, today))
	return {
		"today": str(today),
		"widgets": widgets,
		"todos": my_todos if my_todos is not None else [],
		"todos_error": None if my_todos is not None else "Couldn't load",
	}


def signals():
	"""The Command Center's 'Decisions this week' (gateway overview), only those with something in them."""
	message = gateway("overview") or {}
	return {
		"today": message.get("today"),
		"signals": [
			{k: s.get(k) for k in ("id", "label", "dt", "count", "tone", "status")}
			for s in message.get("signals") or []
			if s.get("count")
		],
	}
