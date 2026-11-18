"""Purchasing board: the Command Center purchasing desk, live from ERPNext.

``get_board`` feeds the Command Center Purchasing step: what needs ordering (shortages
against orders, reorder levels), material requests, RFQs and supplier quotations, purchase
orders with vendor status / lead time / ETA, inbound shipments with their costs, purchase
receipts, bills (with QuickBooks status and a 3-way match) and landed cost.

It is read-only and acts as the signed-in user. Dollar figures go only to people with a
finance or purchasing manager role (``scrub``). The write endpoints below it change only
tracking fields or create DRAFTS through the standard ERPNext mappers; nothing here ever
submits or cancels. Every write leaves a "Command Center: ..." comment on the record.

Layout: pure helpers (unit-tested without a database), ``assemble`` (pure: raw rows in,
board out), readers (one bulk query per doctype), ``get_board``, then the writes.
"""

import json
import math
from datetime import timedelta

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api import purchasing
from illumenate_lighting.illumenate_lighting.api.production_board import (
	_fields,
	_has_field,
	as_date,
	incoming_purchases,
	open_orders,
	stock_on_hand,
	work_orders_for,
)

VIEW_ROLES = {
	"Command Center Viewer",
	"System Manager",
	"Purchase Manager",
	"Purchase User",
	"Stock Manager",
	"Accounts Manager",
	"Accounts User",
}
MONEY_ROLES = {"Command Center Finance", "System Manager", "Purchase Manager", "Accounts Manager"}
EDIT_ROLES = {"Command Center Editor", "System Manager", "Purchase Manager", "Purchase User"}

# Fields blanked for people without a money role (plus any key ending in "_amount").
MONEY_KEYS = {
	"amount",
	"total",
	"rate",
	"value",
	"goods_value",
	"est",
	"actual",
	"est_cost",
	"actual_cost",
	"variance",
	"outstanding",
	"landed_pct",
	"purchase_rate",
	"landed_rate",
	"lcv_amount",
	"open_amount",
	"price",
}

WINDOW_DAYS = 120
PO_LANES = (
	"draft",
	"not_sent",
	"awaiting_confirmation",
	"confirmed",
	"in_transit",
	"partly_received",
	"to_bill",
	"done",
	"on_hold",
)
QUOTE_LANES = ("rfq_draft", "awaiting_reply", "quoted", "expiring", "ordered", "expired", "lost")
MR_LANES = ("draft", "to_quote", "quoted", "ordered", "receiving", "done")
SHIPMENT_LANES = ("planned", "moving", "customs", "arriving", "delivered", "final")
BILL_LANES = ("draft", "unpaid", "overdue", "partly_paid", "paid")
ALLOCATION_BASIS = {"By value": "Amount", "By qty": "Qty", "Manual": "Distribute Manually"}
SERVICE_ITEMS = {"FREIGHT-IN", "DUTY", "TARIFF", "BROKERAGE", "MPF-HMF", "INSURANCE-IN", "DRAYAGE"}

PO_TRACKING_FIELDS = (
	"ill_vendor_status",
	"ill_sent_on",
	"ill_vendor_confirmed_on",
	"ill_vendor_order_no",
	"ill_est_lead_time_days",
	"ill_promised_ship_date",
	"ill_eta",
	"ill_freight_mode",
	"ill_purchasing_notes",
)
PO_LINE_FIELDS = ("ill_est_lead_time_days", "ill_eta")
SHIPMENT_FIELDS = (
	"status",
	"supplier",
	"freight_mode",
	"forwarder",
	"customs_broker",
	"tracking_no",
	"tracking_url",
	"container_no",
	"incoterm",
	"origin_country",
	"port_of_loading",
	"port_of_entry",
	"etd",
	"atd",
	"eta",
	"ata",
	"cleared_on",
	"delivered_on",
	"entry_no",
	"entered_value",
	"notes",
)
COST_FIELDS = (
	"cost_type",
	"description",
	"estimated_amount",
	"actual_amount",
	"vendor",
	"purchase_invoice",
	"include_in_landed_cost",
	"expense_account",
	"allocation",
)


# ---------------------------------------------------------------------------
# Pure helpers (no database)
# ---------------------------------------------------------------------------


def _num(value):
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def _iso(day):
	day = as_date(day)
	return day.isoformat() if day else None


def _days_between(start, end):
	start, end = as_date(start), as_date(end)
	return (end - start).days if start and end else None


def po_lane(po):
	"""Board lane for one Purchase Order (first matching rule wins; plan 4.2)."""
	docstatus = int(po.get("docstatus") or 0)
	if docstatus == 0:
		return "draft"
	if docstatus == 2 or po.get("status") == "Cancelled":
		return None
	status = po.get("status")
	if status == "On Hold":
		return "on_hold"
	if status in ("Completed", "Closed", "Delivered"):
		return "done"
	received, billed = _num(po.get("per_received")), _num(po.get("per_billed"))
	if received >= 100 and billed < 100:
		return "to_bill"
	if received >= 100:
		return "done"
	if 0 < received < 100:
		return "partly_received"
	vendor = po.get("ill_vendor_status") or po.get("vendor_status") or ""
	if vendor in ("Shipped", "Delivered"):
		return "in_transit"
	if vendor in ("Confirmed", "In production"):
		return "confirmed"
	if vendor in ("Sent", "Issue"):
		return "awaiting_confirmation"
	return "not_sent"


def quote_lane(quote, today, warn_days):
	"""Lane for an RFQ or Supplier Quotation. ``quote['doctype']`` says which."""
	today = as_date(today)
	docstatus = int(quote.get("docstatus") or 0)
	if docstatus == 2 or quote.get("status") in ("Cancelled", "Stopped"):
		return "lost"
	if quote.get("po"):
		return "ordered"
	if quote.get("doctype") == "Request for Quotation":
		if docstatus == 0:
			return "rfq_draft"
		suppliers = quote.get("suppliers") or []
		if any((s.get("quote_status") or "Pending") == "Pending" for s in suppliers) and not quote.get("sqs"):
			return "awaiting_reply"
		return "quoted"
	if quote.get("status") == "Ordered":
		return "ordered"
	valid = as_date(quote.get("valid_till"))
	if quote.get("status") == "Expired" or (valid and valid < today):
		return "expired"
	if valid and (valid - today).days <= int(warn_days or 0):
		return "expiring"
	return "quoted"


def mr_lane(mr):
	if int(mr.get("docstatus") or 0) == 0:
		return "draft"
	status = mr.get("status") or ""
	if status in ("Received", "Stopped", "Cancelled", "Transferred", "Issued", "Manufactured"):
		return "done"
	if status == "Partially Received":
		return "receiving"
	if status in ("Ordered", "Partially Ordered"):
		return "ordered"
	if mr.get("sqs") or mr.get("rfqs"):
		return "quoted"
	return "to_quote"


def shipment_lane(status):
	return {
		"Planned": "planned",
		"Booked": "moving",
		"In transit": "moving",
		"At port / customs": "customs",
		"Cleared": "customs",
		"Out for delivery": "arriving",
		"Delivered": "delivered",
		"Costs final": "final",
	}.get(status or "Planned")


def bill_lane(bill, today):
	if int(bill.get("docstatus") or 0) == 0:
		return "draft"
	if int(bill.get("docstatus") or 0) == 2:
		return None
	status = bill.get("status") or ""
	outstanding = _num(bill.get("outstanding_amount", bill.get("outstanding")))
	if status == "Paid" or outstanding <= 0:
		return "paid"
	if status == "Partly Paid":
		return "partly_paid"
	due = as_date(bill.get("due_date"))
	if status == "Overdue" or (due and due < as_date(today)):
		return "overdue"
	return "unpaid"


def eta(po_row, header, lead):
	"""(date, source): line ETA -> header ETA -> Required By -> order date + lead time."""
	po_row, header = po_row or {}, header or {}
	for value, source in (
		(po_row.get("ill_eta"), "line"),
		(header.get("ill_eta"), "po"),
		(po_row.get("schedule_date"), "required by"),
		(header.get("schedule_date"), "required by"),
	):
		if value:
			return as_date(value), source
	start = as_date(header.get("transaction_date"))
	if start and lead:
		return start + timedelta(days=int(lead)), "lead time"
	return None, "none"


def late_flags(eta_date, need_by, today, received=False):
	eta_date, need_by, today = as_date(eta_date), as_date(need_by), as_date(today)
	return {
		"overdue": bool(eta_date and not received and eta_date < today),
		"will_miss": bool(eta_date and need_by and not received and eta_date > need_by),
	}


def shortages(demand, stock, incoming, lead_fn, today, safety, open_docs=None):
	"""What to order, in the D.purch row shape the Command Center already draws.

	``demand``: [{item, qty, need_by, src ('Sales Order'|'Work Order'), doc, draft}]. Firm
	demand (submitted orders, active work orders) minus stock on hand minus open PO
	quantity is ``short_firm``; adding draft Sales Orders gives ``short_all``.
	``lead_fn(item)`` -> {lead, lead_src, supplier, group, manufactured}.
	order_by = need_by - lead time - safety days.
	"""
	today = as_date(today)
	open_docs = open_docs or {}
	by_item = {}
	for row in demand:
		if _num(row.get("qty")) <= 0 or not row.get("item"):
			continue
		by_item.setdefault(row["item"], []).append(row)
	out = []
	for item, rows in by_item.items():
		firm = sum(_num(r["qty"]) for r in rows if not r.get("draft"))
		every = sum(_num(r["qty"]) for r in rows)
		on_hand = _num(stock.get(item))
		pending = incoming.get(item) or 0
		on_order = sum(q for _d, q in pending) if isinstance(pending, list) else _num(pending)
		short_firm = round(max(0.0, firm - on_hand - on_order), 6)
		short_all = round(max(0.0, every - on_hand - on_order), 6)
		if short_all <= 0:
			continue
		info = lead_fn(item) or {}
		lead = info.get("lead")
		dates = [as_date(r.get("need_by")) for r in rows if not r.get("draft") and r.get("need_by")]
		dates = dates or [as_date(r.get("need_by")) for r in rows if r.get("need_by")]
		need_by = min(dates) if dates else None
		order_by = need_by - timedelta(days=int(lead or 0) + int(safety or 0)) if need_by and lead else None
		docs, seen = [], set()
		for r in rows:
			key = (r.get("src"), r.get("doc"))
			if r.get("doc") and key not in seen:
				seen.add(key)
				docs.append(
					{"src": r.get("src") or "Sales Order", "doc": r["doc"], "draft": bool(r.get("draft"))}
				)
		extra = open_docs.get(item) or {}
		out.append(
			{
				"item": item,
				"group": info.get("group"),
				"lead": lead,
				"lead_src": info.get("lead_src") or "none",
				"on_hand": round(on_hand, 6),
				"on_order": round(on_order, 6),
				"supplier": info.get("supplier"),
				"need_by": _iso(need_by),
				"order_by": _iso(order_by),
				"late": bool(order_by and order_by < today and short_firm > 0),
				"short_firm": short_firm,
				"short_all": short_all,
				"draft_po": extra.get("draft_po"),
				"mr": extra.get("mr"),
				"manufactured": bool(info.get("manufactured")),
				"docs": docs,
			}
		)
	# firm shortages first, then by order-by date
	out.sort(key=lambda r: (r["short_firm"] <= 0, r["order_by"] or "9999", r["item"]))
	return out


