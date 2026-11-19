"""Warehouse flow: what the warehouse does next, in ERPNext document terms.

One read-only endpoint, ``get_flow``, feeds the Command Center Manufacturing "Flow"
tab and the Shipping page's pick list. Where the production board mirrors the old
Schedule Wizard workbook (points, dollars, capacity), this follows the documents:

    Sales Order  ->  Work Order  ->  pick materials  ->  build  ->  pick & ship  ->  Delivery Note

* **Sales orders**: every submitted, open, not fully delivered order, with how many
  of its build lines (items with a BOM) already have work orders, and the one step
  it is waiting on (``STEPS``) with the next thing to do.
* **Work orders**: every open work order (draft, not started, in process, stopped)
  plus completed ones for open orders or finished in the last 14 days, in lanes.
* **Picking**: pieces to pull from stock for work orders (required minus transferred)
  and for orders ready to ship (ordered minus delivered or already picked, bundles
  expanded). Stock outside work-in-progress warehouses is handed to orders in
  ship-date order, so "short" means short after earlier orders take theirs.
* Open Pick Lists, draft Delivery Notes, and what shipped in the last 7 days.

No money is returned, so every viewer sees the same thing. Nothing is written.
"""

from datetime import date, timedelta

import frappe

from illumenate_lighting.illumenate_lighting.api import production_board as pb

VIEW_ROLES = pb.VIEW_ROLES | {"Stock Manager", "Stock User"}

# Order steps, earliest first. An order sits at the first step it hasn't finished.
STEPS = ("held", "needs_wo", "draft_wo", "waiting_parts", "to_pick", "building", "to_ship")
STEP_LABELS = {
	"held": "On hold",
	"needs_wo": "Needs work orders",
	"draft_wo": "Work orders in draft",
	"waiting_parts": "Waiting for parts",
	"to_pick": "Pick materials",
	"building": "Building",
	"to_ship": "Pick & ship",
}
NEXT_ACTION = {
	"held": "Clear the hold (hold reason, On Hold status or a stopped work order)",
	"needs_wo": "Create work orders for the build lines",
	"draft_wo": "Submit the draft work orders",
	"waiting_parts": "Wait for parts; purchasing has the ETA",
	"to_pick": "Pull materials and start the work orders",
	"building": "Finish the work orders",
	"to_ship": "Pick, pack and submit a delivery note",
}
# Work order lanes, in floor order.
WO_LANES = ("draft", "to_pick", "waiting_parts", "in_process", "completed", "stopped")
RECENT_DAYS = 14
SHIPPED_DAYS = 7
# Units counted as pieces; anything else (inches, feet, metres) is summed by unit.
PIECE_UOMS = {
	"nos",
	"no",
	"ea",
	"each",
	"unit",
	"units",
	"pc",
	"pcs",
	"piece",
	"pieces",
	"set",
	"sets",
	"pair",
	"kit",
	"box",
}
OPEN_PICK_EXCLUDE = ("Completed", "Cancelled")


# ---------------------------------------------------------------------------
# Pure helpers (no database)
# ---------------------------------------------------------------------------


def _num(value):
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def is_piece(uom):
	return (uom or "").strip().lower() in PIECE_UOMS


def qty_summary(rows):
	"""{"lines", "pieces", "other": [{"uom", "qty"}]} for pick rows with ``qty`` and ``uom``."""
	pieces, other, lines = 0.0, {}, 0
	for row in rows:
		qty = _num(row.get("qty"))
		if qty <= 0:
			continue
		lines += 1
		if is_piece(row.get("uom")):
			pieces += qty
		else:
			uom = row.get("uom") or "units"
			other[uom] = other.get(uom, 0) + qty
	return {
		"lines": lines,
		"pieces": round(pieces, 2),
		"other": [{"uom": u, "qty": round(q, 2)} for u, q in sorted(other.items())],
	}


