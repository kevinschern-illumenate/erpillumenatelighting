"""Production Board: the warehouse Schedule Wizard, live from ERPNext.

One read-only endpoint, ``get_board``, feeds the Command Center Manufacturing view.
It mirrors the workbook the warehouse manager planned from:

* **Status** of every open Sales Order, derived from its Work Orders, stock and
  deliveries (workbook codes: 1 Pend-Prod, 2 In-Prod, 3 Pend-Ship, 5 Held,
  7 Paint, 9 Waiting for parts). A floor override on the order can force Paint,
  Held or Waiting for parts.
* **Queue** with build points by conductor count and adders (``build_points``),
  hours, and worth per point = (revenue - commission) / points.
* **Waiting for parts**: Work Order material short after stock is handed out in
  ship-date order; the ETA is when open Purchase Orders cover the shortage.
* **Capacity**: workload (in-house + this month's waiting-for-parts points) burned
  down by points per person per day x head count, over workdays, with what is left
  of today's shift and overtime.
* **Shipped** this month from Delivery Notes, with on-time % (ship date on or before
  the estimated ship date, or marked "not warehouse fault").

Dollar figures are returned only to people with a finance or manufacturing manager
role; everyone else gets ``None`` in those fields.
"""

from datetime import date, datetime, timedelta

import frappe

from illumenate_lighting.illumenate_lighting.api import build_points

PEND_PROD, IN_PROD, PEND_SHIP, HELD, PAINT, WFP = 1, 2, 3, 5, 7, 9
LABELS = {
	PEND_PROD: "Pend-Prod",
	IN_PROD: "In-Prod",
	PEND_SHIP: "Pend-Ship",
	HELD: "Held",
	PAINT: "Paint",
	WFP: "Waiting for parts",
}
KEYS = {PEND_PROD: "pend_prod", IN_PROD: "in_prod", PEND_SHIP: "pend_ship", HELD: "held", PAINT: "paint", WFP: "wfp"}
OVERRIDES = {"Paint": PAINT, "Held": HELD, "Waiting for parts": WFP}

VIEW_ROLES = {"Command Center Viewer", "System Manager", "Manufacturing Manager", "Manufacturing User"}
MONEY_ROLES = {"Command Center Finance", "System Manager", "Manufacturing Manager", "Accounts Manager"}
BURNDOWN_DAYS = 22


# ---------------------------------------------------------------------------
# Pure helpers (no database)
# ---------------------------------------------------------------------------


def as_date(value):
	if value in (None, ""):
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	return date.fromisoformat(str(value)[:10])


def is_workday(day, holidays):
	return day.weekday() < 5 and day not in holidays


def workdays(start, count, holidays):
	"""``count`` workdays from ``start`` (inclusive when it is a workday)."""
	days, day = [], start
	while len(days) < count:
		if is_workday(day, holidays):
			days.append(day)
		day += timedelta(days=1)
	return days


def next_workday(day, holidays):
	day += timedelta(days=1)
	while not is_workday(day, holidays):
		day += timedelta(days=1)
	return day


def workdays_left_in_month(today, holidays, *, include_today=True):
	end = month_end(today)
	day = today if include_today else today + timedelta(days=1)
	count = 0
	while day <= end:
		count += is_workday(day, holidays)
		day += timedelta(days=1)
	return count


def month_end(day):
	first_next = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
	return first_next - timedelta(days=1)


def order_status(order, work_orders, short):
	"""Workbook status code for one open Sales Order.

	``work_orders`` are its non-cancelled Work Orders; ``short`` says whether any of
	them still lacks material after stock is handed out.
	"""
	override = OVERRIDES.get(order.get("ill_production_status_override") or "")
	if override:
		return override
	if order.get("status") == "On Hold" or any(w.get("status") == "Stopped" for w in work_orders):
		return HELD
	if not work_orders:
		# Nothing to build (stock lines only) is ready to ship; a build without a WO waits for one.
		return PEND_PROD if (order.get("ill_build_points") or 0) > 0 else PEND_SHIP
	if all(w.get("status") == "Completed" or (w.get("produced_qty") or 0) >= (w.get("qty") or 0) for w in work_orders):
		return PEND_SHIP
	if any(
		w.get("status") == "In Process" or (w.get("material_transferred_for_manufacturing") or 0) > 0
		for w in work_orders
	):
		return IN_PROD
	if short:
		return WFP
	return PEND_PROD