def reorder_breaches(bins, reorder_rows):
	"""Item Reorder rows whose warehouse's projected qty is below the reorder level."""
	projected = {}
	for b in bins:
		key = (b.get("item_code"), b.get("warehouse"))
		projected[key] = projected.get(key, 0) + _num(b.get("projected_qty"))
	out = []
	for r in reorder_rows:
		item = r.get("item") or r.get("parent")
		level = _num(r.get("warehouse_reorder_level"))
		if not item or level <= 0:
			continue
		have = projected.get((item, r.get("warehouse")), 0.0)
		if have >= level:
			continue
		qty = _num(r.get("warehouse_reorder_qty"))
		out.append(
			{
				"item": item,
				"warehouse": r.get("warehouse"),
				"projected": round(have, 6),
				"level": level,
				"reorder_qty": qty,
				"suggest_qty": round(max(qty, level - have), 6),
			}
		)
	return out


def suggest_reorder_level(daily_usage, lead, safety):
	if not daily_usage or daily_usage <= 0 or not lead:
		return None
	return math.ceil(daily_usage * (int(lead) + int(safety or 0)) - 1e-9)


def allocate_costs(total, items, basis):
	"""Split ``total`` over items like ERPNext's Landed Cost Voucher.

	``basis`` "qty" or "value" (also accepts "By qty"/"Qty"/"By value"/"Amount"). Each
	share is rounded to cents and the last item takes the rounding remainder.
	"""
	by_qty = str(basis).lower() in ("qty", "by qty")
	weights = [_num(i.get("qty") if by_qty else (i.get("amount") or i.get("base_amount"))) for i in items]
	whole = sum(weights)
	if not items:
		return []
	if not whole:
		weights, whole = [1.0] * len(items), float(len(items))
	shares = [round(_num(total) * w / whole, 2) for w in weights]
	shares[-1] = round(_num(total) - sum(shares[:-1]), 2)
	return shares


def landed_unit_cost(rate, qty, allocated):
	return round(_num(rate) + (_num(allocated) / _num(qty) if _num(qty) else 0), 4)


def uplift_pct(rate, landed):
	return round((_num(landed) - _num(rate)) / _num(rate) * 100, 2) if _num(rate) else None


def three_way(po_rows, pr_rows, pi_rows, pct=2.0, dollars=50.0):
	"""PO vs received vs billed, per item: quantity and price variances.

	Rows are {item, qty, rate}. Qty variance = billed - received (ordered when nothing was
	received yet); price variance = (billed rate - PO rate) x billed qty. Flagged above
	``pct`` % or ``dollars``.
	"""

	def fold(rows):
		out = {}
		for r in rows:
			cur = out.setdefault(r.get("item"), [0.0, 0.0])
			cur[0] += _num(r.get("qty"))
			cur[1] += _num(r.get("qty")) * _num(r.get("rate"))
		return out

	po, pr, pi = fold(po_rows), fold(pr_rows), fold(pi_rows)
	items, qty_var, price_var, qty_off, price_off = [], 0.0, 0.0, False, False
	for item, (billed_qty, billed_value) in pi.items():
		ordered_qty, ordered_value = po.get(item, (0.0, 0.0))
		received_qty = pr.get(item, (0.0, 0.0))[0] if item in pr else ordered_qty
		po_rate = ordered_value / ordered_qty if ordered_qty else 0.0
		bill_rate = billed_value / billed_qty if billed_qty else 0.0
		dq = round(billed_qty - received_qty, 6)
		dp = round((bill_rate - po_rate) * billed_qty, 2) if po_rate else 0.0
		q_flag = bool(received_qty and abs(dq) / received_qty * 100 > pct) or bool(dq and not received_qty)
		p_flag = bool(po_rate) and (abs(bill_rate - po_rate) / po_rate * 100 > pct or abs(dp) > dollars)
		qty_off, price_off = qty_off or q_flag, price_off or p_flag
		qty_var += dq
		price_var += dp
		items.append({"item": item, "qty": dq, "price": dp, "qty_off": q_flag, "price_off": p_flag})
	match = "qty_off" if qty_off else "price_off" if price_off else "matches"
	return {"match": match, "qty": round(qty_var, 6), "price": round(price_var, 2), "items": items}


def scrub(value):
	"""Blank every money field, at any depth."""
	if isinstance(value, dict):
		for key, item in value.items():
			if key in MONEY_KEYS or key.endswith("_amount"):
				if isinstance(item, dict):
					value[key] = {k: None for k in item}
				elif not isinstance(item, list):
					value[key] = None
				else:
					scrub(item)
			else:
				scrub(item)
	elif isinstance(value, list):
		for item in value:
			scrub(item)
	return value


def lcv_plan(costs, receipts, allow_estimate=False):
	"""Taxes rows and distribution basis for a Landed Cost Voucher, or raise ValueError.

	``costs``: shipment cost lines; ``receipts``: [{name, docstatus}]. One taxes row per
	included cost type (amount = actual; estimates only with ``allow_estimate``).
	"""
	if not receipts:
		raise ValueError(_("This shipment has no purchase receipts yet."))
	draft = [r["name"] for r in receipts if int(r.get("docstatus") or 0) != 1]
	if draft:
		raise ValueError(_("Submit these purchase receipts first: {0}").format(", ".join(draft)))
	lines = [c for c in costs if int(c.get("include_in_landed_cost") or 0)]
	if not lines:
		raise ValueError(_("No cost line on this shipment is marked In Landed Cost."))
	no_account = sorted({c.get("cost_type") for c in lines if not c.get("expense_account")})
	if no_account:
		raise ValueError(_("Set an expense account on: {0}").format(", ".join(no_account)))
	unbilled = sorted({c.get("cost_type") for c in lines if c.get("actual_amount") in (None, "")})
	if unbilled and not allow_estimate:
		raise ValueError(
			_("No actual amount yet for: {0}. Link the bills, or draft it from estimates.").format(
				", ".join(unbilled)
			)
		)
	bases = {c.get("allocation") or "By value" for c in lines}
	if len(bases) > 1:
		raise ValueError(
			_(
				"These costs use different allocation bases ({0}). A Landed Cost Voucher has one basis: "
				"split them into two vouchers or set them all to Manual."
			).format(", ".join(sorted(bases)))
		)
	grouped = {}
	for c in lines:
		amount = (
			_num(c.get("actual_amount"))
			if c.get("actual_amount") not in (None, "")
			else _num(c.get("estimated_amount"))
		)
		key = c.get("cost_type")
		row = grouped.setdefault(
			key, {"expense_account": c.get("expense_account"), "description": key, "amount": 0.0}
		)
		if row["expense_account"] != c.get("expense_account"):
			raise ValueError(
				_("{0} lines post to different accounts; use one account per cost type.").format(key)
			)
		row["amount"] += amount
	taxes = [dict(r, amount=round(r["amount"], 2)) for r in grouped.values() if r["amount"]]
	if not taxes:
		raise ValueError(_("The included costs add up to zero."))
	return {"taxes": taxes, "basis": ALLOCATION_BASIS[bases.pop()]}


# ---------------------------------------------------------------------------
# The board (pure): raw rows in, board out
# ---------------------------------------------------------------------------


def _lead_info(item, raw, lead_fn):
	info = (raw.get("items") or {}).get(item) or {}
	supplier = info.get("default_supplier")
	days, source = lead_fn(item, supplier)
	return {
		"lead": days,
		"lead_src": source,
		"supplier": supplier,
		"group": info.get("item_group"),
		"manufactured": bool(info.get("default_bom")),
	}


def _decision(out, id_, label, count, tone, tab, lane=None):
	if count:
		out.append({"id": id_, "label": label, "count": count, "tone": tone, "tab": tab, "lane": lane})