def wo_lane(wo, short):
	"""Where a work order sits: draft, to_pick, waiting_parts, in_process, completed or stopped."""
	if int(wo.get("docstatus") or 0) == 0:
		return "draft"
	status = wo.get("status") or ""
	if status == "Stopped":
		return "stopped"
	if status in ("Completed", "Closed") or (
		_num(wo.get("qty")) and _num(wo.get("produced_qty")) >= _num(wo.get("qty"))
	):
		return "completed"
	if status == "In Process" or _num(wo.get("material_transferred_for_manufacturing")) > 0:
		return "in_process"
	return "waiting_parts" if short else "to_pick"


def wo_pick_lines(wo, required):
	"""Materials still to pull for one work order: required minus transferred.

	With "skip material transfer" ERPNext consumes straight from the source
	warehouse, so consumed quantity is what has left the shelf.
	"""
	moved = "consumed_qty" if int(wo.get("skip_transfer") or 0) else "transferred_qty"
	out = []
	for r in required:
		qty = round(_num(r.get("required_qty")) - _num(r.get(moved)), 4)
		if qty > 0:
			out.append(
				{
					"item": r.get("item_code"),
					"item_name": r.get("item_name") or r.get("item_code"),
					"qty": qty,
					"uom": r.get("stock_uom") or "",
					"warehouse": r.get("source_warehouse") or wo.get("source_warehouse") or "",
				}
			)
	return out


def build_coverage(lines, wos):
	"""How much of each build line is covered by work orders.

	Work orders match their ``sales_order_item`` first; older ones without it are
	shared out over the order's lines for the same item. Returns
	{line name: covered stock qty}.
	"""
	covered = {line["name"]: 0.0 for line in lines}
	loose = {}
	for w in wos:
		if (w.get("status") or "") == "Cancelled" or int(w.get("docstatus") or 0) == 2:
			continue
		if w.get("sales_order_item") in covered:
			covered[w["sales_order_item"]] += _num(w.get("qty"))
		else:
			key = w.get("production_item")
			loose[key] = loose.get(key, 0) + _num(w.get("qty"))
	for line in lines:
		left = loose.get(line["item_code"], 0)
		if left <= 0:
			continue
		want = max(_num(line.get("stock_qty") or line.get("qty")) - covered[line["name"]], 0)
		take = min(want, left)
		covered[line["name"]] += take
		loose[line["item_code"]] = left - take
	return covered


def needs_work_orders(lines, wos, item_meta):
	"""Build lines (items with a BOM) not yet covered by work orders or deliveries."""
	build = [
		ln for ln in lines if ln.get("bom_no") or (item_meta.get(ln["item_code"]) or {}).get("default_bom")
	]
	covered = build_coverage(build, wos)
	out = []
	for ln in build:
		factor = _num(ln.get("conversion_factor")) or 1
		total = _num(ln.get("stock_qty")) or _num(ln.get("qty")) * factor
		delivered = _num(ln.get("delivered_qty")) * factor
		missing = round(total - max(covered[ln["name"]], delivered), 4)
		if missing > 0:
			out.append(
				{
					"line": ln["name"],
					"item": ln["item_code"],
					"item_name": ln.get("item_name") or ln["item_code"],
					"qty": round(total, 4),
					"missing": missing,
				}
			)
	return build, out


def ship_pick_lines(lines, packed, item_meta):
	"""What is left to pick for shipping on one order, bundles expanded to their parts.

	A line still to pick = ordered - max(delivered, already picked). Non-stock lines
	without bundle parts (samples, services) and drop-ship lines are skipped.
	"""
	by_parent = {}
	for p in packed:
		by_parent.setdefault(p.get("parent_detail_docname"), []).append(p)
	out = []
	for ln in lines:
		if int(ln.get("delivered_by_supplier") or 0):
			continue
		qty = _num(ln.get("qty"))
		remaining = qty - max(_num(ln.get("delivered_qty")), _num(ln.get("picked_qty")))
		if remaining <= 0:
			continue
		parts = by_parent.get(ln["name"]) or []
		if parts:
			share = (qty - _num(ln.get("delivered_qty"))) / qty if qty else 0
			for p in parts:
				left = round(_num(p.get("qty")) * share - _num(p.get("picked_qty")), 4)
				if left > 0:
					out.append(
						{
							"item": p.get("item_code"),
							"item_name": p.get("item_name") or p.get("item_code"),
							"qty": left,
							"uom": p.get("uom") or "",
							"warehouse": p.get("warehouse") or ln.get("warehouse") or "",
							"kit": ln["item_code"],
						}
					)
			continue
		meta = item_meta.get(ln["item_code"]) or {}
		if not int(meta.get("is_stock_item", 1) or 0):
			continue
		factor = _num(ln.get("conversion_factor")) or 1
		out.append(
			{
				"item": ln["item_code"],
				"item_name": ln.get("item_name") or ln["item_code"],
				"qty": round(remaining * factor, 4),
				"uom": ln.get("stock_uom") or ln.get("uom") or "",
				"warehouse": ln.get("warehouse") or "",
			}
		)
	return out


