# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Stage, Waiting On and Stage Detail on Sales Orders and Quotations.

The stage is worked out from data the ERP already has. The six production stages
(Pend-Prod, Waiting for parts, In-Prod, Paint, Held, Pend-Ship) come from the
Production Board's own rules (``production_board.order_status``), so the list view
and the Command Center always agree. Stage Override wins over the worked-out stage
until it is cleared, except that a cancelled document is always Cancelled and a
completed order (or a won or lost quote) always shows that.

Shortages are allocated across every open order in ship-date order, so one order's
stage can change when another order changes. Events therefore queue one refresh of
all open documents (deduplicated), and a cron sweep catches changes ERPNext makes
without running document hooks (Close, On Hold, quote expiry, customer replies).
"""

from datetime import date, datetime

import frappe

from illumenate_lighting.illumenate_lighting.api import build_points
from illumenate_lighting.illumenate_lighting.api import production_board as pb

STAGE = "ill_stage"
OVERRIDE = "ill_stage_override"
WAITING = "ill_waiting_on"
NOTE = "ill_stage_note"
# Quotation only: when it was submitted, so Follow Up counts from sending, not from its date.
SENT_ON = "ill_quote_sent_on"
WRITTEN = (STAGE, WAITING, NOTE)

US, CUSTOMER, VENDOR, WAREHOUSE = "Us", "Customer", "Vendor", "Warehouse"
WAITING_OPTIONS = ("", US, CUSTOMER, VENDOR, WAREHOUSE)

# (stage, waiting on, list indicator colour), in the order an order moves through them.
SALES_ORDER_STAGES = (
	("Pending Approval", US, "gray"),
	("Hold for Release", CUSTOMER, "purple"),
	("Hold for Confirmation", CUSTOMER, "purple"),
	("Needs Work Orders", US, "red"),
	("Pend-Prod", WAREHOUSE, "blue"),
	("Waiting for parts", VENDOR, "orange"),
	("In-Prod", WAREHOUSE, "green"),
	("Paint", VENDOR, "orange"),
	("Held", US, "red"),
	("Pend-Ship", WAREHOUSE, "green"),
	("Hold for Ship", CUSTOMER, "purple"),
	("Will Call - Ready", CUSTOMER, "green"),
	("Proforma - Awaiting Payment", CUSTOMER, "yellow"),
	("Partially Shipped", WAREHOUSE, "light-blue"),
	("Shipped / In Transit", "", "cyan"),
	("Delivered", "", "darkgrey"),
	("Completed", "", "gray"),
	("Cancelled", "", "red"),
)
QUOTATION_STAGES = (
	("Drafting", US, "gray"),
	("Waiting on Info", CUSTOMER, "orange"),
	("Waiting on Vendor", VENDOR, "orange"),
	("Sent", CUSTOMER, "blue"),
	("Revising", US, "purple"),
	("Follow Up", US, "red"),
	("Won", "", "green"),
	("Lost", "", "darkgrey"),
	("Expired", "", "gray"),
	("Cancelled", "", "red"),
)
STAGES = {"Sales Order": SALES_ORDER_STAGES, "Quotation": QUOTATION_STAGES}
WAITING_ON = {dt: {s: w for s, w, _c in rows} for dt, rows in STAGES.items()}

BOARD_STAGE = {
	pb.PEND_PROD: "Pend-Prod",
	pb.IN_PROD: "In-Prod",
	pb.PEND_SHIP: "Pend-Ship",
	pb.HELD: "Held",
	pb.PAINT: "Paint",
	pb.WFP: "Waiting for parts",
}
# Hold Reason values (add_production_hold_fields) are stages of the same name.
HOLD_STAGES = ("Hold for Release", "Hold for Confirmation", "Hold for Ship")
# A Sales Order in one of these is not swept again.
SO_FINAL = ("Completed", "Cancelled")
QUOTE_FINAL = ("Won", "Lost", "Expired", "Cancelled")
WON_STATUSES = ("Ordered", "Partially Ordered")
DEFAULT_FOLLOW_UP_DAYS = 7
JOB_ID = "ill-order-stage-refresh"


# ---------------------------------------------------------------------------
# Pure rules (no database)
# ---------------------------------------------------------------------------


def _num(value):
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def _date(value):
	if not value:
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	return date.fromisoformat(str(value)[:10])


def _result(doctype, stage, notes=(), waiting=None):
	return {
		STAGE: stage,
		WAITING: WAITING_ON[doctype].get(stage, "") if waiting is None else waiting,
		NOTE: " · ".join(n for n in notes if n),
	}


def shipped_note(per_delivered):
	share = _num(per_delivered)
	return f"Partially Shipped ({round(share)}%)" if 0 < share < 100 else ""


def sales_order_stage(order, board=None, paid=False):
	"""Stage fields for one Sales Order.

	``board`` is the Production Board's view of an open order: ``{"status": code,
	"work_orders": count, "eta": date | None, "no_po": [items]}``; None when the
	order is not on the board (draft, closed or fully delivered). ``paid`` says
	whether a Proforma order has been paid in full.
	"""
	dt = "Sales Order"
	docstatus = int(order.get("docstatus") or 0)
	if docstatus == 2:
		return _result(dt, "Cancelled")
	if docstatus == 1 and order.get("status") in ("Completed", "Closed"):
		return _result(dt, "Completed")

	partial = shipped_note(order.get("per_delivered"))
	override = order.get(OVERRIDE) or ""
	if override:
		return _result(dt, override, ["Override", partial])
	if docstatus == 0:
		return _result(dt, "Pending Approval")
	if _num(order.get("per_delivered")) >= 100:
		return _result(dt, "Shipped / In Transit")

	hold = order.get("ill_hold_reason") or ""
	if hold in HOLD_STAGES:
		return _result(dt, hold, [partial])
	if not board:
		# Open but not on the board yet (the board query runs a moment later): wait for the sweep.
		return None

	status = board.get("status")
	if status == pb.PEND_SHIP:
		if partial:
			return _result(dt, "Partially Shipped", [partial])
		marked = order.get("ill_proforma_will_call") or ""
		if marked == "Will Call":
			return _result(dt, "Will Call - Ready")
		if marked == "Proforma" and not paid:
			return _result(dt, "Proforma - Awaiting Payment")
		return _result(dt, "Pend-Ship")
	if status == pb.PEND_PROD and not board.get("work_orders"):
		return _result(dt, "Needs Work Orders", [partial])
	notes = [partial]
	if status == pb.WFP:
		eta = _date(board.get("eta"))
		notes.append(f"Parts ETA {eta.isoformat()}" if eta else "No PO for short parts")
	return _result(dt, BOARD_STAGE.get(status, "Pend-Prod"), notes)


def quotation_stage(quote, today, follow_up_days=DEFAULT_FOLLOW_UP_DAYS, last_sent=None):
	"""Stage fields for one Quotation. ``last_sent`` is the latest email sent from it."""
	dt = "Quotation"
	docstatus = int(quote.get("docstatus") or 0)
	status = quote.get("status") or ""
	if docstatus == 2:
		return _result(dt, "Cancelled")
	if status in WON_STATUSES:
		return _result(dt, "Won")
	if status == "Lost":
		return _result(dt, "Lost")
	override = quote.get(OVERRIDE) or ""
	if override:
		return _result(dt, override, ["Override"])
	if docstatus == 0:
		return _result(dt, "Drafting")
	valid_till = _date(quote.get("valid_till"))
	if status == "Expired" or (valid_till and valid_till < today):
		return _result(dt, "Expired")
	if status == "Replied":
		return _result(dt, "Follow Up", ["Customer replied"])
	sent = _date(last_sent) or _date(quote.get(SENT_ON)) or _date(quote.get("transaction_date"))
	days = (today - sent).days if sent else 0
	if days >= follow_up_days:
		return _result(dt, "Follow Up", [f"Sent {days} days ago, no reply"])
	return _result(dt, "Sent")


def changed(row, values):
	return any((row.get(f) or "") != (values.get(f) or "") for f in WRITTEN)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def _ready(doctype):
	try:
		return frappe.get_meta(doctype).has_field(STAGE)
	except Exception:
		return False


def board_view():
	"""{open Sales Order: board view} using the Production Board's own queries and rules."""
	orders = pb.open_orders()
	names = [o.name for o in orders]
	wos = pb.work_orders_for(names)
	by_order = {}
	for w in wos:
		by_order.setdefault(w.sales_order, []).append(w)

	def esd_of(order):
		return pb.as_date(order.get("ill_estimated_ship_date") or order.get("delivery_date"))

	ranked = sorted(orders, key=lambda o: (esd_of(o) or date.max, o.name))
	needs = pb.material_needs(wos)
	items = {item for bucket in needs.values() for item in bucket}
	shortages = pb.allocate(
		[o.name for o in ranked], needs, pb.stock_on_hand(items), pb.incoming_purchases(items)
	)
	painting = pb.paint_jobs(names, build_points.settings().get("paint_supplier_group"))
	view = {}
	for order in orders:
		gap = shortages.get(order.name) or {"short": {}, "eta": None, "no_po": []}
		mine = by_order.get(order.name, [])
		# The board's rule without the override: the override is applied by sales_order_stage.
		plain = dict(order)
		plain.pop(OVERRIDE, None)
		view[order.name] = {
			"status": pb.order_status(plain, mine, bool(gap["short"]), bool(painting.get(order.name))),
			"work_orders": len(mine),
			"eta": gap["eta"],
			"no_po": gap["no_po"],
		}
	return view


