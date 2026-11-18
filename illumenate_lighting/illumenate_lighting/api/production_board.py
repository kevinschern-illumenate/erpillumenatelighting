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
RELEASE_HOLDS = ("Hold for Release", "Hold for Confirmation")
SHIP_HOLD = "Hold for Ship"
# Fields blanked for people without a money role.
# Any key ending in "_amount" is money too.
MONEY_KEYS = {
	"amount",
	"com",
	"com_pct",
	"worth",
	"goal_pct",
	"month_goal",
	"gap",
	"needed_per_day",
	"shipped_mtd",
	"available_to_ship",
	"monthly_revenue_goal",
}

VIEW_ROLES = {"Command Center Viewer", "System Manager", "Manufacturing Manager", "Manufacturing User"}
# Who may correct an order's build counts from the queue.
ADJUST_ROLES = {"System Manager", "Manufacturing Manager", "Manufacturing User"}
COUNT_LABELS = {
	"runs_2c": "2C",
	"runs_3c": "3C",
	"runs_4c": "4C",
	"runs_5c": "5C",
	"runs_6c": "6C",
	"loose": "Loose",
	"wet": "WR",
	"fmc": "FMC",
	"assembly": "Assy",
}
MAX_COUNT = 100000
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


def order_status(order, work_orders, short, paint_open=False):
	"""Workbook status code for one open Sales Order.

	``work_orders`` are its non-cancelled Work Orders; ``short`` says whether any of
	them still lacks material after stock is handed out; ``paint_open`` whether an
	outside paint purchase order for it is still open.
	"""
	override = OVERRIDES.get(order.get("ill_production_status_override") or "")
	if override:
		return override
	if (
		order.get("ill_hold_reason")
		or order.get("status") == "On Hold"
		or any(w.get("status") == "Stopped" for w in work_orders)
	):
		return HELD
	if not work_orders:
		# Nothing to build (stock lines only) is ready to ship; a build without a WO waits for one.
		return PEND_PROD if (order.get("ill_build_points") or 0) > 0 else PEND_SHIP
	if all(w.get("status") == "Completed" or (w.get("produced_qty") or 0) >= (w.get("qty") or 0) for w in work_orders):
		return PEND_SHIP
	if paint_open:
		return PAINT
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


def scrub(value):
	"""Blank every money field, at any depth."""
	if isinstance(value, dict):
		for key, item in value.items():
			if (key in MONEY_KEYS or key.endswith("_amount")) and not isinstance(item, (dict, list)):
				value[key] = None
			else:
				scrub(item)
	elif isinstance(value, list):
		for item in value:
			scrub(item)
	return value