def order_step(order, missing, wo_rows):
	"""The one step an open order is waiting on (see ``STEPS``)."""
	override = order.get("ill_production_status_override") or ""
	if (
		override == "Held"
		or order.get("ill_hold_reason")
		or order.get("status") == "On Hold"
		or any(w["lane"] == "stopped" for w in wo_rows)
	):
		return "held"
	if missing:
		return "needs_wo"
	if any(w["lane"] == "draft" for w in wo_rows):
		return "draft_wo"
	if override == "Waiting for parts":
		return "waiting_parts"
	if override == "Paint" or any(w["lane"] == "in_process" for w in wo_rows):
		return "building"
	if any(w["lane"] == "waiting_parts" for w in wo_rows):
		return "waiting_parts"
	if any(w["lane"] == "to_pick" for w in wo_rows):
		return "to_pick"
	return "to_ship"


def _esd(order):
	return pb.as_date(order.get("ill_estimated_ship_date") or order.get("delivery_date"))


def build_flow(data, today):
	"""The flow payload from already-read rows (pure, no database).

	``data`` keys: orders, so_items, packed, item_meta, wos, required, stock,
	incoming, pick_lists, pick_locations, draft_dns, shipped.
	"""
	orders = data["orders"]
	open_names = {o["name"] for o in orders}
	order_by_name = {o["name"]: o for o in orders}
	item_meta = data.get("item_meta") or {}
	lines_by_so, packed_by_so, wos_by_so, req_by_wo = {}, {}, {}, {}
	for ln in data.get("so_items") or []:
		lines_by_so.setdefault(ln["parent"], []).append(ln)
	for p in data.get("packed") or []:
		packed_by_so.setdefault(p["parent"], []).append(p)
	for r in data.get("required") or []:
		req_by_wo.setdefault(r["parent"], []).append(r)
	wos = [
		w
		for w in data.get("wos") or []
		if (w.get("status") or "") != "Cancelled" and int(w.get("docstatus") or 0) < 2
	]
	for w in wos:
		if w.get("sales_order"):
			wos_by_so.setdefault(w["sales_order"], []).append(w)

	def esd_key(so):
		o = order_by_name.get(so)
		return (_esd(o) if o else None) or date.max

	# --- Material: one hand-out of stock, earliest ship date first ---
	wo_pick = {}
	for w in wos:
		if int(w.get("docstatus") or 0) == 1 and w.get("status") not in ("Completed", "Closed", "Stopped"):
			wo_pick[w["name"]] = wo_pick_lines(w, req_by_wo.get(w["name"]) or [])
	ship_pick = {}
	pre_steps = {}
	for o in orders:
		build, missing = needs_work_orders(
			lines_by_so.get(o["name"]) or [], wos_by_so.get(o["name"]) or [], item_meta
		)
		pre_steps[o["name"]] = (build, missing)
		ship_pick[o["name"]] = ship_pick_lines(
			lines_by_so.get(o["name"]) or [], packed_by_so.get(o["name"]) or [], item_meta
		)

	needs = {}
	for name, rows in wo_pick.items():
		bucket = needs.setdefault("wo:" + name, {})
		for r in rows:
			bucket[r["item"]] = bucket.get(r["item"], 0) + r["qty"]
	wo_so = {w["name"]: w.get("sales_order") for w in wos}
	ranked = sorted(("wo:" + n for n in wo_pick), key=lambda k: (esd_key(wo_so.get(k[3:])), k))
	alloc = pb.allocate(ranked, needs, data.get("stock") or {}, data.get("incoming") or {})

	# --- Work orders ---
	wo_rows = []
	for w in wos:
		gap = alloc.get("wo:" + w["name"]) or {"short": {}, "eta": None, "no_po": []}
		lane = wo_lane(w, bool(gap["short"]))
		so = w.get("sales_order") or ""
		o = order_by_name.get(so)
		esd = _esd(o) if o else None
		pick = wo_pick.get(w["name"]) or []
		for r in pick:
			r["short"] = round(gap["short"].get(r["item"], 0), 4)
			r["on_hand"] = round((data.get("stock") or {}).get(r["item"], 0), 4)
		wo_rows.append(
			{
				"name": w["name"],
				"status": "Draft" if int(w.get("docstatus") or 0) == 0 else w.get("status"),
				"docstatus": int(w.get("docstatus") or 0),
				"lane": lane,
				"so": so,
				"so_open": so in open_names,
				"customer": (o or {}).get("customer_name")
				or (o or {}).get("customer")
				or w.get("customer_name")
				or "",
				"esd": esd.isoformat() if esd else None,
				"past_due": bool(esd and esd < today and lane != "completed"),
				"item": w.get("production_item"),
				"item_name": w.get("item_name") or w.get("production_item"),
				"qty": _num(w.get("qty")),
				"produced": _num(w.get("produced_qty")),
				"transferred": _num(w.get("material_transferred_for_manufacturing")),
				"created": str(w.get("creation") or "")[:10] or None,
				"planned_start": str(w.get("planned_start_date") or "")[:10] or None,
				"short": [{"item": i, "qty": round(q, 4)} for i, q in gap["short"].items()],
				"eta": gap["eta"].isoformat() if gap["eta"] else None,
				"no_po": gap["no_po"],
				"pick": pick if lane in ("to_pick", "in_process", "waiting_parts") else [],
			}
		)
	wo_rows.sort(key=lambda r: (WO_LANES.index(r["lane"]), r["esd"] or "9999", r["name"]))
	wo_by_so = {}
	for r in wo_rows:
		if r["so"]:
			wo_by_so.setdefault(r["so"], []).append(r)

	# --- Pick lists and draft delivery notes ---
	locs = {}
	for loc in data.get("pick_locations") or []:
		locs.setdefault(loc["parent"], []).append(loc)
	pick_lists = []
	for p in data.get("pick_lists") or []:
		rows = locs.get(p["name"]) or []
		sos = sorted({r.get("sales_order") for r in rows if r.get("sales_order")})
		summary = qty_summary(
			[
				{"qty": r.get("stock_qty") or r.get("qty"), "uom": r.get("stock_uom") or r.get("uom")}
				for r in rows
			]
		)
		pick_lists.append(
			{
				"name": p["name"],
				"purpose": p.get("purpose") or "",
				"status": "Draft" if int(p.get("docstatus") or 0) == 0 else p.get("status"),
				"docstatus": int(p.get("docstatus") or 0),
				"customer": p.get("customer") or "",
				"work_order": p.get("work_order") or "",
				"sales_orders": sos,
				"open_order": any(so in open_names for so in sos),
				"created": str(p.get("creation") or "")[:10] or None,
				**summary,
			}
		)
	dns = []
	for d in data.get("draft_dns") or []:
		sos = sorted(set(d.get("sales_orders") or []))
		dns.append(
			{
				"name": d["name"],
				"customer": d.get("customer_name") or d.get("customer") or "",
				"posting_date": str(d.get("posting_date") or "")[:10] or None,
				"sales_orders": sos,
				# A draft for an order that is closed or fully delivered is clean-up, not work.
				"open_order": any(so in open_names for so in sos),
			}
		)
	pl_by_so, dn_by_so = {}, {}
	for p in pick_lists:
		for so in p["sales_orders"]:
			pl_by_so.setdefault(so, []).append(p["name"])
	for d in dns:
		for so in d["sales_orders"]:
			dn_by_so.setdefault(so, []).append(d["name"])

	# --- Sales orders ---
	ship_needs = {}
	order_rows = []
	for o in sorted(orders, key=lambda x: (_esd(x) or date.max, x["name"])):
		build, missing = pre_steps[o["name"]]
		rows = wo_by_so.get(o["name"], [])
		step = order_step(o, missing, rows)
		esd = _esd(o)
		pick = ship_pick[o["name"]] if step == "to_ship" else []
		if pick:
			bucket = ship_needs.setdefault("so:" + o["name"], {})
			for r in pick:
				bucket[r["item"]] = bucket.get(r["item"], 0) + r["qty"]
		lanes = {}
		for r in rows:
			lanes[r["lane"]] = lanes.get(r["lane"], 0) + 1
		order_rows.append(
			{
				"so": o["name"],
				"customer": o.get("customer_name") or o.get("customer") or "",
				"status": o.get("status") or "",
				"esd": esd.isoformat() if esd else None,
				"esd_is_ship_date": bool(o.get("ill_estimated_ship_date")),
				"past_due": bool(esd and esd < today),
				"per_delivered": round(_num(o.get("per_delivered")), 1),
				"points": round(_num(o.get("ill_build_points")), 2),
				"hold_reason": o.get("ill_hold_reason") or "",
				"override": o.get("ill_production_status_override") or "",
				"notes": o.get("ill_floor_notes") or "",
				"step": step,
				"step_label": STEP_LABELS[step],
				"next": NEXT_ACTION[step],
				"build_lines": len(build),
				"build_covered": len(build) - len(missing),
				"needs_wo": missing,
				"work_orders": [r["name"] for r in rows],
				"wo_lanes": lanes,
				"parts_short": any(
					r["short"] for r in rows if r["lane"] in ("waiting_parts", "in_process", "to_pick")
				),
				"pick": pick,
				"pick_lists": pl_by_so.get(o["name"], []),
				"draft_dns": dn_by_so.get(o["name"], []),
			}
		)
	# Shipping picks get what stock is left after the work orders took theirs.
	left = dict(data.get("stock") or {})
	for gap_key, need in needs.items():
		got = alloc.get(gap_key) or {"short": {}}
		for item, qty in need.items():
			left[item] = left.get(item, 0) - (qty - got["short"].get(item, 0))
	ship_alloc = pb.allocate(
		[k for k in ("so:" + r["so"] for r in order_rows) if k in ship_needs], ship_needs, left, {}
	)
	for r in order_rows:
		gap = ship_alloc.get("so:" + r["so"]) or {"short": {}}
		for p in r["pick"]:
			p["short"] = round(gap["short"].get(p["item"], 0), 4)
		r["pick_short"] = any(p["short"] for p in r["pick"])
		r["pick_summary"] = qty_summary(r["pick"])

	# --- Summary for the flow strip and the to-do list ---
	steps = {s: 0 for s in STEPS}
	for r in order_rows:
		steps[r["step"]] += 1
	lanes = {k: 0 for k in WO_LANES}
	for r in wo_rows:
		lanes[r["lane"]] += 1
	build_orders = [r for r in order_rows if r["build_lines"]]
	prod_pick = [p for r in wo_rows if r["lane"] in ("to_pick", "in_process") for p in r["pick"]]
	ship_rows = [r for r in order_rows if r["step"] == "to_ship"]
	ship_pick_rows = [p for r in ship_rows for p in r["pick"]]
	shipped = data.get("shipped") or []
	summary = {
		"orders": len(order_rows),
		"steps": steps,
		"build_orders": len(build_orders),
		"stock_only": len(order_rows) - len(build_orders),
		"covered": sum(1 for r in build_orders if r["build_covered"] == r["build_lines"]),
		"partly": sum(1 for r in build_orders if 0 < r["build_covered"] < r["build_lines"]),
		"uncovered": sum(1 for r in build_orders if r["build_covered"] == 0),
		"lines_need_wo": sum(len(r["needs_wo"]) for r in order_rows),
		"wo_lanes": lanes,
		"wo_open": sum(v for k, v in lanes.items() if k != "completed"),
		"wo_no_open_order": sum(1 for r in wo_rows if r["lane"] != "completed" and not r["so_open"]),
		"pick_production": {
			"work_orders": sum(1 for r in wo_rows if r["lane"] in ("to_pick", "in_process") and r["pick"]),
			**qty_summary(prod_pick),
		},
		"pick_shipping": {
			"orders": sum(1 for r in ship_rows if r["pick"]),
			"short_orders": sum(1 for r in ship_rows if r["pick_short"]),
			**qty_summary(ship_pick_rows),
		},
		"past_due": sum(1 for r in order_rows if r["past_due"]),
		"pick_lists_open": sum(1 for p in pick_lists if p["open_order"]),
		"pick_lists_stale": sum(1 for p in pick_lists if not p["open_order"]),
		"draft_dns": sum(1 for d in dns if d["open_order"]),
		"draft_dns_stale": sum(1 for d in dns if not d["open_order"]),
		"shipped_week": len(shipped),
	}
	return {
		"today": today.isoformat(),
		"summary": summary,
		"orders": order_rows,
		"work_orders": wo_rows,
		"pick_lists": pick_lists,
		"draft_dns": dns,
		"shipped": shipped,
		"step_labels": STEP_LABELS,
	}