def assemble(raw, settings, today, lead_fn, money=True, can_edit=False):
	"""Build the board from raw ERPNext rows. Pure: no database access."""
	today = as_date(today)
	warn_quote = int(settings.get("quote_expiry_warn_days") or 7)
	warn_confirm = int(settings.get("vendor_confirm_warn_days") or 3)
	warn_bill = int(settings.get("receipt_bill_warn_days") or 14)
	warn_lcv = int(settings.get("lcv_warn_days") or 30)
	safety = int(settings.get("safety_days") or 0)
	items_info = raw.get("items") or {}
	so_dates = {k: as_date(v) for k, v in (raw.get("so_dates") or {}).items()}

	# ---- links between documents ----
	mr_rfqs, mr_sqs, mr_pos = {}, {}, {}
	rfq_sqs, sq_pos = {}, {}
	for rfq in raw.get("rfqs") or []:
		for it in rfq.get("items") or []:
			if it.get("material_request"):
				mr_rfqs.setdefault(it["material_request"], set()).add(rfq["name"])
	for sq in raw.get("sqs") or []:
		for it in sq.get("items") or []:
			if it.get("material_request"):
				mr_sqs.setdefault(it["material_request"], set()).add(sq["name"])
			if it.get("request_for_quotation"):
				rfq_sqs.setdefault(it["request_for_quotation"], set()).add(sq["name"])
	for p in raw.get("pos") or []:
		if int(p.get("docstatus") or 0) == 2:
			continue
		for it in p.get("items") or []:
			if it.get("material_request"):
				mr_pos.setdefault(it["material_request"], set()).add(p["name"])
			if it.get("supplier_quotation"):
				sq_pos.setdefault(it["supplier_quotation"], set()).add(p["name"])
	rfq_pos = {}
	for rfq, sqs in rfq_sqs.items():
		for sq in sqs:
			rfq_pos.setdefault(rfq, set()).update(sq_pos.get(sq, set()))

	# ---- material requests ----
	mrs = []
	for mr in raw.get("mrs") or []:
		name = mr["name"]
		row = {
			"name": name,
			"status": mr.get("status"),
			"docstatus": int(mr.get("docstatus") or 0),
			"schedule_date": _iso(mr.get("schedule_date")),
			"transaction_date": _iso(mr.get("transaction_date")),
			"items": [
				{
					"item": i.get("item_code"),
					"qty": _num(i.get("qty")),
					"ordered_qty": _num(i.get("ordered_qty")),
				}
				for i in mr.get("items") or []
			],
			"from_so": next(
				(i.get("sales_order") for i in mr.get("items") or [] if i.get("sales_order")), None
			),
			"rfqs": sorted(mr_rfqs.get(name, ())),
			"sqs": sorted(mr_sqs.get(name, ())),
			"pos": sorted(mr_pos.get(name, ())),
		}
		row["lane"] = mr_lane(row)
		row["late"] = bool(
			row["schedule_date"] and as_date(row["schedule_date"]) < today and row["lane"] != "done"
		)
		mrs.append(row)

	# ---- RFQs and supplier quotations ----
	quotes = []
	for rfq in raw.get("rfqs") or []:
		pos = sorted(rfq_pos.get(rfq["name"], ()))
		row = {
			"doctype": "Request for Quotation",
			"name": rfq["name"],
			"status": rfq.get("status"),
			"docstatus": int(rfq.get("docstatus") or 0),
			"suppliers": [
				{
					"supplier": s.get("supplier"),
					"quote_status": s.get("quote_status") or "Pending",
					"email_sent": bool(s.get("email_sent")),
				}
				for s in rfq.get("suppliers") or []
			],
			"sqs": sorted(rfq_sqs.get(rfq["name"], ())),
			"transaction_date": _iso(rfq.get("transaction_date")),
			"valid_till": None,
			"days_left": None,
			"total": None,
			"lead_days": None,
			"items": len(rfq.get("items") or []),
			"mr": next(
				(i.get("material_request") for i in rfq.get("items") or [] if i.get("material_request")), None
			),
			"rfq": None,
			"po": pos[0] if pos else None,
		}
		row["lane"] = quote_lane(row, today, warn_quote)
		quotes.append(row)
	compare = {}
	for sq in raw.get("sqs") or []:
		pos = sorted(sq_pos.get(sq["name"], ()))
		its = sq.get("items") or []
		leads = [int(i.get("lead_time_days") or 0) for i in its if i.get("lead_time_days")]
		valid = as_date(sq.get("valid_till"))
		row = {
			"doctype": "Supplier Quotation",
			"name": sq["name"],
			"status": sq.get("status"),
			"docstatus": int(sq.get("docstatus") or 0),
			"supplier": sq.get("supplier"),
			"transaction_date": _iso(sq.get("transaction_date")),
			"valid_till": _iso(valid),
			"days_left": (valid - today).days if valid else None,
			"total": _num(sq.get("base_grand_total") or sq.get("grand_total")),
			"lead_days": max(leads) if leads else None,
			"items": len(its),
			"mr": next((i.get("material_request") for i in its if i.get("material_request")), None),
			"rfq": next(
				(i.get("request_for_quotation") for i in its if i.get("request_for_quotation")), None
			),
			"po": pos[0] if pos else None,
		}
		row["lane"] = quote_lane(row, today, warn_quote)
		quotes.append(row)
		if row["lane"] in ("quoted", "expiring") and row["docstatus"] == 1:
			for i in its:
				compare.setdefault(i.get("item_code"), []).append(
					{
						"sq": sq["name"],
						"supplier": sq.get("supplier"),
						"rate": _num(i.get("rate")),
						"lead_days": int(i.get("lead_time_days") or 0) or None,
						"valid_till": row["valid_till"],
					}
				)
	quote_compare = []
	for item, rows in sorted(compare.items()):
		if len({r["sq"] for r in rows}) < 2:
			continue
		cheapest = min(r["rate"] for r in rows)
		leads = [r["lead_days"] for r in rows if r["lead_days"]]
		fastest = min(leads) if leads else None
		for r in rows:
			r["cheapest"] = r["rate"] == cheapest
			r["fastest"] = bool(fastest and r["lead_days"] == fastest)
		quote_compare.append({"item": item, "rows": sorted(rows, key=lambda r: r["rate"])})

	# ---- shipments (before POs: they feed the PO cards) ----
	lcv_by_receipt = {}
	vouchers = []
	for v in raw.get("lcvs") or []:
		receipts = [r for r in v.get("receipts") or [] if r]
		for r in receipts:
			lcv_by_receipt.setdefault(r, []).append(
				{"name": v["name"], "docstatus": int(v.get("docstatus") or 0)}
			)
		vouchers.append(
			{
				"name": v["name"],
				"docstatus": int(v.get("docstatus") or 0),
				"receipts": receipts,
				"amount": _num(v.get("total_taxes_and_charges")),
				"posting_date": _iso(v.get("posting_date")),
			}
		)
	receipt_docstatus = {r["name"]: int(r.get("docstatus") or 0) for r in raw.get("receipts") or []}
	shipments, po_shipments, receipt_shipment = [], {}, {}
	for s in raw.get("shipments") or []:
		lane = shipment_lane(s.get("status"))
		if not lane:
			continue
		costs = s.get("costs") or []
		pos = [r.get("purchase_order") for r in s.get("purchase_orders") or [] if r.get("purchase_order")]
		receipts = [r.get("purchase_receipt") for r in s.get("receipts") or [] if r.get("purchase_receipt")]
		lcvs = [
			{"name": r.get("landed_cost_voucher"), "docstatus": int(r.get("lcv_docstatus") or 0)}
			for r in s.get("landed_cost_vouchers") or []
			if r.get("landed_cost_voucher")
		]
		for r in receipts:
			for v in lcv_by_receipt.get(r, []):
				if v["name"] not in {x["name"] for x in lcvs}:
					lcvs.append(dict(v))
		totals = purchasing.shipment_totals(s.get("purchase_orders") or [], costs)
		included = [c for c in costs if int(c.get("include_in_landed_cost") or 0)]
		landed_basis = sum(purchasing.cost_basis_amount(c) for c in included)
		landed = any(v["docstatus"] == 1 for v in lcvs)
		needs_lcv = bool(
			landed_basis > 0
			and not landed
			and (receipts or s.get("status") in ("Delivered", "Costs final"))
			and s.get("status") != "Cancelled"
		)
		for p in pos:
			po_shipments.setdefault(p, []).append(s["name"])
		for r in receipts:
			receipt_shipment.setdefault(r, s["name"])
		shipments.append(
			{
				"name": s["name"],
				"status": s.get("status"),
				"lane": lane,
				"supplier": s.get("supplier"),
				"forwarder": s.get("forwarder"),
				"broker": s.get("customs_broker"),
				"mode": s.get("freight_mode"),
				"tracking_no": s.get("tracking_no"),
				"tracking_url": s.get("tracking_url"),
				"container_no": s.get("container_no"),
				"incoterm": s.get("incoterm"),
				"port_of_loading": s.get("port_of_loading"),
				"port_of_entry": s.get("port_of_entry"),
				"entry_no": s.get("entry_no"),
				"etd": _iso(s.get("etd")),
				"atd": _iso(s.get("atd")),
				"eta": _iso(s.get("eta")),
				"ata": _iso(s.get("ata")),
				"delivered_on": _iso(s.get("delivered_on")),
				"notes": s.get("notes"),
				"pos": pos,
				"receipts": receipts,
				"goods_value": totals["goods_value"],
				"est_cost": totals["estimated_cost_total"],
				"actual_cost": totals["actual_cost_total"],
				"variance": totals["variance"],
				"landed_pct": totals["landed_cost_pct"],
				"costs": [
					{
						"name": c.get("name"),
						"cost_type": c.get("cost_type"),
						"description": c.get("description"),
						"est": _num(c.get("estimated_amount")),
						"actual": None
						if c.get("actual_amount") in (None, "")
						else _num(c.get("actual_amount")),
						"vendor": c.get("vendor"),
						"pi": c.get("purchase_invoice"),
						"in_lc": bool(int(c.get("include_in_landed_cost") or 0)),
						"expense_account": c.get("expense_account"),
						"allocation": c.get("allocation"),
					}
					for c in costs
				],
				"lcvs": lcvs,
				"needs_lcv": needs_lcv,
				"_landed_basis": landed_basis,
				"_receipt_status": [receipt_docstatus.get(r, 0) for r in receipts],
			}
		)

	# ---- receipts and bills, indexed by PO ----
	po_receipts, po_invoices = {}, {}
	for r in raw.get("receipts") or []:
		if int(r.get("docstatus") or 0) == 2:
			continue
		for i in r.get("items") or []:
			if i.get("purchase_order"):
				po_receipts.setdefault(i["purchase_order"], set()).add(r["name"])
	for b in raw.get("invoices") or []:
		if int(b.get("docstatus") or 0) == 2:
			continue
		for i in b.get("items") or []:
			if i.get("purchase_order"):
				po_invoices.setdefault(i["purchase_order"], set()).add(b["name"])

	# ---- purchase orders ----
	paint = set(raw.get("paint_suppliers") or ())
	pos_out = []
	for p in raw.get("pos") or []:
		lane = po_lane(p)
		if not lane:
			continue
		lines = []
		header_lead, header_src = purchasing.resolve_lead([(p.get("ill_est_lead_time_days"), "po")])
		best = (None, "none")
		for it in p.get("items") or []:
			days, src = lead_fn(it.get("item_code"), p.get("supplier"), po_row=it, po=p)
			if days and (not best[0] or days > best[0]):
				best = (days, src)
			line_eta, _src = eta(it, p, days)
			lines.append(
				{
					"name": it.get("name"),
					"item": it.get("item_code"),
					"item_name": it.get("item_name"),
					"qty": _num(it.get("qty")),
					"received_qty": _num(it.get("received_qty")),
					"ill_est_lead_time_days": it.get("ill_est_lead_time_days"),
					"ill_eta": _iso(it.get("ill_eta")),
					"lead_days": days,
					"eta": _iso(line_eta),
				}
			)
		lead_days, lead_src = (header_lead, header_src) if header_lead else best
		po_eta, eta_src = eta(None, p, lead_days)
		sos = sorted({it.get("sales_order") for it in p.get("items") or [] if it.get("sales_order")})
		needs = sorted((so_dates[s], s) for s in sos if so_dates.get(s))
		need_by, need_so = (needs[0][0], needs[0][1]) if needs else (None, None)
		received = _num(p.get("per_received")) >= 100 or lane in ("done", "to_bill")
		flags = late_flags(po_eta, need_by, today, received=received or lane == "draft")
		pos_out.append(
			{
				"name": p["name"],
				"supplier": p.get("supplier"),
				"lane": lane,
				"status": p.get("status"),
				"docstatus": int(p.get("docstatus") or 0),
				"vendor_status": p.get("ill_vendor_status") or ("Not sent" if lane != "draft" else ""),
				"transaction_date": _iso(p.get("transaction_date")),
				"creation": _iso(p.get("creation")),
				"sent_on": _iso(p.get("ill_sent_on")),
				"confirmed_on": _iso(p.get("ill_vendor_confirmed_on")),
				"vendor_order_no": p.get("ill_vendor_order_no"),
				"promised_ship_date": _iso(p.get("ill_promised_ship_date")),
				"est_lead_time_days": p.get("ill_est_lead_time_days"),
				# the header ETA as typed (the board's "eta" falls back to lines / Required By / lead time)
				"ill_eta": _iso(p.get("ill_eta")),
				"lead_days": lead_days,
				"lead_src": lead_src,
				"eta": _iso(po_eta),
				"eta_src": eta_src,
				"need_by": _iso(need_by),
				"overdue": flags["overdue"] and lane != "draft",
				"will_miss": flags["will_miss"],
				"will_miss_so": need_so if flags["will_miss"] else None,
				"per_received": _num(p.get("per_received")),
				"per_billed": _num(p.get("per_billed")),
				"amount": _num(p.get("base_net_total") or p.get("base_grand_total") or p.get("grand_total")),
				"freight_mode": p.get("ill_freight_mode"),
				"notes": p.get("ill_purchasing_notes"),
				"sales_orders": sos,
				"shipments": po_shipments.get(p["name"], []),
				"receipts": sorted(po_receipts.get(p["name"], ())),
				"invoices": sorted(po_invoices.get(p["name"], ())),
				"paint": p.get("supplier") in paint,
				"lines": lines,
			}
		)
	po_by_name = {p["name"]: p for p in pos_out}

	# ---- receipts ----
	shipment_by_name = {s["name"]: s for s in shipments}
	receipts_out = []
	for r in raw.get("receipts") or []:
		docstatus = int(r.get("docstatus") or 0)
		if docstatus == 2:
			continue
		its = r.get("items") or []
		lcv_amount = round(sum(_num(i.get("landed_cost_voucher_amount")) for i in its), 2)
		ship = receipt_shipment.get(r["name"])
		landed = lcv_amount > 0 or any(v["docstatus"] == 1 for v in lcv_by_receipt.get(r["name"], []))
		ship_needs = bool(ship and shipment_by_name.get(ship, {}).get("_landed_basis"))
		status = "landed" if landed else "needs_lcv" if ship_needs and docstatus == 1 else "no_costs"
		receipts_out.append(
			{
				"name": r["name"],
				"supplier": r.get("supplier"),
				"posting_date": _iso(r.get("posting_date")),
				"status": r.get("status"),
				"docstatus": docstatus,
				"pos": sorted({i.get("purchase_order") for i in its if i.get("purchase_order")}),
				"amount": _num(r.get("base_net_total") or r.get("base_grand_total")),
				"billed_pct": _num(r.get("per_billed")),
				"shipment": ship,
				"lcv_amount": lcv_amount,
				"needs_lcv": status == "needs_lcv",
				"lcv_status": status,
			}
		)

	# ---- bills ----
	shipment_bills = {c["pi"] for s in shipments for c in s["costs"] if c.get("pi")}
	po_lines = {}
	for p in raw.get("pos") or []:
		po_lines[p["name"]] = [
			{"item": i.get("item_code"), "qty": _num(i.get("qty")), "rate": _num(i.get("rate"))}
			for i in p.get("items") or []
		]
	pr_lines = {}
	for r in raw.get("receipts") or []:
		if int(r.get("docstatus") or 0) == 1:
			pr_lines[r["name"]] = [
				{"item": i.get("item_code"), "qty": _num(i.get("qty")), "rate": _num(i.get("rate"))}
				for i in r.get("items") or []
			]
	qbo_since = as_date(raw.get("qbo_since"))
	bills = []
	for b in raw.get("invoices") or []:
		lane = bill_lane(b, today)
		if not lane or int(b.get("is_return") or 0):
			continue
		its = b.get("items") or []
		pos = sorted({i.get("purchase_order") for i in its if i.get("purchase_order")})
		prs = sorted({i.get("purchase_receipt") for i in its if i.get("purchase_receipt")})
		goods = bool(pos or prs)
		freight = b["name"] in shipment_bills or any(i.get("item_code") in SERVICE_ITEMS for i in its)
		kind = "freight/duty" if freight and not goods else "goods"
		match, variance = None, None
		if pos:
			bill_items = {i.get("item_code") for i in its}
			po_rows = [r for p in pos for r in po_lines.get(p, []) if r["item"] in bill_items]
			pr_rows = [r for p in prs for r in pr_lines.get(p, []) if r["item"] in bill_items]
			pi_rows = [
				{"item": i.get("item_code"), "qty": _num(i.get("qty")), "rate": _num(i.get("rate"))}
				for i in its
			]
			if po_rows:
				check = three_way(po_rows, pr_rows, pi_rows)
				match, variance = check["match"], {"qty": check["qty"], "price": check["price"]}
		bills.append(
			{
				"name": b["name"],
				"supplier": b.get("supplier"),
				"bill_no": b.get("bill_no"),
				"posting_date": _iso(b.get("posting_date")),
				"due_date": _iso(b.get("due_date")),
				"status": b.get("status"),
				"docstatus": int(b.get("docstatus") or 0),
				"lane": lane,
				"amount": _num(b.get("base_grand_total") or b.get("grand_total")),
				"outstanding": _num(b.get("outstanding_amount")),
				"qbo_id": b.get("custom_qbo_id"),
				"not_in_qbo": bool(
					int(b.get("docstatus") or 0) == 1
					and not b.get("custom_qbo_id")
					and qbo_since
					and as_date(b.get("posting_date"))
					and as_date(b.get("posting_date")) >= qbo_since
				),
				"pos": pos,
				"receipts": prs,
				"kind": kind,
				"match": match,
				"variance": variance,
			}
		)
	bills = [
		b
		for b in bills
		if b["lane"] != "paid" or (as_date(b["posting_date"]) or today) >= today - timedelta(days=30)
	]

	# ---- landed cost ----
	pending = []
	for s in shipments:
		if not s["needs_lcv"]:
			continue
		included = [c for c in s["costs"] if c["in_lc"]]
		pending.append(
			{
				"shipment": s["name"],
				"receipt": s["receipts"][0] if s["receipts"] else None,
				"receipts": s["receipts"],
				"supplier": s["supplier"],
				"est": round(sum(c["est"] for c in included), 2),
				"actual": round(sum(c["actual"] or 0 for c in included), 2),
				"missing_bills": sorted({c["cost_type"] for c in included if c["actual"] is None}),
				"ready": bool(
					s["receipts"]
					and all(x == 1 for x in s["_receipt_status"])
					and all(c["actual"] is not None for c in included)
				),
				"delivered_on": s["delivered_on"],
			}
		)
	history = {}
	for h in raw.get("landed_history") or []:
		history.setdefault(h.get("item_code"), []).append(h)
	by_item, in_stock = [], 0.0
	stock = raw.get("stock") or {}
	for item, rows in sorted(history.items()):
		rows = sorted(rows, key=lambda r: str(r.get("posting_date") or ""))
		last = rows[-1]
		rate = _num(last.get("rate"))
		landed = landed_unit_cost(rate, last.get("qty"), last.get("landed_cost_voucher_amount"))
		ups = [
			uplift_pct(
				r.get("rate"),
				landed_unit_cost(r.get("rate"), r.get("qty"), r.get("landed_cost_voucher_amount")),
			)
			for r in rows
		]
		ups = [u for u in ups if u is not None]
		in_stock += max(0.0, landed - rate) * max(0.0, _num(stock.get(item)))
		by_item.append(
			{
				"item": item,
				"item_name": (items_info.get(item) or {}).get("item_name") or last.get("item_name"),
				"last_receipt": last.get("parent"),
				"purchase_rate": rate,
				"landed_rate": landed,
				"uplift_pct": uplift_pct(rate, landed),
				"avg_uplift_12m": round(sum(ups) / len(ups), 2) if ups else None,
			}
		)

	# ---- what to order ----
	def info(item):
		return _lead_info(item, raw, lead_fn)

	shortage_rows = shortages(
		raw.get("demand") or [], stock, raw.get("incoming") or {}, info, today, safety, raw.get("open_docs")
	)
	usage = raw.get("usage") or {}
	open_docs = raw.get("open_docs") or {}
	reorder = []
	for r in reorder_breaches(raw.get("bins") or [], raw.get("reorder_rows") or []):
		i = info(r["item"])
		r.update(
			{
				"item_name": (items_info.get(r["item"]) or {}).get("item_name"),
				"supplier": i["supplier"],
				"lead": i["lead"],
				"lead_src": i["lead_src"],
				"open_mr": (open_docs.get(r["item"]) or {}).get("mr"),
				"open_po": (open_docs.get(r["item"]) or {}).get("po")
				or (open_docs.get(r["item"]) or {}).get("draft_po"),
				"suggested_level": suggest_reorder_level(usage.get(r["item"]), i["lead"], safety),
			}
		)
		reorder.append(r)

	gaps = {"no_supplier": [], "no_lead": [], "no_reorder": [], "no_hts": [], "no_origin": []}
	reorder_items = {r.get("item") or r.get("parent") for r in raw.get("reorder_rows") or []}
	for item, it in sorted(items_info.items()):
		if (
			it.get("default_bom")
			or not int(it.get("is_purchase_item", 1) or 0)
			or int(it.get("disabled") or 0)
		):
			continue
		row = {"item": item, "item_name": it.get("item_name")}
		i = info(item)
		if not it.get("default_supplier"):
			gaps["no_supplier"].append(row)
		if not i["lead"]:
			gaps["no_lead"].append(row)
		if int(it.get("is_stock_item", 1) or 0) and item not in reorder_items:
			gaps["no_reorder"].append(
				dict(row, suggested_level=suggest_reorder_level(usage.get(item), i["lead"], safety))
			)
		if not it.get("customs_tariff_number"):
			gaps["no_hts"].append(row)
		if not it.get("country_of_origin"):
			gaps["no_origin"].append(row)

	# ---- suppliers ----
	sup = {}
	for p in pos_out:
		if p["docstatus"] != 1:
			continue
		s = sup.setdefault(
			p["supplier"],
			{"open": [], "amount": 0.0, "quoted": [], "actual": [], "on_time": [], "last": None},
		)
		if p["lane"] not in ("done",):
			s["open"].append(p["name"])
			s["amount"] += p["amount"] * (1 - min(p["per_received"], 100) / 100)
		if p["lead_src"] in ("quote", "po", "po line", "supplier") and p["lead_days"]:
			s["quoted"].append(p["lead_days"])
		if not s["last"] or (p["transaction_date"] or "") > s["last"]:
			s["last"] = p["transaction_date"]
	for r in receipts_out:
		if r["docstatus"] != 1:
			continue
		for name in r["pos"]:
			p = po_by_name.get(name)
			if not p or p["supplier"] not in sup:
				continue
			days = _days_between(p["transaction_date"], r["posting_date"])
			if days is not None:
				sup[p["supplier"]]["actual"].append(days)
			if p["eta"]:
				sup[p["supplier"]]["on_time"].append(as_date(r["posting_date"]) <= as_date(p["eta"]))
	defaults = raw.get("suppliers") or {}
	suppliers = []
	for name, s in sorted(sup.items(), key=lambda kv: -kv[1]["amount"]):
		suppliers.append(
			{
				"supplier": name,
				"open_pos": len(s["open"]),
				"open_amount": round(s["amount"], 2),
				"avg_quoted_lead": round(sum(s["quoted"]) / len(s["quoted"]), 1) if s["quoted"] else None,
				"avg_actual_lead": round(sum(s["actual"]) / len(s["actual"]), 1) if s["actual"] else None,
				"on_time_pct": round(sum(s["on_time"]) / len(s["on_time"]) * 100) if s["on_time"] else None,
				"last_po": s["last"],
				"default_lead": (defaults.get(name) or {}).get("ill_default_lead_time_days"),
			}
		)

	# ---- summary and decisions ----
	def count(rows, **match):
		return sum(1 for r in rows if all(r.get(k) == v for k, v in match.items()))

	ago = lambda n: today - timedelta(days=n)  # noqa: E731
	firm = [r for r in shortage_rows if r["short_firm"] > 0]
	open_po = [p for p in pos_out if p["docstatus"] == 1 and p["lane"] not in ("done", "on_hold")]
	summary = {
		"to_order": {"count": len(firm), "late": sum(1 for r in firm if r["late"])},
		"reorder": {"count": len(reorder)},
		"mrs": {"count": sum(1 for m in mrs if m["lane"] != "done"), "draft": count(mrs, lane="draft")},
		"quotes": {
			"out": sum(
				1 for q in quotes if q["lane"] in ("rfq_draft", "awaiting_reply", "quoted", "expiring")
			),
			"expiring": count(quotes, lane="expiring"),
		},
		"pos": {
			**{lane: count(pos_out, lane=lane) for lane in PO_LANES if lane not in ("done", "on_hold")},
			"overdue": sum(1 for p in pos_out if p["overdue"]),
			"count": len(open_po),
			"amount": round(sum(p["amount"] for p in open_po), 2),
		},
		"shipments": {lane: count(shipments, lane=lane) for lane in SHIPMENT_LANES if lane != "final"},
		"receipts": {
			"to_bill": sum(1 for r in receipts_out if r["docstatus"] == 1 and r["billed_pct"] < 100),
			"needs_lcv": count(receipts_out, lcv_status="needs_lcv"),
		},
		"bills": {
			"unpaid_amount": round(sum(b["outstanding"] for b in bills if b["docstatus"] == 1), 2),
			"overdue": count(bills, lane="overdue"),
			"not_in_qbo": sum(1 for b in bills if b["not_in_qbo"]),
			"count": sum(1 for b in bills if b["lane"] != "paid"),
		},
		"landed": {
			"needs_lcv": len(pending),
			"est_open_amount": round(sum(p["actual"] or p["est"] for p in pending), 2),
			"in_stock_amount": round(in_stock, 2),
		},
	}
	decisions = []
	_decision(
		decisions,
		"to_order_late",
		"Shortages past their order-by date",
		summary["to_order"]["late"],
		"bad",
		"order",
	)
	_decision(decisions, "reorder_breach", "Items below their reorder level", len(reorder), "warn", "order")
	_decision(
		decisions,
		"mr_unactioned",
		"Material requests with no quote or order after 2 days",
		sum(
			1
			for m in mrs
			if m["lane"] == "to_quote" and m["transaction_date"] and as_date(m["transaction_date"]) < ago(2)
		),
		"warn",
		"requests",
		"to_quote",
	)
	_decision(
		decisions,
		"quote_expiring",
		"Supplier quotes about to expire",
		count(quotes, lane="expiring"),
		"warn",
		"quotes",
		"expiring",
	)
	_decision(
		decisions,
		"rfq_no_reply",
		"RFQs with no reply after 5 days",
		sum(
			1
			for q in quotes
			if q["lane"] == "awaiting_reply"
			and q["transaction_date"]
			and as_date(q["transaction_date"]) < ago(5)
		),
		"warn",
		"quotes",
		"awaiting_reply",
	)
	_decision(
		decisions,
		"po_draft_old",
		"Draft purchase orders older than 2 days",
		sum(
			1
			for p in pos_out
			if p["lane"] == "draft" and as_date(p["creation"] or p["transaction_date"] or today) < ago(2)
		),
		"warn",
		"pos",
		"draft",
	)
	_decision(
		decisions,
		"po_not_sent",
		"Submitted POs not sent to the vendor",
		count(pos_out, lane="not_sent"),
		"bad",
		"pos",
		"not_sent",
	)
	_decision(
		decisions,
		"po_unconfirmed",
		f"POs sent but not confirmed after {warn_confirm} days",
		sum(
			1
			for p in pos_out
			if p["lane"] == "awaiting_confirmation"
			and as_date(p["sent_on"] or p["transaction_date"] or today) < ago(warn_confirm)
		),
		"warn",
		"pos",
		"awaiting_confirmation",
	)
	_decision(
		decisions, "po_overdue", "POs past their ETA, not received", summary["pos"]["overdue"], "bad", "pos"
	)
	_decision(
		decisions,
		"po_will_miss",
		"POs arriving after the sales order needs them",
		sum(1 for p in pos_out if p["will_miss"]),
		"bad",
		"pos",
	)
	_decision(
		decisions,
		"shipment_eta_passed",
		"Shipments past their ETA",
		sum(
			1
			for s in shipments
			if s["lane"] in ("planned", "moving", "customs", "arriving")
			and s["eta"]
			and as_date(s["eta"]) < today
		),
		"warn",
		"shipments",
	)
	_decision(
		decisions,
		"receipt_no_bill",
		f"Receipts with no bill after {warn_bill} days",
		sum(
			1
			for r in receipts_out
			if r["docstatus"] == 1
			and r["billed_pct"] < 100
			and r["posting_date"]
			and as_date(r["posting_date"]) < ago(warn_bill)
		),
		"warn",
		"receipts",
	)
	_decision(
		decisions,
		"bill_overdue",
		"Overdue vendor bills",
		summary["bills"]["overdue"],
		"bad",
		"bills",
		"overdue",
	)
	_decision(
		decisions,
		"bill_not_in_qbo",
		"Bills not in QuickBooks",
		summary["bills"]["not_in_qbo"],
		"bad",
		"bills",
	)
	late_lcv = [p for p in pending if p["delivered_on"] and as_date(p["delivered_on"]) < ago(warn_lcv)]
	_decision(
		decisions,
		"needs_lcv",
		"Shipments whose freight and duty are not in stock value yet",
		len(pending),
		"bad" if late_lcv else "warn",
		"landed",
	)
	_decision(
		decisions,
		"cost_variance",
		"Shipments costing 15%+ more than estimated",
		sum(
			1
			for s in shipments
			if any(c["actual"] is not None for c in s["costs"])
			and sum(c["est"] for c in s["costs"] if c["actual"] is not None) > 0
			and s["actual_cost"] > 1.15 * sum(c["est"] for c in s["costs"] if c["actual"] is not None)
		),
		"warn",
		"shipments",
	)

	for s in shipments:
		s.pop("_landed_basis", None)
		s.pop("_receipt_status", None)
	board = {
		"today": today.isoformat(),
		"money": bool(money),
		"can_edit": bool(can_edit),
		"settings": {
			k: settings.get(k)
			for k in (
				"quote_expiry_warn_days",
				"vendor_confirm_warn_days",
				"receipt_bill_warn_days",
				"lcv_warn_days",
				"safety_days",
				"default_warehouse",
				"company",
			)
		},
		"summary": summary,
		"decisions": decisions,
		"shortages": shortage_rows,
		"reorder": reorder,
		"mrs": mrs,
		"quotes": quotes,
		"quote_compare": quote_compare,
		"pos": pos_out,
		"shipments": shipments,
		"receipts": receipts_out,
		"bills": bills,
		"landed": {
			"pending": pending,
			"vouchers": vouchers,
			"by_item": by_item,
			"in_stock_amount": round(in_stock, 2),
		},
		"gaps": gaps,
		"suppliers": suppliers,
		"missing": sorted(set(raw.get("missing") or [])),
	}
	return board if money else scrub(board)