def paid_orders(orders):
	"""Names of Proforma orders paid in full, by advance or by invoices with nothing outstanding."""
	paid = set()
	invoiced = []
	for o in orders:
		total = _num(o.get("rounded_total")) or _num(o.get("grand_total"))
		if total and _num(o.get("advance_paid")) >= total - 0.005:
			paid.add(o.name)
		elif _num(o.get("per_billed")) >= 100:
			invoiced.append(o.name)
	if invoiced:
		lines = frappe.get_all(
			"Sales Invoice Item",
			filters={"sales_order": ["in", invoiced], "docstatus": 1},
			fields=["parent", "sales_order"],
			limit_page_length=0,
		)
		invoices = {}
		for row in lines:
			invoices.setdefault(row.sales_order, set()).add(row.parent)
		every = sorted({inv for group in invoices.values() for inv in group})
		outstanding = (
			{
				r.name: _num(r.outstanding_amount)
				for r in frappe.get_all(
					"Sales Invoice",
					filters={"name": ["in", every], "docstatus": 1},
					fields=["name", "outstanding_amount"],
					limit_page_length=0,
				)
			}
			if every
			else {}
		)
		for name, group in invoices.items():
			if all(outstanding.get(inv, 1) <= 0.005 for inv in group):
				paid.add(name)
	return paid