def add_months(day, months):
	month = day.month - 1 + months
	return date(day.year + month // 12, month % 12 + 1, 1)


def workdays_between(start, end, holidays):
	count, day = 0, start
	while day <= end:
		count += is_workday(day, holidays)
		day += timedelta(days=1)
	return count


def inbound_days(received, days, holidays):
	"""The Inbound(RR) sheet: orders received per workday.

	``received`` rows: {"received": date, "esd": date|None, "amount", "com"}.
	Same day = ship date is the day received; next day = the next workday; rush =
	ship date within 3 workdays of receipt.
	"""
	rows = []
	for day in days:
		hit = [r for r in received if r["received"] == day]
		nxt = next_workday(day, holidays)
		third = day
		for _ in range(3):
			third = next_workday(third, holidays)
		amount = sum(r["amount"] for r in hit)
		com = sum(r["com"] for r in hit)
		rows.append(
			{
				"date": day.isoformat(),
				"count": len(hit),
				"amount": round(amount, 2),
				"com": round(com, 2),
				"com_pct": round(com / amount, 4) if amount else 0,
				"zero": sum(1 for r in hit if not r["amount"]),
				"same_day": sum(1 for r in hit if r["esd"] == day),
				"next_day": sum(1 for r in hit if r["esd"] == nxt),
				"rush": sum(1 for r in hit if r["esd"] and r["esd"] <= third),
			}
		)
	return rows


def average(values):
	values = list(values)
	return round(sum(values) / len(values), 2) if values else 0


def month_totals(rows, key, months):
	"""Revenue and commission per month for rows dated by ``key`` (ESPR / HFS sheets)."""
	out = []
	for first in months:
		last = month_end(first)
		hit = [r for r in rows if r.get(key) and first <= as_date(r[key]) <= last]
		amount = sum(r["amount"] for r in hit)
		com = sum(r["com"] for r in hit)
		out.append(
			{
				"month": first.isoformat(),
				"count": len(hit),
				"amount": round(amount, 2),
				"com": round(com, 2),
				"com_pct": round(com / amount, 4) if amount else 0,
			}
		)
	return out


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
		"ill_hold_reason",
		"ill_likely_ship_date",
		"ill_proforma_will_call",
		"ill_build_points",
		"ill_build_hours",
		"ill_build_points_warnings",
		build_points.ADJUST_FIELD,
		build_points.ADJUST_NOTE_FIELD,
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
	# Purchasing tracks an editable ETA (ill_eta, line then header); it wins over "Required By"
	# when the fields exist, so the production and purchasing boards agree.
	header_eta = _has_field("Purchase Order", "ill_eta")
	line_eta = _has_field("Purchase Order Item", "ill_eta")
	orders = frappe.get_all(
		"Purchase Order",
		filters={"docstatus": 1, "status": ["not in", ["Closed", "Completed", "Cancelled", "On Hold"]]},
		fields=["name", "ill_eta"] if header_eta else ["name"],
		limit_page_length=0,
	)
	if not orders:
		return {}
	po_eta = {o.name: o.get("ill_eta") for o in orders}
	incoming = {}
	for row in frappe.get_all(
		"Purchase Order Item",
		filters={"parent": ["in", list(po_eta)], "item_code": ["in", list(items)]},
		fields=["parent", "item_code", "schedule_date", "qty", "received_qty", "stock_qty"]
		+ (["ill_eta"] if line_eta else []),
		limit_page_length=0,
	):
		qty = float(row.qty or 0)
		open_share = (qty - float(row.received_qty or 0)) / qty if qty else 0
		pending = float(row.stock_qty or qty) * open_share
		when = row.get("ill_eta") or po_eta.get(row.get("parent")) or row.schedule_date
		if pending > 0 and when:
			incoming.setdefault(row.item_code, []).append((as_date(when), pending))
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
				"Sales Order",
				[
					"name",
					"customer_name",
					"delivery_date",
					"ill_estimated_ship_date",
					"net_total",
					"total_commission",
					"ill_proforma_will_call",
				],
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
				"prowc": so.get("ill_proforma_will_call") or "",
			}
		)
	shipped.sort(key=lambda s: s["shipped"], reverse=True)
	return shipped


def received_orders(start, end):
	"""Submitted Sales Orders received (transaction date) between two dates."""
	rows = frappe.get_all(
		"Sales Order",
		filters={"docstatus": 1, "transaction_date": ["between", [start, end]]},
		fields=_fields(
			"Sales Order",
			["name", "transaction_date", "delivery_date", "ill_estimated_ship_date", "net_total", "total_commission"],
		),
		limit_page_length=0,
	)
	out = []
	for row in rows:
		amount = float(row.net_total or 0)
		out.append(
			{
				"received": as_date(row.transaction_date),
				"esd": as_date(row.get("ill_estimated_ship_date") or row.get("delivery_date")),
				"amount": amount,
				"com": float(row.total_commission or 0),
			}
		)
	return out


def goals(values):
	"""{first of month: revenue goal} from the settings goal table."""
	out = {}
	try:
		rows = frappe.get_all(
			"ilL-Child-Production-Goal",
			filters={"parenttype": build_points.SETTINGS, "parentfield": "monthly_goals"},
			fields=["month", "revenue_goal"],
		)
	except Exception:
		rows = []
	for row in rows:
		if row.month:
			out[as_date(row.month).replace(day=1)] = float(row.revenue_goal or 0)
	return out