# ---------------------------------------------------------------------------
# Reading ERPNext (one query per doctype, bulk `in` filters)
# ---------------------------------------------------------------------------


def _roles():
	return set(frappe.get_roles(frappe.session.user))


def _exists(doctype):
	return bool(frappe.db.exists("DocType", doctype))


def _children(child, parents, wanted, parenttype=None):
	"""Child rows grouped by parent. Parents were read with the user's permissions."""
	if not parents or not _exists(child):
		return {}
	filters = {"parent": ["in", list(parents)]}
	if parenttype:
		filters["parenttype"] = parenttype
	out = {}
	for row in frappe.get_all(
		child, filters=filters, fields=_fields(child, ["parent", *wanted]), limit_page_length=0
	):
		out.setdefault(row.parent, []).append(row)
	return out


class _Reader:
	def __init__(self, today):
		self.today = today
		self.cutoff = today - timedelta(days=WINDOW_DAYS)
		self.missing = []

	def parents(self, doctype, wanted, filters=None, or_filters=None, order_by="modified desc"):
		"""Permission-aware list; a doctype the user can't read (or that's missing) is skipped."""
		if not _exists(doctype):
			self.missing.append(doctype)
			return []
		try:
			return frappe.get_list(
				doctype,
				fields=_fields(doctype, wanted),
				filters=filters or {},
				or_filters=or_filters,
				order_by=order_by,
				limit_page_length=0,
			)
		except Exception:
			self.missing.append(doctype)
			return []

	def with_children(self, rows, child, key, wanted, parenttype):
		kids = _children(child, [r.name for r in rows], wanted, parenttype)
		for r in rows:
			r[key] = kids.get(r.name, [])
		return rows