SO_FIELDS = [
	"name",
	"docstatus",
	"status",
	"per_delivered",
	"per_billed",
	"advance_paid",
	"grand_total",
	"rounded_total",
	"ill_hold_reason",
	"ill_proforma_will_call",
	OVERRIDE,
	*WRITTEN,
]


def _write(doctype, name, values):
	frappe.db.set_value(doctype, name, values, update_modified=False)


def _candidates(doctype, fields, final, extra=()):
	"""Rows whose stage can still change: not final, never set, or matching an ``extra`` filter."""
	fields = pb._fields(doctype, fields)
	rows = {}
	for filters in ({STAGE: ["not in", list(final)]}, {STAGE: ["is", "not set"]}, *extra):
		for row in frappe.get_all(doctype, filters=filters, fields=fields, limit_page_length=0):
			rows[row.name] = row
	return list(rows.values())


def refresh_sales_orders():
	"""Recompute Stage on every Sales Order that is not yet Completed or Cancelled."""
	if not _ready("Sales Order"):
		return 0
	rows = _candidates(
		"Sales Order",
		SO_FIELDS,
		SO_FINAL,
		(
			# Re-opened after Close: back on the board.
			{"docstatus": 1, STAGE: "Completed", "status": ["not in", ["Completed", "Closed"]]},
			# Cancelled after it was swept as Completed.
			{"docstatus": 2, STAGE: "Completed"},
		),
	)
	if not rows:
		return 0
	view = board_view()
	proforma = [r for r in rows if r.get("ill_proforma_will_call") == "Proforma" and r.docstatus == 1]
	paid = paid_orders(proforma)
	updated = 0
	for row in rows:
		values = sales_order_stage(row, view.get(row.name), row.name in paid)
		if values and changed(row, values):
			_write("Sales Order", row.name, values)
			updated += 1
	return updated


def follow_up_days():
	values = build_points.settings()
	days = build_points._number(values, "quote_follow_up_days", DEFAULT_FOLLOW_UP_DAYS)
	return int(days) if days and days > 0 else DEFAULT_FOLLOW_UP_DAYS