def allocate(orders, needs, stock, incoming):
	"""Hand stock to orders in ship-date order; find each order's shortages and ETA.

	``orders`` - order names, earliest ship date first.
	``needs`` - {order: {item: qty still to issue}}.
	``stock`` - {item: qty on hand}.
	``incoming`` - {item: [(date, qty), ...]} open purchase quantities.
	Returns {order: {"short": {item: qty}, "eta": date|None, "no_po": [items]}}.
	"""
	stock = dict(stock)
	incoming = {item: sorted(rows) for item, rows in incoming.items()}
	used_incoming = {item: 0.0 for item in incoming}
	result = {}
	for order in orders:
		short, eta, no_po = {}, None, []
		for item, qty in (needs.get(order) or {}).items():
			if qty <= 0:
				continue
			take = min(qty, max(stock.get(item, 0), 0))
			stock[item] = stock.get(item, 0) - take
			missing = round(qty - take, 6)
			if missing <= 0:
				continue
			short[item] = missing
			# Walk this item's open POs past what earlier orders already claimed.
			claimed, covered_at, running = used_incoming.get(item, 0.0), None, 0.0
			for when, available in incoming.get(item, []):
				running += available
				if running - claimed >= missing - 1e-9:
					covered_at = when
					break
			if covered_at is None:
				no_po.append(item)
			else:
				used_incoming[item] = claimed + missing
				eta = max(eta, covered_at) if eta else covered_at
		result[order] = {"short": short, "eta": eta if not no_po else None, "no_po": no_po}
	return result


def burndown(workload, per_day, left_today, days, *, ot_daily=0, ot_days=0, ot_weekend=0):
	"""Remaining points at the end of each workday, and the day the queue clears.

	Day one uses what is left of today's shift instead of a full day. Daily overtime
	applies to the first ``ot_days`` workdays; weekend overtime is credited on Monday.
	"""
	rows, remaining, clear = [], float(workload), None
	for i, day in enumerate(days):
		capacity = left_today if i == 0 else per_day
		if i < ot_days:
			capacity += ot_daily
		if day.weekday() == 0 and i > 0:
			capacity += ot_weekend
		remaining -= capacity
		rows.append({"date": day.isoformat(), "capacity": round(capacity, 2), "remaining": round(max(remaining, 0), 2)})
		if clear is None and remaining <= 0:
			clear = day.isoformat()
	return rows, clear


def shift_left_fraction(now, shift_end, shift_hours):
	"""Share of a full day's capacity still available today (0-1)."""
	end = datetime.combine(now.date(), shift_end)
	hours = max((end - now).total_seconds() / 3600, 0)
	return min(hours / shift_hours, 1) if shift_hours else 0


def on_time_rows(shipments, today):
	"""Weekly on-time % for the month (weeks Monday-Sunday), like the Shipped sheet."""
	start = today.replace(day=1)
	week = start - timedelta(days=start.weekday())
	rows = []
	while week <= today:
		end = week + timedelta(days=6)
		inside = [s for s in shipments if week <= as_date(s["shipped"]) <= end]
		ok = sum(1 for s in inside if s["on_time"] or s["not_warehouse_fault"])
		rows.append(
			{
				"week_of": week.isoformat(),
				"shipments": len(inside),
				"on_time_pct": round(ok / len(inside), 4) if inside else None,
			}
		)
		week += timedelta(days=7)
	return rows


# ---------------------------------------------------------------------------
# Reading ERPNext
# ---------------------------------------------------------------------------