def _demand(reader, open_so):
	"""Firm and draft demand rows for shortages, plus the item codes they touch."""
	today = reader.today
	submitted = {s.name: s for s in open_so}
	drafts = reader.parents(
		"Sales Order",
		["name", "delivery_date", "transaction_date"],
		filters={"docstatus": 0, "modified": [">=", reader.cutoff]},
	)
	so_names = list(submitted) + [d.name for d in drafts]
	lines = _children(
		"Sales Order Item",
		so_names,
		["item_code", "qty", "stock_qty", "delivered_qty", "conversion_factor", "delivery_date"],
		"Sales Order",
	)
	wos = work_orders_for(list(submitted)) if submitted else []
	active = [w for w in wos if w.get("status") in ("Draft", "Not Started", "In Process")]
	wo_items = _children(
		"Work Order Item", [w.name for w in active], ["item_code", "required_qty", "transferred_qty"]
	)
	wo_built = set()
	if wos:
		for w in frappe.get_all(
			"Work Order",
			filters={"name": ["in", [w.name for w in wos]]},
			fields=["name", "sales_order", "production_item"],
			limit_page_length=0,
		):
			wo_built.add((w.sales_order, w.production_item))
	codes = {line.item_code for rows in lines.values() for line in rows}
	boms = {}
	if codes:
		for it in frappe.get_all(
			"Item",
			filters={"name": ["in", list(codes)], "default_bom": ["is", "set"]},
			fields=["name", "default_bom"],
			limit_page_length=0,
		):
			boms[it.name] = it.default_bom
	bom_lines, bom_qty = {}, {}
	if boms:
		for b in frappe.get_all(
			"BOM",
			filters={"name": ["in", list(set(boms.values()))]},
			fields=["name", "quantity"],
			limit_page_length=0,
		):
			bom_qty[b.name] = _num(b.quantity) or 1
		bom_lines = _children("BOM Item", list(bom_qty), ["item_code", "stock_qty"], "BOM")
	demand = []
	for so, rows in lines.items():
		head = submitted.get(so) or next((d for d in drafts if d.name == so), None)
		draft = so not in submitted
		for line in rows:
			factor = _num(line.conversion_factor) or 1
			open_qty = _num(line.stock_qty or _num(line.qty) * factor) - _num(line.delivered_qty) * factor
			if open_qty <= 0:
				continue
			need = as_date(line.delivery_date) or as_date(head and head.get("delivery_date")) or today
			if (so, line.item_code) in wo_built and not draft:
				continue  # its work order's materials carry the demand
			bom = boms.get(line.item_code)
			if bom:
				per = bom_qty.get(bom, 1)
				for comp in bom_lines.get(bom, []):
					demand.append(
						{
							"item": comp.item_code,
							"qty": open_qty * _num(comp.stock_qty) / per,
							"need_by": need,
							"src": "Sales Order",
							"doc": so,
							"draft": draft,
						}
					)
			else:
				demand.append(
					{
						"item": line.item_code,
						"qty": open_qty,
						"need_by": need,
						"src": "Sales Order",
						"doc": so,
						"draft": draft,
					}
				)
	for w in active:
		head = submitted.get(w.sales_order)
		need = as_date(head and head.get("delivery_date")) or today
		for row in wo_items.get(w.name, []):
			qty = _num(row.required_qty) - _num(row.transferred_qty)
			if qty > 0:
				demand.append(
					{
						"item": row.item_code,
						"qty": qty,
						"need_by": need,
						"src": "Work Order",
						"doc": w.name,
						"draft": False,
					}
				)
	return demand