def paint_jobs(order_names, supplier_group):
	"""{sales order: [open outside-paint PO lines]} for suppliers in the paint group."""
	if not order_names or not supplier_group:
		return {}
	suppliers = frappe.get_all("Supplier", filters={"supplier_group": supplier_group}, pluck="name")
	if not suppliers:
		return {}
	orders = {
		po.name: po
		for po in frappe.get_all(
			"Purchase Order",
			filters={
				"docstatus": 1,
				"supplier": ["in", suppliers],
				"status": ["not in", ["Closed", "Completed", "Cancelled"]],
			},
			fields=["name", "supplier", "transaction_date", "schedule_date"],
			limit_page_length=0,
		)
	}
	if not orders:
		return {}
	jobs = {}
	for row in frappe.get_all(
		"Purchase Order Item",
		filters={"parent": ["in", list(orders)], "sales_order": ["in", order_names]},
		fields=["parent", "sales_order", "item_code", "item_name", "qty", "received_qty", "schedule_date"],
		limit_page_length=0,
	):
		if float(row.received_qty or 0) >= float(row.qty or 0):
			continue
		po = orders[row.parent]
		jobs.setdefault(row.sales_order, []).append(
			{
				"po": row.parent,
				"supplier": po.supplier,
				"sent": as_date(po.transaction_date).isoformat() if po.transaction_date else None,
				"due_back": as_date(row.schedule_date or po.schedule_date).isoformat()
				if (row.schedule_date or po.schedule_date)
				else None,
				"item": row.item_code,
				"item_name": row.item_name,
				"qty": float(row.qty or 0) - float(row.received_qty or 0),
			}
		)
	return jobs


MR_DONE_STATUSES = ("Received", "Issued", "Transferred")
MR_RECENT_DAYS = 30
MR_LOOKBACK_DAYS = 180


def mr_lane(mr):
	"""Where a Manufacture Material Request sits on the floor.

	draft -> needs_wo (submitted, no work order yet) -> building (has work orders,
	not all finished) -> done (every work order finished). ERPNext marks the request
	"Manufactured" as soon as work orders cover the full quantity, so that status
	alone means "building", not "built".
	"""
	if int(mr.get("docstatus") or 0) == 0:
		return "draft"
	if (mr.get("status") or "") in MR_DONE_STATUSES:
		return "done"
	wos = [w for w in mr.get("work_orders") or [] if w.get("status") != "Cancelled"]
	if wos:
		return "done" if all(w.get("status") == "Completed" for w in wos) else "building"
	qty = sum(i.get("qty") or 0 for i in mr.get("items") or [])
	covered = sum(i.get("ordered_qty") or 0 for i in mr.get("items") or [])
	if mr.get("status") == "Manufactured" or (qty and covered >= qty):
		return "building"
	return "needs_wo"


def manufacture_requests(today):
	"""Manufacture-type Material Requests still being worked, plus ones finished in the last 30 days.

	"Manufactured" requests (work orders cover them) are read for 180 days so slow
	builds stay visible; the board drops finished ones older than 30 days.
	"""
	parents = frappe.get_all(
		"Material Request",
		filters={
			"material_request_type": "Manufacture",
			"docstatus": ["<", 2],
			"status": ["not in", ["Stopped", "Cancelled"]],
		},
		or_filters=[
			["status", "not in", ["Manufactured", *MR_DONE_STATUSES]],
			["modified", ">=", (today - timedelta(days=MR_LOOKBACK_DAYS)).isoformat()],
		],
		fields=["name", "status", "docstatus", "transaction_date", "schedule_date", "owner", "modified"],
		order_by="modified desc",
		limit_page_length=500,
	)
	if not parents:
		return []
	names = [p.name for p in parents]
	items = {}
	for row in frappe.get_all(
		"Material Request Item",
		filters={"parent": ["in", names], "parenttype": "Material Request"},
		fields=["parent", "item_code", "item_name", "qty", "ordered_qty", "sales_order", "schedule_date"],
		order_by="idx asc",
		limit_page_length=0,
	):
		items.setdefault(row.parent, []).append(row)
	wos = {}
	if _has_field("Work Order", "material_request"):
		for w in frappe.get_all(
			"Work Order",
			filters={"material_request": ["in", names], "docstatus": ["<", 2]},
			fields=["name", "status", "docstatus", "material_request", "qty", "produced_qty", "sales_order"],
			limit_page_length=0,
		):
			wos.setdefault(w.material_request, []).append(w)
	return build_manufacture_requests(parents, items, wos, today)