def _roles():
	return set(frappe.get_roles(frappe.session.user))


def _has_field(doctype, field):
	return frappe.get_meta(doctype).has_field(field)


def _fields(doctype, wanted):
	meta = frappe.get_meta(doctype)
	return [f for f in wanted if "." in f or f in ("name", "status", "docstatus") or meta.has_field(f)]


def holiday_dates(values):
	name = values.get("holiday_list")
	if not name:
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
		name = frappe.db.get_value("Company", company, "default_holiday_list") if company else None
	if not name:
		return set()
	return {as_date(d) for d in frappe.get_all("Holiday", filters={"parent": name}, pluck="holiday_date")}


def _shift_end(value):
	if isinstance(value, timedelta):
		return (datetime.min + value).time()
	text = str(value or "16:30:00")
	parts = [int(p) for p in text.split(":")[:3]] + [0, 0]
	return datetime.min.replace(hour=parts[0], minute=parts[1], second=parts[2]).time()


def open_orders():
	wanted = [
		"name",
		"customer",
		"customer_name",
		"status",
		"transaction_date",
		"delivery_date",
		"net_total",
		"total_commission",
		"per_delivered",
		"ill_estimated_ship_date",
		"ill_production_status_override",
		"ill_floor_notes",
		"ill_build_points",
		"ill_build_hours",
		"ill_build_points_warnings",
		*[build_points.FIELD[key] for key in build_points.COUNT_KEYS],
	]
	return frappe.get_all(
		"Sales Order",
		filters={
			"docstatus": 1,
			"status": ["not in", ["Closed", "Completed", "Cancelled"]],
			"per_delivered": ["<", 100],
		},
		fields=_fields("Sales Order", wanted),
		order_by="delivery_date asc",
		limit_page_length=0,
	)


def work_orders_for(order_names):
	if not order_names:
		return []
	return frappe.get_all(
		"Work Order",
		filters={"sales_order": ["in", order_names], "docstatus": ["<", 2], "status": ["!=", "Cancelled"]},
		fields=_fields(
			"Work Order",
			[
				"name",
				"sales_order",
				"status",
				"docstatus",
				"qty",
				"produced_qty",
				"material_transferred_for_manufacturing",
				"ill_build_points",
			],
		),
		limit_page_length=0,
	)


def material_needs(work_orders):
	"""{sales order: {item: qty still to issue}} for Work Orders not yet in process."""
	waiting = {w.name: w.sales_order for w in work_orders if w.status in ("Draft", "Not Started")}
	if not waiting:
		return {}
	rows = frappe.get_all(
		"Work Order Item",
		filters={"parent": ["in", list(waiting)]},
		fields=["parent", "item_code", "required_qty", "transferred_qty"],
		limit_page_length=0,
	)
	needs = {}
	for row in rows:
		qty = float(row.required_qty or 0) - float(row.transferred_qty or 0)
		if qty > 0:
			bucket = needs.setdefault(waiting[row.parent], {})
			bucket[row.item_code] = bucket.get(row.item_code, 0) + qty
	return needs


def stock_on_hand(items):
	stock = {}
	if items:
		for row in frappe.get_all(
			"Bin", filters={"item_code": ["in", list(items)]}, fields=["item_code", "actual_qty"], limit_page_length=0
		):
			stock[row.item_code] = stock.get(row.item_code, 0) + float(row.actual_qty or 0)
	return stock


def incoming_purchases(items):
	if not items:
		return {}
	orders = frappe.get_all(
		"Purchase Order",
		filters={"docstatus": 1, "status": ["not in", ["Closed", "Completed", "Cancelled", "On Hold"]]},
		pluck="name",
		limit_page_length=0,
	)
	if not orders:
		return {}
	incoming = {}
	for row in frappe.get_all(
		"Purchase Order Item",
		filters={"parent": ["in", orders], "item_code": ["in", list(items)]},
		fields=["item_code", "schedule_date", "qty", "received_qty", "stock_qty"],
		limit_page_length=0,
	):
		qty = float(row.qty or 0)
		open_share = (qty - float(row.received_qty or 0)) / qty if qty else 0
		pending = float(row.stock_qty or qty) * open_share
		if pending > 0 and row.schedule_date:
			incoming.setdefault(row.item_code, []).append((as_date(row.schedule_date), pending))
	return incoming