def _usage(items, days):
	"""Average outbound stock per workday-ish day over the look-back window."""
	if not items or not days:
		return {}
	start = frappe.utils.add_days(frappe.utils.nowdate(), -int(days))
	rows = frappe.db.sql(
		"""select item_code, -sum(actual_qty) as qty from `tabStock Ledger Entry`
		where item_code in %(items)s and posting_date >= %(start)s and actual_qty < 0 and is_cancelled = 0
		group by item_code""",
		{"items": tuple(items), "start": start},
		as_dict=True,
	)
	workdays = max(1, round(int(days) * 5 / 7))
	return {r.item_code: _num(r.qty) / workdays for r in rows}


def load(today, settings):
	"""Every raw row the board needs."""
	reader = _Reader(today)
	cutoff = reader.cutoff
	raw = {"missing": reader.missing}

	mrs = reader.parents(
		"Material Request",
		["name", "status", "docstatus", "transaction_date", "schedule_date", "material_request_type"],
		filters={
			"material_request_type": "Purchase",
			"docstatus": ["<", 2],
			"status": ["not in", ["Stopped", "Cancelled"]],
		},
		or_filters=[["status", "not in", ["Received", "Ordered"]], ["modified", ">=", cutoff]],
	)
	raw["mrs"] = reader.with_children(
		mrs,
		"Material Request Item",
		"items",
		["item_code", "qty", "ordered_qty", "sales_order"],
		"Material Request",
	)
	rfqs = reader.parents(
		"Request for Quotation",
		["name", "status", "docstatus", "transaction_date", "schedule_date"],
		filters={"docstatus": ["<", 2]},
		or_filters=[["docstatus", "=", 0], ["modified", ">=", cutoff]],
	)
	reader.with_children(
		rfqs,
		"Request for Quotation Supplier",
		"suppliers",
		["supplier", "quote_status", "email_sent"],
		"Request for Quotation",
	)
	raw["rfqs"] = reader.with_children(
		rfqs,
		"Request for Quotation Item",
		"items",
		["item_code", "material_request"],
		"Request for Quotation",
	)
	sqs = reader.parents(
		"Supplier Quotation",
		[
			"name",
			"supplier",
			"status",
			"docstatus",
			"transaction_date",
			"valid_till",
			"grand_total",
			"base_grand_total",
		],
		filters={"docstatus": ["<", 2]},
		or_filters=[["status", "in", ["Draft", "Submitted"]], ["modified", ">=", cutoff]],
	)
	raw["sqs"] = reader.with_children(
		sqs,
		"Supplier Quotation Item",
		"items",
		[
			"item_code",
			"item_name",
			"qty",
			"rate",
			"lead_time_days",
			"expected_delivery_date",
			"request_for_quotation",
			"material_request",
		],
		"Supplier Quotation",
	)
	pos = reader.parents(
		"Purchase Order",
		[
			"name",
			"supplier",
			"status",
			"docstatus",
			"creation",
			"transaction_date",
			"schedule_date",
			"per_received",
			"per_billed",
			"base_net_total",
			"base_grand_total",
			*purchasing_fields(),
		],
		filters={"docstatus": ["<", 2]},
		or_filters=[
			["status", "not in", ["Completed", "Closed", "Cancelled", "Delivered"]],
			["modified", ">=", cutoff],
		],
	)
	raw["pos"] = reader.with_children(
		pos,
		"Purchase Order Item",
		"items",
		[
			"name",
			"item_code",
			"item_name",
			"qty",
			"received_qty",
			"rate",
			"base_net_amount",
			"schedule_date",
			"material_request",
			"supplier_quotation",
			"sales_order",
			"ill_eta",
			"ill_est_lead_time_days",
		],
		"Purchase Order",
	)
	receipts = reader.parents(
		"Purchase Receipt",
		[
			"name",
			"supplier",
			"status",
			"docstatus",
			"posting_date",
			"per_billed",
			"base_net_total",
			"base_grand_total",
		],
		filters={"docstatus": ["<", 2]},
		or_filters=[["status", "in", ["Draft", "To Bill", "Partly Billed"]], ["posting_date", ">=", cutoff]],
	)
	raw["receipts"] = reader.with_children(
		receipts,
		"Purchase Receipt Item",
		"items",
		[
			"item_code",
			"qty",
			"rate",
			"purchase_order",
			"landed_cost_voucher_amount",
			"base_net_amount",
			"valuation_rate",
		],
		"Purchase Receipt",
	)
	invoices = reader.parents(
		"Purchase Invoice",
		[
			"name",
			"supplier",
			"bill_no",
			"posting_date",
			"due_date",
			"status",
			"docstatus",
			"is_return",
			"base_grand_total",
			"base_net_total",
			"outstanding_amount",
			"custom_qbo_id",
		],
		filters={"docstatus": ["<", 2]},
		or_filters=[["outstanding_amount", ">", 0], ["posting_date", ">=", cutoff], ["docstatus", "=", 0]],
	)
	raw["invoices"] = reader.with_children(
		invoices,
		"Purchase Invoice Item",
		"items",
		[
			"item_code",
			"qty",
			"rate",
			"purchase_order",
			"purchase_receipt",
			"expense_account",
			"base_net_amount",
		],
		"Purchase Invoice",
	)
	lcvs = reader.parents(
		"Landed Cost Voucher",
		["name", "docstatus", "posting_date", "total_taxes_and_charges"],
		filters={"docstatus": ["<", 2]},
		or_filters=[["docstatus", "=", 0], ["posting_date", ">=", cutoff - timedelta(days=WINDOW_DAYS)]],
	)
	lcv_receipts = _children(
		"Landed Cost Purchase Receipt", [v.name for v in lcvs], ["receipt_document"], "Landed Cost Voucher"
	)
	for v in lcvs:
		v["receipts"] = [r.receipt_document for r in lcv_receipts.get(v.name, [])]
	raw["lcvs"] = lcvs
	shipments = reader.parents(
		purchasing.SHIPMENT,
		["name", "status", "modified", *purchasing_shipment_fields()],
		filters={"status": ["!=", "Cancelled"]},
		or_filters=[["status", "not in", ["Delivered", "Costs final"]], ["modified", ">=", cutoff]],
	)
	if shipments:
		reader.with_children(
			shipments,
			"ilL-Child-Shipment-PO",
			"purchase_orders",
			["purchase_order", "supplier", "po_value", "share_pct"],
			purchasing.SHIPMENT,
		)
		reader.with_children(
			shipments,
			"ilL-Child-Shipment-Receipt",
			"receipts",
			["purchase_receipt", "posting_date", "value"],
			purchasing.SHIPMENT,
		)
		reader.with_children(
			shipments, "ilL-Child-Shipment-Cost", "costs", ["name", *COST_FIELDS], purchasing.SHIPMENT
		)
		reader.with_children(
			shipments,
			"ilL-Child-Shipment-LCV",
			"landed_cost_vouchers",
			["landed_cost_voucher", "lcv_docstatus"],
			purchasing.SHIPMENT,
		)
	raw["shipments"] = shipments

	# demand, stock and items
	open_so = open_orders()
	raw["demand"] = _demand(reader, open_so)
	raw["so_dates"] = {s.name: s.get("delivery_date") for s in open_so}
	po_sos = {i.sales_order for p in pos for i in p["items"] if i.get("sales_order")} - set(raw["so_dates"])
	if po_sos:
		for s in frappe.get_all(
			"Sales Order",
			filters={"name": ["in", list(po_sos)]},
			fields=["name", "delivery_date"],
			limit_page_length=0,
		):
			raw["so_dates"][s.name] = s.delivery_date
	codes = {d["item"] for d in raw["demand"]}
	for group in ("mrs", "sqs", "pos", "receipts"):
		for doc in raw[group]:
			codes.update(i.get("item_code") for i in doc.get("items") or [] if i.get("item_code"))
	reorder_rows = frappe.get_all(
		"Item Reorder",
		filters={"parenttype": "Item"},
		fields=[
			"parent",
			"warehouse",
			"warehouse_reorder_level",
			"warehouse_reorder_qty",
			"material_request_type",
		],
		limit_page_length=0,
	)
	raw["reorder_rows"] = reorder_rows
	codes.update(r.parent for r in reorder_rows)
	bins = frappe.get_all(
		"Bin",
		filters={"actual_qty": [">", 0]},
		fields=["item_code", "warehouse", "actual_qty", "projected_qty"],
		limit_page_length=0,
	)
	reorder_items = {r.parent for r in reorder_rows}
	if reorder_items:
		bins += frappe.get_all(
			"Bin",
			filters={"item_code": ["in", list(reorder_items)], "actual_qty": ["<=", 0]},
			fields=["item_code", "warehouse", "actual_qty", "projected_qty"],
			limit_page_length=0,
		)
	raw["bins"] = bins
	codes.update(b.item_code for b in bins)
	codes.discard(None)
	codes = sorted(codes)
	raw["stock"] = stock_on_hand(codes)
	raw["incoming"] = incoming_purchases(codes)
	items = {}
	if codes:
		for it in frappe.get_all(
			"Item",
			filters={"name": ["in", codes]},
			fields=_fields(
				"Item",
				[
					"name",
					"item_name",
					"item_group",
					"lead_time_days",
					"customs_tariff_number",
					"country_of_origin",
					"is_stock_item",
					"is_purchase_item",
					"default_bom",
					"disabled",
				],
			),
			limit_page_length=0,
		):
			items[it.name] = dict(it)
	raw["items"] = items
	raw["landed_history"] = _landed_history(today)

	open_docs = {}
	for p in pos:
		for i in p["items"]:
			slot = open_docs.setdefault(i.item_code, {})
			if int(p.docstatus or 0) == 0:
				slot.setdefault("draft_po", p.name)
			elif p.status not in ("Completed", "Closed", "Delivered") and _num(i.received_qty) < _num(i.qty):
				slot.setdefault("po", p.name)
	for m in raw["mrs"]:
		if m.status in ("Draft", "Pending", "Partially Ordered") or int(m.docstatus or 0) == 0:
			for i in m["items"]:
				open_docs.setdefault(i.item_code, {}).setdefault("mr", m.name)
	raw["open_docs"] = open_docs
	supplier_names = sorted({p.supplier for p in pos if p.supplier})
	raw["suppliers"] = {}
	if supplier_names:
		for s in frappe.get_all(
			"Supplier",
			filters={"name": ["in", supplier_names]},
			fields=_fields("Supplier", ["name", "supplier_group", "ill_default_lead_time_days"]),
			limit_page_length=0,
		):
			raw["suppliers"][s.name] = s
	paint_group = None
	if _exists("ilL-Production-Settings"):
		paint_group = frappe.db.get_single_value("ilL-Production-Settings", "paint_supplier_group")
	raw["paint_suppliers"] = {
		n for n, s in raw["suppliers"].items() if paint_group and s.get("supplier_group") == paint_group
	}
	try:
		from illumenate_lighting.illumenate_lighting.api import qbo_bills

		since = (qbo_bills.queue_filters() or {}).get("posting_date")
		raw["qbo_since"] = since[1] if since else None
	except Exception:
		raw["qbo_since"] = None
	try:
		purchased = [c for c in codes if not items.get(c, {}).get("default_bom")]
		raw["usage"] = _usage(purchased, settings.get("reorder_lookback_days"))
	except Exception:
		raw["usage"] = {}
	return raw