# ---------------------------------------------------------------------------
# Reading ERPNext
# ---------------------------------------------------------------------------


def _child_rows(doctype, parent_type, names, wanted, order_by="idx asc"):
	if not names:
		return []
	return frappe.get_all(
		doctype,
		filters={"parent": ["in", list(names)], "parenttype": parent_type},
		fields=["parent", "name", *pb._fields(doctype, wanted)],
		order_by=order_by,
		limit_page_length=0,
	)


def sales_order_lines(names):
	return _child_rows(
		"Sales Order Item",
		"Sales Order",
		names,
		[
			"item_code",
			"item_name",
			"qty",
			"stock_qty",
			"uom",
			"stock_uom",
			"conversion_factor",
			"delivered_qty",
			"picked_qty",
			"warehouse",
			"bom_no",
			"delivered_by_supplier",
		],
	)


def packed_lines(names):
	return _child_rows(
		"Packed Item",
		"Sales Order",
		names,
		[
			"parent_item",
			"parent_detail_docname",
			"item_code",
			"item_name",
			"qty",
			"uom",
			"picked_qty",
			"warehouse",
		],
	)


def item_info(codes):
	if not codes:
		return {}
	rows = frappe.get_all(
		"Item",
		filters={"name": ["in", list(codes)]},
		fields=pb._fields("Item", ["name", "default_bom", "is_stock_item"]),
		limit_page_length=0,
	)
	return {r["name"]: r for r in rows}