def shipments_this_month(today, commission_rates):
	start = today.replace(day=1)
	wanted = ["name", "posting_date", "net_total", "ill_late_reason", "ill_not_warehouse_fault"]
	notes = frappe.get_all(
		"Delivery Note",
		filters={"docstatus": 1, "is_return": 0, "posting_date": ["between", [start, today]]},
		fields=_fields("Delivery Note", wanted),
		limit_page_length=0,
	)
	if not notes:
		return []
	links = {}
	for row in frappe.get_all(
		"Delivery Note Item",
		filters={"parent": ["in", [n.name for n in notes]], "against_sales_order": ["is", "set"]},
		fields=["parent", "against_sales_order"],
		limit_page_length=0,
	):
		links.setdefault(row.parent, row.against_sales_order)
	orders = {}
	so_names = list(set(links.values()))
	if so_names:
		for row in frappe.get_all(
			"Sales Order",
			filters={"name": ["in", so_names]},
			fields=_fields(
				"Sales Order", ["name", "customer_name", "delivery_date", "ill_estimated_ship_date", "net_total", "total_commission"]
			),
			limit_page_length=0,
		):
			orders[row.name] = row
	shipped = []
	for note in notes:
		so = orders.get(links.get(note.name)) or {}
		esd = as_date(so.get("ill_estimated_ship_date") or so.get("delivery_date"))
		day = as_date(note.posting_date)
		rate = commission_rates.get(so.get("name"))
		if rate is None:
			net = float(so.get("net_total") or 0)
			rate = float(so.get("total_commission") or 0) / net if net else 0
		amount = float(note.net_total or 0)
		shipped.append(
			{
				"delivery_note": note.name,
				"so": so.get("name"),
				"customer": so.get("customer_name"),
				"amount": amount,
				"com_pct": round(rate, 4),
				"com": round(amount * rate, 2),
				"esd": esd.isoformat() if esd else None,
				"shipped": day.isoformat(),
				"on_time": bool(esd and day <= esd),
				"not_warehouse_fault": bool(note.get("ill_not_warehouse_fault")),
				"late_reason": note.get("ill_late_reason"),
			}
		)
	shipped.sort(key=lambda s: s["shipped"], reverse=True)
	return shipped


# ---------------------------------------------------------------------------
# The board
# ---------------------------------------------------------------------------


def _bucket():
	return {"amount": 0.0, "com": 0.0, "count": 0, "points": 0.0}


def _add(bucket, row):
	bucket["amount"] += row["amount"]
	bucket["com"] += row["com"]
	bucket["count"] += 1
	bucket["points"] += row["points"]


def _finish(bucket, money):
	bucket["com_pct"] = round(bucket["com"] / bucket["amount"], 4) if bucket["amount"] else 0
	bucket["points"] = round(bucket["points"], 2)
	if not money:
		bucket.update(amount=None, com=None, com_pct=None)
	else:
		bucket["amount"], bucket["com"] = round(bucket["amount"], 2), round(bucket["com"], 2)
	return bucket