def build_manufacture_requests(parents, items, wos, today):
	"""Rows for the Manufacturing view's Material requests tab (pure, no database)."""
	rows = []
	for mr in parents:
		its = items.get(mr["name"]) or []
		work = wos.get(mr["name"]) or []
		row = {
			"name": mr["name"],
			"status": mr.get("status"),
			"docstatus": int(mr.get("docstatus") or 0),
			"transaction_date": as_date(mr.get("transaction_date")).isoformat() if mr.get("transaction_date") else None,
			"schedule_date": as_date(mr.get("schedule_date")).isoformat() if mr.get("schedule_date") else None,
			"owner": mr.get("owner"),
			"items": [
				{
					"item": i.get("item_code"),
					"item_name": i.get("item_name"),
					"qty": float(i.get("qty") or 0),
					"ordered_qty": float(i.get("ordered_qty") or 0),
				}
				for i in its
			],
			"sales_orders": sorted({i.get("sales_order") for i in its if i.get("sales_order")}),
			"work_orders": [
				{
					"name": w.get("name"),
					"status": "Draft" if int(w.get("docstatus") or 0) == 0 else w.get("status"),
					"qty": float(w.get("qty") or 0),
					"produced_qty": float(w.get("produced_qty") or 0),
				}
				for w in work
			],
		}
		row["lane"] = mr_lane(row)
		if row["lane"] == "done" and mr.get("modified") and as_date(mr["modified"]) < today - timedelta(days=MR_RECENT_DAYS):
			continue
		row["late"] = bool(row["schedule_date"] and as_date(row["schedule_date"]) < today and row["lane"] != "done")
		rows.append(row)
	rows.sort(key=lambda r: (r["schedule_date"] or "9999-12-31", r["name"]))
	return rows


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
	painting = paint_jobs(names, values.get("paint_supplier_group"))
	release_weights = build_points.release_weights(values)

	rows, rates = [], {}
	for order in ranked:
		net = float(order.get("net_total") or 0)
		rate = float(order.get("total_commission") or 0) / net if net else 0
		rates[order.name] = rate
		open_share = 1 - float(order.get("per_delivered") or 0) / 100
		amount = net * open_share
		gap = shortages.get(order.name) or {"short": {}, "eta": None, "no_po": []}
		status = order_status(
			order, by_order.get(order.name, []), bool(gap["short"]), bool(painting.get(order.name))
		)
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
			"adjustments": build_points.adjustments(order.get(build_points.ADJUST_FIELD)),
			"adjust_note": order.get(build_points.ADJUST_NOTE_FIELD) or "",
			"warnings": [w for w in (order.get("ill_build_points_warnings") or "").split("\n") if w],
			"work_orders": len(by_order.get(order.name, [])),
			"short_items": [{"item": item, "qty": round(qty, 3)} for item, qty in gap["short"].items()],
			"no_po_items": gap["no_po"],
			"eta": eta.isoformat() if eta else None,
			"going_to_miss": bool(status == WFP and (not eta or (esd and esd < eta))),
			"this_month": bool(status != WFP or (eta and eta <= month_last)),
			"past_due": bool(esd and esd < today),
			"hold_reason": order.get("ill_hold_reason") or "",
			"likely_ship": str(order.get("ill_likely_ship_date") or "")[:10] or None,
			"prowc": order.get("ill_proforma_will_call") or "",
			"paint": painting.get(order.name, []),
		}
		counts = row["counts"]
		row["release_points"] = build_points.score(counts, release_weights)
		row["release_days"] = round(row["release_points"] / per_day, 2) if per_day else None
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

	# --- Inbound (run rate): orders received per workday, last 30 workdays ---
	back, day = [], today
	while len(back) < 30:
		if is_workday(day, holidays):
			back.append(day)
		day -= timedelta(days=1)
	month_first = today.replace(day=1)
	received = received_orders(min(back[-1], month_first), today)
	inbound_rows = inbound_days(received, back, holidays)
	before = [r for r in inbound_rows if r["date"] < today.isoformat()]
	this_month_before = [r for r in before if r["date"] >= month_first.isoformat()]
	avg_30 = average(r["amount"] for r in before)
	inbound = {
		"today_amount": inbound_rows[0]["amount"] if back[0] == today else 0,
		"today": inbound_rows[0] if back[0] == today else None,
		"month_avg_amount": average(r["amount"] for r in this_month_before),
		"avg_30_amount": avg_30,
		"month_received_amount": round(sum(r["amount"] for r in inbound_rows if r["date"] >= month_first.isoformat()), 2),
		"days": inbound_rows,
	}

	# --- Daily dollars: shipped per workday this month ---
	month_days = [d for d in workdays(month_first, 23, holidays) if d <= month_last]
	by_day = {}
	for s_row in shipped:
		by_day.setdefault(s_row["shipped"], []).append(s_row)
	daily_rows = [
		{
			"date": d.isoformat(),
			"count": len(by_day.get(d.isoformat(), [])),
			"amount": round(sum(x["amount"] for x in by_day.get(d.isoformat(), [])), 2),
		}
		for d in month_days
	]
	shipped_days = [r["amount"] for r in daily_rows if r["date"] < today.isoformat() and r["amount"] > 0]
	daily = {
		"days": daily_rows,
		"average_amount": average(shipped_days),
		"needed_amount": round(gap_amount / days_left, 2) if goal and days_left else None,
	}

	# --- Releases (hold for release / confirmation) and hold for ship ---
	releases = [r for r in rows if r["hold_reason"] in RELEASE_HOLDS]
	ship_holds = [r for r in rows if r["hold_reason"] == SHIP_HOLD]
	for r in ship_holds:
		r["days_until"] = (as_date(r["esd"]) - today).days if r["esd"] else None
	months = [add_months(month_first, k) for k in range(4)]
	release_summary = {
		"rows": releases,
		"months": month_totals(releases, "likely_ship", months),
		"points": round(sum(r["release_points"] for r in releases), 2),
		"days": round(sum(r["release_points"] for r in releases) / per_day, 2) if per_day else None,
		"no_date": sum(1 for r in releases if not r["likely_ship"]),
	}
	next_last = month_end(add_months(month_first, 1))
	ship_hold_summary = {
		"rows": ship_holds,
		"months": month_totals(ship_holds, "esd", months[:3]),
		"total_amount": round(sum(r["amount"] for r in ship_holds), 2),
		"through_next_month_amount": round(
			sum(r["amount"] for r in ship_holds if r["esd"] and as_date(r["esd"]) <= next_last), 2
		),
		"week_amount": round(
			sum(r["amount"] for r in ship_holds if r["days_until"] is not None and r["days_until"] <= 7), 2
		),
	}

	# --- Monthly reporting: this month and the next two against goal ---
	goal_table = goals(values)

	def ship_month(row):
		when = as_date(row["esd"])
		if row["status"] == WFP and row["eta"]:
			when = max(when or as_date(row["eta"]), as_date(row["eta"]))
		return max(when or today, month_first)

	reporting = []
	for k in range(3):
		first = add_months(month_first, k)
		last = month_end(first)

		def in_month(when, first=first, last=last):
			return when is not None and first <= when <= last

		scheduled = [
			r
			for r in rows
			if (r["status"] != HELD or r["hold_reason"] == SHIP_HOLD)
			and not (r["status"] == WFP and r["going_to_miss"])
			and in_month(ship_month(r))
		]
		at_risk = [
			r
			for r in rows
			if (r["status"] == WFP and r["going_to_miss"] and in_month(ship_month(r)))
			or (k == 0 and r["status"] == HELD and not r["hold_reason"])
		]
		released = [r for r in releases if r["likely_ship"] and in_month(as_date(r["likely_ship"]))]
		days_in = workdays_left_in_month(today, holidays, include_today=False) if k == 0 else workdays_between(first, last, holidays)
		month_goal = goal_table.get(first, goal)
		figures = {
			"shipped_amount": round(shipped_mtd, 2) if k == 0 else 0,
			"scheduled_amount": round(sum(r["amount"] for r in scheduled), 2),
			"run_rate_amount": round(avg_30 * days_in, 2),
			"at_risk_amount": round(sum(r["amount"] for r in at_risk), 2),
			"release_amount": round(sum(r["amount"] for r in released), 2),
		}
		projected = sum(figures.values())
		known = [*scheduled, *released]
		known_amount = sum(r["amount"] for r in known) + (shipped_mtd if k == 0 else 0)
		known_com = sum(r["com"] for r in known) + (sum(x["com"] for x in shipped) if k == 0 else 0)
		reporting.append(
			{
				"month": first.isoformat(),
				"goal_amount": month_goal,
				**figures,
				"projected_amount": round(projected, 2),
				"projected_safe_amount": round(projected - figures["at_risk_amount"], 2),
				"goal_pct": round(projected / month_goal, 4) if month_goal else None,
				"com_pct": round(known_com / known_amount, 4) if known_amount else 0,
				"workdays": days_in,
				"orders": len(scheduled),
			}
		)

	# --- Proforma and will call ---
	def prowc_summary(kind):
		open_rows = [r for r in rows if r["prowc"] == kind]
		done = [x for x in shipped if x.get("prowc") == kind]
		done_amount = sum(x["amount"] for x in done)
		done_com = sum(x["com"] for x in done)
		return {
			"open_count": len(open_rows),
			"open_amount": round(sum(r["amount"] for r in open_rows), 2),
			"completed_count": len(done),
			"completed_amount": round(done_amount, 2),
			"com_pct": round(done_com / done_amount, 4) if done_amount else 0,
		}

	prowc = {
		"proforma": prowc_summary("Proforma"),
		"will_call": prowc_summary("Will Call"),
		"rows": [r for r in rows if r["prowc"]],
		"completed": [x for x in shipped if x.get("prowc")],
	}

	# --- Paint (outside finishing) ---
	paint_rows = [r for r in rows if r["status"] == PAINT]
	paint = {
		"rows": paint_rows,
		"total_amount": round(sum(r["amount"] for r in paint_rows), 2),
		"month_amount": round(
			sum(r["amount"] for r in paint_rows if r["esd"] and as_date(r["esd"]) <= month_last), 2
		),
		"month_count": sum(1 for r in paint_rows if r["esd"] and as_date(r["esd"]) <= month_last),
		"supplier_group": values.get("paint_supplier_group") or None,
	}

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

	board = {
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
		"queue": [r for r in rows if r["status"] != WFP and not r["hold_reason"]],
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
		"inbound": inbound,
		"daily": daily,
		"reporting": reporting,
		"releases": release_summary,
		"ship_holds": ship_hold_summary,
		"prowc": prowc,
		"paint": paint,
		"material_requests": manufacture_requests(today),
	}
	board["can_adjust"] = _can_adjust()
	return board if money else scrub(board)