WO_FIELDS = [
	"name",
	"status",
	"docstatus",
	"sales_order",
	"sales_order_item",
	"production_item",
	"item_name",
	"qty",
	"produced_qty",
	"material_transferred_for_manufacturing",
	"skip_transfer",
	"source_warehouse",
	"wip_warehouse",
	"planned_start_date",
	"creation",
]


def flow_work_orders(order_names, today):
	"""Open work orders, every work order on an open order, and ones completed recently."""
	fields = pb._fields("Work Order", WO_FIELDS)
	found = {}
	queries = [
		{"docstatus": ["<", 2], "status": ["in", ["Draft", "Not Started", "In Process", "Stopped"]]},
		{
			"docstatus": 1,
			"status": "Completed",
			"modified": [">=", (today - timedelta(days=RECENT_DAYS)).isoformat()],
		},
	]
	if order_names:
		queries.append({"docstatus": ["<", 2], "sales_order": ["in", list(order_names)]})
	for filters in queries:
		for w in frappe.get_all("Work Order", filters=filters, fields=fields, limit_page_length=0):
			found[w["name"]] = w
	return list(found.values())


def required_materials(wos):
	names = [
		w["name"]
		for w in wos
		if int(w.get("docstatus") or 0) == 1
		and w.get("status") not in ("Completed", "Closed", "Stopped", "Cancelled")
	]
	return _child_rows(
		"Work Order Item",
		"Work Order",
		names,
		[
			"item_code",
			"item_name",
			"required_qty",
			"transferred_qty",
			"consumed_qty",
			"source_warehouse",
			"stock_uom",
		],
	)