def build_board(now=None, money=True):
	values = build_points.settings()
	now = now or frappe.utils.now_datetime()
	today = now.date()
	holidays = holiday_dates(values)
	num = build_points._number

	per_person = num(values, "points_per_person_day", build_points.DEFAULT_POINTS_PER_PERSON_DAY)
	headcount = num(values, "headcount", 5.5)
	shift_hours = num(values, "shift_hours", 8) or 8
	per_day = per_person * headcount
	per_hour = build_points.points_per_hour(values)
	flag_pct = num(values, "commission_flag_pct", 22) / 100
	ot_daily = num(values, "ot_daily_headcount", 0) * per_person * num(values, "ot_daily_hours", 0) / shift_hours
	ot_weekend = num(values, "ot_weekend_headcount", 0) * per_person * num(values, "ot_weekend_hours", 0) / shift_hours
	ot_days = int(num(values, "ot_daily_days", 0))
	left_fraction = shift_left_fraction(now, _shift_end(values.get("shift_end_time")), shift_hours) if is_workday(today, holidays) else 0

	orders = open_orders()
	names = [o.name for o in orders]
	wos = work_orders_for(names)
	by_order = {}
	for w in wos:
		by_order.setdefault(w.sales_order, []).append(w)

	def esd_of(order):
		return as_date(order.get("ill_estimated_ship_date") or order.get("delivery_date"))

	ranked = sorted(orders, key=lambda o: (esd_of(o) or date.max, o.name))
	needs = material_needs(wos)
	items = {item for bucket in needs.values() for item in bucket}
	shortages = allocate(
		[o.name for o in ranked], needs, stock_on_hand(items), incoming_purchases(items)
	)
	month_last = month_end(today)

	rows, rates = [], {}
	for order in ranked:
		net = float(order.get("net_total") or 0)
		rate = float(order.get("total_commission") or 0) / net if net else 0
		rates[order.name] = rate
		open_share = 1 - float(order.get("per_delivered") or 0) / 100
		amount = net * open_share
		gap = shortages.get(order.name) or {"short": {}, "eta": None, "no_po": []}
		status = order_status(order, by_order.get(order.name, []), bool(gap["short"]))
		points = float(order.get("ill_build_points") or 0)
		esd = esd_of(order)
		eta = gap["eta"]
		row = {
			"so": order.name,
			"customer": order.get("customer_name") or order.get("customer"),
			"amount": round(amount, 2),
			"com_pct": round(rate, 4),
			"com": round(amount * rate, 2),
			"esd": esd.isoformat() if esd else None,
			"esd_is_ship_date": bool(order.get("ill_estimated_ship_date")),
			"status": status,
			"status_label": LABELS[status],
			"counts": {key: float(order.get(build_points.FIELD[key]) or 0) for key in build_points.COUNT_KEYS},
			"points": round(points, 2),
			"hours": round(points / per_hour, 2) if per_hour else 0,
			"worth": round((amount - amount * rate) / points, 2) if points else None,
			"notes": order.get("ill_floor_notes") or "",
			"warnings": [w for w in (order.get("ill_build_points_warnings") or "").split("\n") if w],
			"work_orders": len(by_order.get(order.name, [])),
			"short_items": [{"item": item, "qty": round(qty, 3)} for item, qty in gap["short"].items()],
			"no_po_items": gap["no_po"],
			"eta": eta.isoformat() if eta else None,
			"going_to_miss": bool(status == WFP and (not eta or (esd and esd < eta))),
			"this_month": bool(status != WFP or (eta and eta <= month_last)),
			"past_due": bool(esd and esd < today),
		}
		rows.append(row)

	pipeline = {key: _bucket() for key in KEYS.values()}
	for row in rows:
		_add(pipeline[KEYS[row["status"]]], row)
	pipeline = {key: _finish(bucket, money) for key, bucket in pipeline.items()}

	next_day = next_workday(today, holidays)
	week_end = today + timedelta(days=(4 - today.weekday()) % 7)

	def due(predicate):
		hit = [r for r in rows if r["status"] != HELD and r["esd"] and predicate(as_date(r["esd"]))]
		return {"count": len(hit), "amount": round(sum(r["amount"] for r in hit), 2) if money else None}

	due_panel = {
		"past_due": due(lambda d: d < today),
		"today": due(lambda d: d == today),
		"next_day": due(lambda d: d == next_day) | {"date": next_day.isoformat()},
		"this_week": due(lambda d: today <= d <= week_end),
	}

	whse = sum(r["points"] for r in rows if r["status"] in (PEND_PROD, IN_PROD))
	in_prod = sum(r["points"] for r in rows if r["status"] == IN_PROD)
	wfp_month = sum(r["points"] for r in rows if r["status"] == WFP and r["this_month"])
	workload = whse + wfp_month
	days = workdays(today, BURNDOWN_DAYS, holidays)
	if not is_workday(today, holidays):
		left_today = 0
	else:
		left_today = per_day * left_fraction
	curve, clear = burndown(
		workload, per_day, left_today, days, ot_daily=ot_daily, ot_days=ot_days, ot_weekend=ot_weekend
	)

	shipped = shipments_this_month(today, rates)
	shipped_today = [s for s in shipped if s["shipped"] == today.isoformat()]

	def ship_sum(items):
		amount = sum(s["amount"] for s in items)
		com = sum(s["com"] for s in items)
		return {
			"count": len(items),
			"amount": round(amount, 2) if money else None,
			"com": round(com, 2) if money else None,
			"com_pct": round(com / amount, 4) if money and amount else None,
		}

	on_time = sum(1 for s in shipped if s["on_time"] or s["not_warehouse_fault"])
	available = [r for r in rows if r["status"] != HELD and r["this_month"]]
	goal = num(values, "monthly_revenue_goal", 0)
	shipped_mtd = sum(s["amount"] for s in shipped)
	available_amount = sum(r["amount"] for r in available)
	days_left = workdays_left_in_month(today, holidays, include_today=False)
	gap_amount = goal - shipped_mtd - available_amount

	shipped_summary = {
		"today": ship_sum(shipped_today),
		"mtd": ship_sum(shipped),
		"on_time_pct": round(on_time / len(shipped), 4) if shipped else None,
		"weekly": on_time_rows(shipped, today),
		"rows": shipped,
	}
	if not money:
		for row in rows:
			row.update(amount=None, com=None, com_pct=None, worth=None)
		for s in shipped:
			s.update(amount=None, com=None, com_pct=None)

	return {
		"as_of": now.isoformat(timespec="seconds"),
		"today": today.isoformat(),
		"money": money,
		"settings": {
			"points_per_person_day": per_person,
			"headcount": headcount,
			"capacity_per_day": round(per_day, 2),
			"points_per_hour": round(per_hour, 2),
			"weights": build_points.weights(values),
			"commission_flag_pct": flag_pct,
			"monthly_revenue_goal": goal if money else None,
		},
		"pipeline": pipeline,
		"due": due_panel,
		"capacity": {
			"whse_points": round(whse, 2),
			"in_prod_points": round(in_prod, 2),
			"wfp_month_points": round(wfp_month, 2),
			"workload": round(workload, 2),
			"capacity_per_day": round(per_day, 2),
			"left_today": round(left_today, 2),
			"days_to_complete": round(workload / per_day, 2) if per_day else None,
			"date_clear": clear,
			"burndown": curve,
			"overtime": {"daily": round(ot_daily, 2), "days": ot_days, "weekend": round(ot_weekend, 2)},
		},
		"queue": [r for r in rows if r["status"] != WFP],
		"wfp": [r for r in rows if r["status"] == WFP],
		"shipped": shipped_summary,
		"goal": {
			"month_goal": goal if money else None,
			"shipped_mtd": round(shipped_mtd, 2) if money else None,
			"available_to_ship": round(available_amount, 2) if money else None,
			"gap": round(gap_amount, 2) if money and goal else None,
			"shipping_days_left": days_left,
			"needed_per_day": round(gap_amount / days_left, 2) if money and goal and days_left else None,
		},
	}


@frappe.whitelist()
def get_board():
	roles = _roles()
	if not roles & VIEW_ROLES:
		frappe.throw("You need the Command Center Viewer role to see the production board.", frappe.PermissionError)
	return build_board(money=bool(roles & MONEY_ROLES))