def _landed_history(today):
	rows = frappe.get_all(
		"Purchase Receipt Item",
		filters={
			"docstatus": 1,
			"landed_cost_voucher_amount": [">", 0],
			"creation": [">=", today - timedelta(days=365)],
		},
		fields=[
			"parent",
			"item_code",
			"item_name",
			"qty",
			"rate",
			"valuation_rate",
			"landed_cost_voucher_amount",
		],
		limit_page_length=0,
	)
	if not rows:
		return []
	dates = {
		r.name: r.posting_date
		for r in frappe.get_all(
			"Purchase Receipt",
			filters={"name": ["in", list({r.parent for r in rows})]},
			fields=["name", "posting_date"],
			limit_page_length=0,
		)
	}
	for r in rows:
		r["posting_date"] = dates.get(r.parent)
	return rows


def purchasing_fields():
	return list(PO_TRACKING_FIELDS)


def purchasing_shipment_fields():
	return [
		"supplier",
		"freight_mode",
		"forwarder",
		"customs_broker",
		"tracking_no",
		"tracking_url",
		"container_no",
		"incoterm",
		"port_of_loading",
		"port_of_entry",
		"entry_no",
		"etd",
		"atd",
		"eta",
		"ata",
		"delivered_on",
		"notes",
	]


def build_board(today=None, money=True, can_edit=False):
	today = as_date(today or frappe.utils.nowdate())
	settings = purchasing.read_settings()
	raw = load(today, settings)
	suppliers = {p.supplier for p in raw["pos"] if p.supplier}
	suppliers |= {s.supplier for s in raw["sqs"] if s.supplier}
	leads = purchasing.LeadTimes(list(raw["items"]), suppliers, settings=settings, today=today)
	for code, info in raw["items"].items():
		info["default_supplier"] = leads.supplier_for(code)

	def lead_fn(item, supplier=None, po_row=None, po=None):
		return leads.get(item, supplier, po_row=po_row, po=po)

	return assemble(raw, settings, today, lead_fn, money=money, can_edit=can_edit)


@frappe.whitelist()
def get_board():
	roles = _roles()
	if not roles & VIEW_ROLES:
		frappe.throw(
			_("You need the Command Center Viewer role to see the purchasing board."), frappe.PermissionError
		)
	return build_board(money=bool(roles & MONEY_ROLES), can_edit=bool(roles & EDIT_ROLES))


# ---------------------------------------------------------------------------
# Writes (drafts and tracking fields only; nothing is submitted)
# ---------------------------------------------------------------------------


def _need_edit():
	if not _roles() & EDIT_ROLES:
		frappe.throw(
			_("You have view-only access. Ask Kevin for the Command Center Editor or Purchase User role."),
			frappe.PermissionError,
		)


def _arg(value, default=None):
	if isinstance(value, str):
		try:
			return json.loads(value)
		except ValueError:
			frappe.throw(_("Could not read the request."))
	return default if value is None else value


def _only(values, allowed, what):
	bad = sorted(k for k in values if k not in allowed)
	if bad:
		frappe.throw(_("Not editable from the Command Center on {0}: {1}").format(what, ", ".join(bad)))
	return values


def _changes(doc, values):
	changed = []
	for key, value in values.items():
		old = doc.get(key)
		if str(old if old is not None else "") != str(value if value is not None else ""):
			changed.append(
				f"{key.replace('ill_', '')}: {old or '—'} -> {value if value not in (None, '') else '—'}"
			)
			doc.set(key, value if value != "" else None)
	return changed


def _insert(doc, label):
	doc.insert()
	purchasing.comment(doc.doctype, doc.name, f"draft {label} created by {frappe.session.user}")
	return {"name": doc.name, "doctype": doc.doctype}


@frappe.whitelist(methods=["POST"])
def update_po_tracking(po, values=None):
	"""Write the vendor-tracking fields (only those) on a Purchase Order, submitted or not."""
	_need_edit()
	values = _only(_arg(values, {}), PO_TRACKING_FIELDS, "a purchase order")
	doc = frappe.get_doc("Purchase Order", po)
	doc.check_permission("write")
	if doc.docstatus == 2:
		frappe.throw(_("{0} is cancelled.").format(po))
	changed = _changes(doc, values)
	if changed:
		doc.save()
		purchasing.comment(
			"Purchase Order",
			doc.name,
			"tracking edited by " + frappe.session.user + " (" + "; ".join(changed)[:900] + ")",
		)
	return {"name": doc.name, "changed": len(changed)}


@frappe.whitelist(methods=["POST"])
def update_po_line_tracking(po, rows=None):
	"""Line lead time / ETA overrides: rows [{name, ill_est_lead_time_days, ill_eta}]."""
	_need_edit()
	rows = _arg(rows, [])
	doc = frappe.get_doc("Purchase Order", po)
	doc.check_permission("write")
	if doc.docstatus == 2:
		frappe.throw(_("{0} is cancelled.").format(po))
	lines = {r.name: r for r in doc.get("items") or []}
	changed = []
	for row in rows:
		values = _only({k: v for k, v in row.items() if k != "name"}, PO_LINE_FIELDS, "a purchase order line")
		line = lines.get(row.get("name"))
		if not line:
			frappe.throw(_("Line {0} is not on {1}.").format(row.get("name"), po))
		changed += [f"{line.item_code} {c}" for c in _changes(line, values)]
	if changed:
		doc.save()
		purchasing.comment(
			"Purchase Order",
			doc.name,
			"line tracking edited by " + frappe.session.user + " (" + "; ".join(changed)[:900] + ")",
		)
	return {"name": doc.name, "changed": len(changed)}


def _set_int(doctype, name, field, days):
	_need_edit()
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("write")
	days = int(days) if days not in (None, "") else None
	if days is not None and days < 0:
		frappe.throw(_("Lead time can't be negative."))
	changed = _changes(doc, {field: days})
	if changed:
		doc.save()
		purchasing.comment(doctype, doc.name, f"{changed[0]} set by {frappe.session.user}")
	return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
def set_item_lead_time(item, days=None):
	return _set_int("Item", item, "lead_time_days", days)


@frappe.whitelist(methods=["POST"])
def set_supplier_lead_time(supplier, days=None):
	if not _has_field("Supplier", "ill_default_lead_time_days"):
		frappe.throw(_("Supplier lead times arrive with the next app deploy."))
	return _set_int("Supplier", supplier, "ill_default_lead_time_days", days)


@frappe.whitelist(methods=["POST"])
def draft_material_request(items=None):
	"""One draft Purchase Material Request for [{item, qty, schedule_date}].

	Rows never carry ``sales_order``: material_planning would then insist on exploding the
	order's pinned BOM (see validate_material_request).
	"""
	_need_edit()
	items = [i for i in _arg(items, []) if i.get("item") and _num(i.get("qty")) > 0]
	if not items:
		frappe.throw(_("Pick at least one item with a quantity."))
	settings = purchasing.read_settings()
	today = frappe.utils.nowdate()
	dates = [str(i.get("schedule_date"))[:10] for i in items if i.get("schedule_date")]
	date = max(min(dates), today) if dates else frappe.utils.add_days(today, 14)
	warehouse = settings.get("default_warehouse")
	doc = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"company": settings.get("company"),
			"transaction_date": today,
			"schedule_date": date,
			"set_warehouse": warehouse,
			"items": [
				{
					"item_code": i["item"],
					"qty": math.ceil(_num(i["qty"]) - 1e-9),
					"schedule_date": max(str(i.get("schedule_date") or date)[:10], today),
					"warehouse": warehouse,
				}
				for i in items
			],
		}
	)
	return _insert(doc, "material request")


@frappe.whitelist(methods=["POST"])
def make_rfq(material_request, suppliers=None):
	_need_edit()
	suppliers = [s for s in _arg(suppliers, []) if s]
	if not suppliers:
		frappe.throw(_("Pick at least one supplier to ask."))
	from erpnext.stock.doctype.material_request.material_request import make_request_for_quotation

	frappe.get_doc("Material Request", material_request).check_permission("read")
	doc = make_request_for_quotation(material_request)
	doc.set("suppliers", [])
	for s in suppliers:
		doc.append("suppliers", {"supplier": s})
	if doc.meta.has_field("message_for_supplier") and not doc.get("message_for_supplier"):
		doc.message_for_supplier = "Please quote the items below with your price and lead time."
	return _insert(doc, f"RFQ from {material_request}")


@frappe.whitelist(methods=["POST"])
def make_supplier_quotation(material_request=None, rfq=None, supplier=None):
	_need_edit()
	if not supplier:
		frappe.throw(_("Pick the supplier whose quote you are entering."))
	if rfq:
		from erpnext.buying.doctype.request_for_quotation.request_for_quotation import (
			make_supplier_quotation_from_rfq,
		)

		frappe.get_doc("Request for Quotation", rfq).check_permission("read")
		doc = make_supplier_quotation_from_rfq(rfq, for_supplier=supplier)
	elif material_request:
		from erpnext.stock.doctype.material_request.material_request import make_supplier_quotation as mapper

		frappe.get_doc("Material Request", material_request).check_permission("read")
		doc = mapper(material_request)
		doc.supplier = supplier
	else:
		frappe.throw(_("Start from a material request or an RFQ."))
	return _insert(doc, f"supplier quotation from {rfq or material_request}")