def shelf_stock(items, exclude_warehouses):
	"""{item: actual qty} across warehouses, leaving out work-in-progress ones."""
	stock = {}
	if not items:
		return stock
	for row in frappe.get_all(
		"Bin",
		filters={"item_code": ["in", list(items)]},
		fields=["item_code", "warehouse", "actual_qty"],
		limit_page_length=0,
	):
		if row.get("warehouse") in exclude_warehouses:
			continue
		stock[row["item_code"]] = stock.get(row["item_code"], 0) + _num(row.get("actual_qty"))
	return stock


def open_pick_lists():
	lists = frappe.get_all(
		"Pick List",
		filters={"docstatus": ["<", 2], "status": ["not in", list(OPEN_PICK_EXCLUDE)]},
		fields=pb._fields(
			"Pick List", ["name", "purpose", "status", "docstatus", "customer", "work_order", "creation"]
		),
		order_by="creation desc",
		limit_page_length=200,
	)
	locations = _child_rows(
		"Pick List Item",
		"Pick List",
		[p["name"] for p in lists],
		["item_code", "qty", "stock_qty", "picked_qty", "uom", "stock_uom", "warehouse", "sales_order"],
	)
	return lists, locations


def draft_delivery_notes():
	notes = frappe.get_all(
		"Delivery Note",
		filters={"docstatus": 0, "is_return": 0},
		fields=["name", "customer", "customer_name", "posting_date"],
		order_by="modified desc",
		limit_page_length=200,
	)
	links = {}
	for row in _child_rows(
		"Delivery Note Item", "Delivery Note", [n["name"] for n in notes], ["against_sales_order"]
	):
		if row.get("against_sales_order"):
			links.setdefault(row["parent"], []).append(row["against_sales_order"])
	for n in notes:
		n["sales_orders"] = links.get(n["name"], [])
	return notes