@frappe.whitelist()
def get_board():
	roles = _roles()
	if not roles & VIEW_ROLES:
		frappe.throw("You need the Command Center Viewer role to see the production board.", frappe.PermissionError)
	return build_board(money=bool(roles & MONEY_ROLES))


# ---------------------------------------------------------------------------
# Floor corrections to build counts
# ---------------------------------------------------------------------------


def _can_adjust():
	return bool(_roles() & ADJUST_ROLES) and _has_field("Sales Order", build_points.ADJUST_FIELD)


def parse_counts(counts):
	"""Wanted order totals from the queue editor: ``{count key: number >= 0}``."""
	counts = build_points._json(counts, {})
	if not isinstance(counts, dict):
		frappe.throw('Send the counts as an object, for example {"runs_3c": 2}.')
	wanted = {}
	for key, value in counts.items():
		if key not in build_points.COUNT_KEYS:
			frappe.throw(f"Unknown build count: {key}")
		if value in (None, ""):
			continue
		try:
			number = float(value)
		except (TypeError, ValueError):
			frappe.throw(f"{COUNT_LABELS[key]} must be a number.")
		if number < 0 or number > MAX_COUNT:
			frappe.throw(f"{COUNT_LABELS[key]} must be between 0 and {MAX_COUNT}.")
		wanted[key] = round(number, 4)
	return wanted