@frappe.whitelist(methods=["POST"])
def make_po(supplier_quotation=None, material_request=None, supplier=None):
	_need_edit()
	if supplier_quotation:
		sq = frappe.get_doc("Supplier Quotation", supplier_quotation)
		sq.check_permission("read")
		if sq.docstatus != 1:
			frappe.throw(
				_("Submit {0} in the desk first; only a submitted quote converts.").format(supplier_quotation)
			)
		from erpnext.buying.doctype.supplier_quotation.supplier_quotation import make_purchase_order

		doc = make_purchase_order(supplier_quotation)
	elif material_request:
		if not supplier:
			frappe.throw(_("Pick a supplier to order from."))
		from erpnext.stock.doctype.material_request.material_request import make_purchase_order

		frappe.get_doc("Material Request", material_request).check_permission("read")
		doc = make_purchase_order(material_request)
		doc.supplier = supplier
	else:
		frappe.throw(_("Start from a supplier quotation or a material request."))
	# before_insert runs purchasing.prefill_po_tracking (lead time, ETA, vendor status)
	return _insert(doc, f"purchase order from {supplier_quotation or material_request}")


def _submitted_po(po):
	doc = frappe.get_doc("Purchase Order", po)
	doc.check_permission("read")
	if doc.docstatus != 1:
		frappe.throw(_("Submit purchase order {0} in the desk first.").format(po))
	return doc


@frappe.whitelist(methods=["POST"])
def make_receipt(po, shipment=None):
	_need_edit()
	_submitted_po(po)
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

	result = _insert(make_purchase_receipt(po), f"purchase receipt from {po}")
	if shipment:
		ship = frappe.get_doc(purchasing.SHIPMENT, shipment)
		ship.check_permission("write")
		if not any(r.purchase_receipt == result["name"] for r in ship.get("receipts") or []):
			ship.append("receipts", {"purchase_receipt": result["name"]})
			ship.save()
	return result


@frappe.whitelist(methods=["POST"])
def make_invoice(po=None, purchase_receipt=None):
	_need_edit()
	if purchase_receipt:
		pr = frappe.get_doc("Purchase Receipt", purchase_receipt)
		pr.check_permission("read")
		if pr.docstatus != 1:
			frappe.throw(_("Submit purchase receipt {0} in the desk first.").format(purchase_receipt))
		from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice

		doc = make_purchase_invoice(purchase_receipt)
	elif po:
		_submitted_po(po)
		from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice

		doc = make_purchase_invoice(po)
	else:
		frappe.throw(_("Start from a purchase order or a receipt."))
	return _insert(doc, f"purchase invoice from {purchase_receipt or po}")


def _hts_lines(po_names):
	"""Value per PO line with its HTS duty rates, for the duty / tariff estimate."""
	lines = frappe.get_all(
		"Purchase Order Item",
		filters={"parent": ["in", po_names]},
		fields=["item_code", "base_net_amount"],
		limit_page_length=0,
	)
	codes = sorted({line.item_code for line in lines})
	if not codes or not _has_field("Customs Tariff Number", "ill_duty_rate_pct"):
		return []
	hts = {
		i.name: i.customs_tariff_number
		for i in frappe.get_all(
			"Item",
			filters={"name": ["in", codes]},
			fields=["name", "customs_tariff_number"],
			limit_page_length=0,
		)
		if i.customs_tariff_number
	}
	if not hts:
		return []
	rates = {
		r.name: r
		for r in frappe.get_all(
			"Customs Tariff Number",
			filters={"name": ["in", list(set(hts.values()))]},
			fields=["name", "ill_duty_rate_pct", "ill_additional_tariff_pct"],
			limit_page_length=0,
		)
	}
	out = []
	for line in lines:
		rate = rates.get(hts.get(line.item_code))
		if rate:
			out.append(
				{
					"value": line.base_net_amount,
					"duty_pct": rate.ill_duty_rate_pct,
					"tariff_pct": rate.ill_additional_tariff_pct,
				}
			)
	return out


@frappe.whitelist(methods=["POST"])
def create_shipment(pos=None, values=None):
	"""New inbound shipment for these POs, with cost lines estimated from settings and HTS rates."""
	_need_edit()
	pos = [p for p in _arg(pos, []) if p]
	values = _only(_arg(values, {}), SHIPMENT_FIELDS, "a shipment")
	heads = frappe.get_list(
		"Purchase Order",
		filters={"name": ["in", pos], "docstatus": 1},
		fields=[
			"name",
			"supplier",
			"base_net_total",
			*(["ill_freight_mode"] if _has_field("Purchase Order", "ill_freight_mode") else []),
		],
		limit_page_length=0,
	)
	if not heads:
		frappe.throw(_("Pick at least one submitted purchase order."))
	settings = purchasing.read_settings()
	goods = sum(_num(h.base_net_total) for h in heads)
	mode = values.get("freight_mode") or next(
		(h.get("ill_freight_mode") for h in heads if h.get("ill_freight_mode")), None
	)
	doc = frappe.get_doc(
		{
			"doctype": purchasing.SHIPMENT,
			"status": "Planned",
			"supplier": heads[0].supplier,
			"freight_mode": mode,
			**values,
			"purchase_orders": [
				{"purchase_order": h.name, "supplier": h.supplier, "po_value": h.base_net_total}
				for h in heads
			],
			"costs": purchasing.estimate_costs(goods, settings, _hts_lines([h.name for h in heads]), mode),
		}
	)
	doc.insert()
	purchasing.comment(
		purchasing.SHIPMENT,
		doc.name,
		f"created by {frappe.session.user} for {', '.join(h.name for h in heads)}",
	)
	return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
def update_shipment(name, values=None, costs=None, pos=None):
	"""Header fields, and (when given) the full list of cost lines and POs."""
	_need_edit()
	values = _only(_arg(values, {}), SHIPMENT_FIELDS, "a shipment")
	doc = frappe.get_doc(purchasing.SHIPMENT, name)
	doc.check_permission("write")
	changed = _changes(doc, values)
	costs = _arg(costs, None)
	if costs is not None:
		rows = []
		for row in costs:
			clean = _only({k: v for k, v in row.items() if k != "name"}, COST_FIELDS, "a shipment cost line")
			if not clean.get("cost_type"):
				frappe.throw(_("Every cost line needs a cost type."))
			rows.append(clean)
		doc.set("costs", rows)
		changed.append(f"{len(rows)} cost lines")
	pos = _arg(pos, None)
	if pos is not None:
		doc.set("purchase_orders", [{"purchase_order": p} for p in pos if p])
		changed.append(f"{len(pos)} purchase orders")
	if changed:
		doc.save()
		purchasing.comment(
			purchasing.SHIPMENT,
			doc.name,
			"edited by " + frappe.session.user + " (" + "; ".join(changed)[:900] + ")",
		)
	return {"name": doc.name}


def _vendor_invoice_table(meta):
	"""(fieldname, link field) of a vendor-invoice table on Landed Cost Voucher, if this site has one."""
	for field in meta.get_table_fields():
		child = frappe.get_meta(field.options)
		for candidate in ("vendor_invoice", "purchase_invoice"):
			if child.has_field(candidate) and "vendor" in (field.fieldname + field.options).lower():
				return field.fieldname, candidate
	return None, None


@frappe.whitelist(methods=["POST"])
def make_landed_cost_voucher(shipment, allow_estimate=0):
	"""Draft Landed Cost Voucher for a shipment's submitted receipts. Accounts reviews and submits."""
	_need_edit()
	ship = frappe.get_doc(purchasing.SHIPMENT, shipment)
	ship.check_permission("write")
	names = [r.purchase_receipt for r in ship.get("receipts") or [] if r.purchase_receipt]
	receipts = (
		frappe.get_list(
			"Purchase Receipt",
			filters={"name": ["in", names]},
			fields=["name", "docstatus", "supplier", "posting_date", "base_grand_total", "company"],
			limit_page_length=0,
		)
		if names
		else []
	)
	missing = set(names) - {r.name for r in receipts}
	if missing:
		frappe.throw(_("You can't read these receipts: {0}").format(", ".join(sorted(missing))))
	costs = [{k: c.get(k) for k in COST_FIELDS} for c in ship.get("costs") or []]
	try:
		plan = lcv_plan(costs, receipts, allow_estimate=bool(int(allow_estimate or 0)))
	except ValueError as error:
		frappe.throw(str(error))
	settings = purchasing.read_settings()
	doc = frappe.get_doc(
		{
			"doctype": "Landed Cost Voucher",
			"company": receipts[0].company or settings.get("company"),
			"posting_date": frappe.utils.nowdate(),
			"distribute_charges_based_on": plan["basis"],
			"purchase_receipts": [
				{
					"receipt_document_type": "Purchase Receipt",
					"receipt_document": r.name,
					"supplier": r.supplier,
					"posting_date": r.posting_date,
					"grand_total": r.base_grand_total,
				}
				for r in receipts
			],
			"taxes": plan["taxes"],
		}
	)
	doc.get_items_from_purchase_receipts()
	table, link = _vendor_invoice_table(frappe.get_meta("Landed Cost Voucher"))
	if table:
		for bill in sorted(
			{
				c.get("purchase_invoice")
				for c in costs
				if c.get("purchase_invoice") and int(c.get("include_in_landed_cost") or 0)
			}
		):
			doc.append(table, {link: bill})
	result = _insert(doc, f"landed cost voucher for {shipment}")
	ship.append("landed_cost_vouchers", {"landed_cost_voucher": result["name"], "lcv_docstatus": 0})
	ship.save()
	purchasing.comment(
		purchasing.SHIPMENT,
		shipment,
		f"draft landed cost voucher {result['name']} created by {frappe.session.user}",
	)
	return result


@frappe.whitelist(methods=["POST"])
def apply_reorder_level(item, warehouse, level, qty=None):
	"""Add or update the item's reorder row for one warehouse (Phase 5 "Apply")."""
	_need_edit()
	level = _num(level)
	if level <= 0:
		frappe.throw(_("Reorder level must be more than zero."))
	doc = frappe.get_doc("Item", item)
	doc.check_permission("write")
	qty = _num(qty) or level
	row = next((r for r in doc.get("reorder_levels") or [] if r.warehouse == warehouse), None)
	if row:
		row.warehouse_reorder_level, row.warehouse_reorder_qty = level, qty
	else:
		doc.append(
			"reorder_levels",
			{
				"warehouse": warehouse,
				"warehouse_reorder_level": level,
				"warehouse_reorder_qty": qty,
				"material_request_type": "Purchase",
			},
		)
	doc.save()
	purchasing.comment(
		"Item", item, f"reorder level for {warehouse} set to {level:g} (qty {qty:g}) by {frappe.session.user}"
	)
	return {"name": doc.name}