def shipped_recently(today):
	rows = frappe.get_all(
		"Delivery Note",
		filters={
			"docstatus": 1,
			"is_return": 0,
			"posting_date": [">=", (today - timedelta(days=SHIPPED_DAYS - 1)).isoformat()],
		},
		fields=["name", "customer_name", "posting_date"],
		order_by="posting_date desc",
		limit_page_length=200,
	)
	return [
		{
			"name": r["name"],
			"customer": r.get("customer_name") or "",
			"posting_date": str(r.get("posting_date") or "")[:10],
		}
		for r in rows
	]


def read_flow(today):
	orders = pb.open_orders()
	names = [o["name"] for o in orders]
	so_items = sales_order_lines(names)
	packed = packed_lines(names)
	wos = flow_work_orders(names, today)
	required = required_materials(wos)
	codes = {ln["item_code"] for ln in so_items} | {
		w.get("production_item") for w in wos if w.get("production_item")
	}
	stock_items = (
		{r["item_code"] for r in required}
		| {ln["item_code"] for ln in so_items}
		| {p["item_code"] for p in packed}
	)
	wip = {w.get("wip_warehouse") for w in wos if w.get("wip_warehouse")}
	pick_lists, pick_locations = open_pick_lists()
	return {
		"orders": orders,
		"so_items": so_items,
		"packed": packed,
		"item_meta": item_info(codes),
		"wos": wos,
		"required": required,
		"stock": shelf_stock(stock_items, wip),
		"incoming": pb.incoming_purchases({r["item_code"] for r in required}),
		"pick_lists": pick_lists,
		"pick_locations": pick_locations,
		"draft_dns": draft_delivery_notes(),
		"shipped": shipped_recently(today),
	}


@frappe.whitelist()
def get_flow():
	if not set(frappe.get_roles(frappe.session.user)) & VIEW_ROLES:
		frappe.throw(
			"You need the Command Center Viewer role to see the warehouse flow.", frappe.PermissionError
		)
	today = pb.as_date(frappe.utils.now_datetime())
	return build_flow(read_flow(today), today)