def deltas_for(computed, wanted, current):
	"""New adjustments: what to add to the counted totals to reach ``wanted``.

	Keys left out of ``wanted`` keep their current adjustment.
	"""
	out = {}
	for key in build_points.COUNT_KEYS:
		if key in wanted:
			delta = round(wanted[key] - (computed.get(key) or 0), 4)
		else:
			delta = current.get(key) or 0
		if delta:
			out[key] = delta
	return out


def describe_change(before, after, computed):
	"""One line per count that changed, for the order's timeline."""
	lines = []
	for key in build_points.COUNT_KEYS:
		old = round(max((computed.get(key) or 0) + (before.get(key) or 0), 0), 4)
		new = round(max((computed.get(key) or 0) + (after.get(key) or 0), 0), 4)
		if old != new:
			counted = computed.get(key) or 0
			lines.append(f"{COUNT_LABELS[key]}: {old:g} → {new:g} (counted from the build: {counted:g})")
	return lines


@frappe.whitelist(methods=["POST"])
def set_build_counts(sales_order, counts=None, note=None, reset=0):
	"""Correct an open order's build counts (2C-6C runs and adders) from the queue.

	The counted totals still come from the pinned builds; this stores the
	difference on the Sales Order, so later recounts keep the correction. The new
	totals, points and hours are written to the order and the change is noted on
	its timeline. ``reset`` clears every correction.
	"""
	if not _roles() & ADJUST_ROLES:
		frappe.throw("Only manufacturing users can change build counts.", frappe.PermissionError)
	if not _has_field("Sales Order", build_points.ADJUST_FIELD):
		frappe.throw("Build count adjustment fields are missing; run bench migrate first.")
	doc = frappe.get_doc("Sales Order", sales_order)
	if doc.docstatus == 2 or doc.get("status") in ("Closed", "Completed"):
		state = doc.get("status") or "cancelled"
		frappe.throw(f"{sales_order} is {state}; its build counts can no longer change.")

	_, total = build_points.order_totals(doc)
	computed, before = total["computed"], total["adjustments"]
	after = {} if int(reset or 0) else deltas_for(computed, parse_counts(counts), before)
	note = (note or "").strip()[:500]
	changes = describe_change(before, after, computed)
	if not changes and note == (doc.get(build_points.ADJUST_NOTE_FIELD) or ""):
		frappe.throw("Nothing changed.")

	values = {
		build_points.ADJUST_FIELD: frappe.as_json(after) if after else None,
		build_points.ADJUST_NOTE_FIELD: note if after else None,
	}
	frappe.db.set_value("Sales Order", doc.name, values, update_modified=False)
	result = build_points.refresh_sales_order(doc.name)
	if changes:
		comment = "Build counts adjusted on the production board:\n" + "\n".join(changes)
		if note:
			comment += f"\nWhy: {note}"
		comment += f"\nBuild points now {result['points']:g}."
		doc.add_comment("Comment", comment)
	return {
		"sales_order": doc.name,
		"counts": {key: result[key] for key in build_points.COUNT_KEYS},
		"computed": computed,
		"adjustments": after,
		"adjust_note": values[build_points.ADJUST_NOTE_FIELD] or "",
		"points": result["points"],
		"hours": result["hours"],
	}