def last_sent(names):
	"""{quotation: latest communication_date of an email sent from it}."""
	if not names:
		return {}
	latest = {}
	for row in frappe.get_all(
		"Communication",
		filters={
			"reference_doctype": "Quotation",
			"reference_name": ["in", list(names)],
			"sent_or_received": "Sent",
			"communication_type": "Communication",
		},
		fields=["reference_name", "communication_date"],
		limit_page_length=0,
	):
		when = row.communication_date
		if when and (row.reference_name not in latest or str(when) > str(latest[row.reference_name])):
			latest[row.reference_name] = when
	return latest


QUOTE_FIELDS = ["name", "docstatus", "status", "valid_till", "transaction_date", SENT_ON, OVERRIDE, *WRITTEN]


def refresh_quotations():
	"""Recompute Stage on every Quotation not yet Won, Lost, Expired or Cancelled."""
	if not _ready("Quotation"):
		return 0
	rows = _candidates(
		"Quotation",
		QUOTE_FIELDS,
		QUOTE_FINAL,
		# Expired, then given a later Valid Till.
		({"docstatus": 1, STAGE: "Expired", "status": ["!=", "Expired"]},),
	)
	if not rows:
		return 0
	today = _date(frappe.utils.nowdate())
	days = follow_up_days()
	sent = last_sent([r.name for r in rows if r.docstatus == 1])
	updated = 0
	for row in rows:
		values = quotation_stage(row, today, days, sent.get(row.name))
		if changed(row, values):
			_write("Quotation", row.name, values)
			updated += 1
	return updated


def refresh_all():
	"""Queue worker and cron sweep."""
	return {"sales_orders": refresh_sales_orders(), "quotations": refresh_quotations()}


# ---------------------------------------------------------------------------
# Document events
# ---------------------------------------------------------------------------


def queue_refresh(doc=None, method=None):
	"""Queue one refresh of every open stage after this transaction commits.

	Draft documents other than Work Orders change nothing the board counts, so they
	queue nothing; a draft Work Order already moves an order out of Needs Work Orders.
	"""
	if doc is not None and int(doc.get("docstatus") or 0) == 0 and doc.doctype != "Work Order":
		return
	if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_import:
		return
	frappe.enqueue(
		f"{__name__}.refresh_all",
		queue="short",
		job_id=JOB_ID,
		deduplicate=True,
		enqueue_after_commit=True,
	)


def _apply(doc, values):
	if values:
		for field, value in values.items():
			doc.set(field, value)


def _keep_stored(doc):
	"""Put the stored stage back: only the refresh worker sets a worked-out production stage."""
	before = doc.get_doc_before_save()
	if before:
		for field in WRITTEN:
			doc.set(field, before.get(field))


def sales_order_validate(doc, method=None):
	"""Drafts: Pending Approval or the override. Runs on every save before submit."""
	if int(doc.docstatus or 0) == 0:
		_apply(doc, sales_order_stage(doc))


def sales_order_before_update_after_submit(doc, method=None):
	"""An override shows at once; clearing it keeps the stored stage until the refresh."""
	values = sales_order_stage(doc)
	if values and doc.get(OVERRIDE):
		_apply(doc, values)
	else:
		_keep_stored(doc)


def quotation_validate(doc, method=None):
	if int(doc.docstatus or 0) == 0:
		_apply(doc, quotation_stage(doc, _date(frappe.utils.nowdate()), follow_up_days()))


def quotation_before_submit(doc, method=None):
	"""Sending the quote ends whatever it was waiting on while it was drafted."""
	doc.set(OVERRIDE, "")
	if frappe.get_meta("Quotation").has_field(SENT_ON):
		doc.set(SENT_ON, frappe.utils.nowdate())
	_apply(doc, quotation_stage(doc, _date(frappe.utils.nowdate()), follow_up_days()))


def quotation_before_update_after_submit(doc, method=None):
	sent = last_sent([doc.name]).get(doc.name)
	_apply(doc, quotation_stage(doc, _date(frappe.utils.nowdate()), follow_up_days(), sent))


def quotation_on_cancel(doc, method=None):
	doc.db_set(_result("Quotation", "Cancelled"), update_modified=False)


def sales_order_on_cancel(doc, method=None):
	doc.db_set(_result("Sales Order", "Cancelled"), update_modified=False)
