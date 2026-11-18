"""Purchasing tracking: vendor status, lead times and ETAs on Purchase Orders, inbound shipments.

* ``lead_time`` is the one lead-time rule every purchasing view uses (plan 3.7):
  PO line -> PO header -> live Supplier Quotation -> Supplier default -> Item ->
  item group default (ilL-Purchasing-Settings, walking up the group tree).
* Document hooks keep the Command Center purchasing board current without anyone
  re-typing dates: a new PO gets its lead time, ETA, freight mode and "Not sent"; an
  email sent from the PO marks it Sent; a full receipt marks it Delivered and joins the
  open inbound shipment; a forwarder/broker bill fills the shipment's actual cost.
* Every hook is best-effort: a tracking failure is logged and never blocks a submit.
"""

from datetime import timedelta

import frappe

from illumenate_lighting.illumenate_lighting.api.production_board import _fields, _has_field, as_date

SETTINGS = "ilL-Purchasing-Settings"
SHIPMENT = "ilL-Inbound-Shipment"
SHIPMENT_PO = "ilL-Child-Shipment-PO"
SHIPMENT_COST = "ilL-Child-Shipment-Cost"

VENDOR_STATUSES = ("Not sent", "Sent", "Confirmed", "In production", "Shipped", "Delivered")
ISSUE = "Issue"
SHIPMENT_STATUSES = (
	"Planned",
	"Booked",
	"In transit",
	"At port / customs",
	"Cleared",
	"Out for delivery",
	"Delivered",
	"Costs final",
	"Cancelled",
)
SHIPMENT_CLOSED = ("Delivered", "Costs final", "Cancelled")
COST_TYPES = (
	"Freight",
	"Duty",
	"Tariff (additional)",
	"MPF / HMF",
	"Brokerage",
	"Insurance",
	"Drayage / delivery",
	"Storage / demurrage",
	"Sales / use tax",
	"Other",
)
ALLOCATIONS = ("By value", "By qty", "Manual")
LEAD_SOURCES = ("po line", "po", "quote", "supplier", "item", "group default")

DEFAULTS = {
	"company": "ilLumenate Lighting",
	"default_warehouse": "Stores - ilL",
	"safety_days": 3,
	"reorder_lookback_days": 90,
	"hts_stale_days": 90,
	"quote_expiry_warn_days": 7,
	"vendor_confirm_warn_days": 3,
	"receipt_bill_warn_days": 14,
	"lcv_warn_days": 30,
}

# Decisions D2/D3: what is capitalized into inventory, and how it is spread. Used when the
# settings table has no row for a cost type.
FALLBACK_COSTS = {
	"Freight": {"include_in_landed_cost": 1, "allocation": "By qty", "estimate_pct_of_value": 8},
	"Duty": {"include_in_landed_cost": 1, "allocation": "By value", "estimate_pct_of_value": 0},
	"Tariff (additional)": {
		"include_in_landed_cost": 1,
		"allocation": "By value",
		"estimate_pct_of_value": 0,
	},
	"MPF / HMF": {"include_in_landed_cost": 1, "allocation": "By value", "estimate_pct_of_value": 0.4},
	"Brokerage": {"include_in_landed_cost": 1, "allocation": "By value", "estimate_pct_of_value": 0},
	"Insurance": {"include_in_landed_cost": 1, "allocation": "By value", "estimate_pct_of_value": 0},
	"Drayage / delivery": {"include_in_landed_cost": 1, "allocation": "By qty", "estimate_pct_of_value": 0},
	"Storage / demurrage": {
		"include_in_landed_cost": 0,
		"allocation": "By value",
		"estimate_pct_of_value": 0,
	},
	"Sales / use tax": {"include_in_landed_cost": 0, "allocation": "By value", "estimate_pct_of_value": 0},
	"Other": {"include_in_landed_cost": 0, "allocation": "By value", "estimate_pct_of_value": 0},
}


# ---------------------------------------------------------------------------
# Pure helpers (no database)
# ---------------------------------------------------------------------------


def _get(row, key):
	if row is None:
		return None
	return row.get(key) if hasattr(row, "get") else getattr(row, key, None)


def _set(row, key, value):
	if isinstance(row, dict):
		row[key] = value
	else:
		row.set(key, value)


def _num(value):
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def resolve_lead(candidates):
	"""First positive whole-day value from ``[(days, source), ...]`` in precedence order."""
	for value, source in candidates:
		if value in (None, ""):
			continue
		try:
			days = int(float(value))
		except (TypeError, ValueError):
			continue
		if days > 0:
			return days, source
	return None, "none"


def group_lead(group, parents, leads):
	"""Lead time for an item group: its own row, else the nearest ancestor's."""
	seen = set()
	while group and group not in seen:
		seen.add(group)
		if leads.get(group):
			return leads[group]
		group = parents.get(group)
	return None


def vendor_rank(status):
	"""Position in the vendor sequence; blank counts as Not sent, Issue as outside it."""
	if status == ISSUE:
		return None
	return VENDOR_STATUSES.index(status) if status in VENDOR_STATUSES else 0


def forward_status(current, target):
	"""``target`` when it is later in the sequence than ``current``; never backwards, never over Issue."""
	now, then = vendor_rank(current), vendor_rank(target)
	if now is None or then is None or then <= now:
		return None
	return target


def shipment_vendor_status(status):
	"""The PO vendor status a shipment status implies."""
	if status in ("Delivered", "Costs final"):
		return "Delivered"
	if status in ("Booked", "In transit", "At port / customs", "Cleared", "Out for delivery"):
		return "Shipped"
	return None


def eta_from_lead(start, lead):
	start = as_date(start)
	return start + timedelta(days=int(lead)) if start and lead else None


def cost_defaults(cost_type, settings):
	rows = (settings or {}).get("cost_defaults") or {}
	return rows.get(cost_type) or FALLBACK_COSTS.get(cost_type) or FALLBACK_COSTS["Other"]


def fill_cost_defaults(row, settings):
	"""A cost line with no allocation yet is new: give it the cost type's defaults."""
	if _get(row, "allocation"):
		if not _get(row, "expense_account"):
			account = cost_defaults(_get(row, "cost_type"), settings).get("expense_account")
			if account:
				_set(row, "expense_account", account)
		return row
	rule = cost_defaults(_get(row, "cost_type"), settings)
	_set(row, "allocation", rule.get("allocation") or "By value")
	_set(row, "include_in_landed_cost", 1 if rule.get("include_in_landed_cost") else 0)
	if not _get(row, "expense_account") and rule.get("expense_account"):
		_set(row, "expense_account", rule["expense_account"])
	return row


def cost_basis_amount(line):
	"""What a cost line counts as for landed cost %: the bill when it is in, else the estimate."""
	actual = _get(line, "actual_amount")
	return _num(actual) if actual not in (None, "") else _num(_get(line, "estimated_amount"))


def shipment_totals(po_rows, costs):
	goods = round(sum(_num(_get(r, "po_value")) for r in po_rows), 2)
	estimated = round(sum(_num(_get(c, "estimated_amount")) for c in costs), 2)
	billed = [c for c in costs if _get(c, "actual_amount") not in (None, "")]
	actual = round(sum(_num(_get(c, "actual_amount")) for c in billed), 2)
	# Like for like: the estimate of the lines that have been billed.
	billed_estimate = sum(_num(_get(c, "estimated_amount")) for c in billed)
	basis = sum(cost_basis_amount(c) for c in costs)
	return {
		"goods_value": goods,
		"estimated_cost_total": estimated,
		"actual_cost_total": actual,
		"variance": round(actual - billed_estimate, 2) if billed else 0,
		"landed_cost_pct": round(basis / goods * 100, 2) if goods else 0,
	}


def po_shares(po_rows):
	"""Share of costs per PO row: the typed share_pct, else by PO value."""
	typed = [_num(_get(r, "share_pct")) for r in po_rows]
	if any(typed):
		return typed
	total = sum(_num(_get(r, "po_value")) for r in po_rows)
	return [round(_num(_get(r, "po_value")) / total * 100, 2) if total else 0 for r in po_rows]


def bill_amount_for(line, lines_on_bill, bill_total, bill_items):
	"""Actual amount for one cost line from the bill it links.

	A bill that covers one cost line gives its whole net amount. A bill split across
	several lines (one broker bill with duty and brokerage) gives each line the bill
	items that post to that line's account; without an account it stays blank.
	"""
	if len(lines_on_bill) <= 1:
		return round(_num(bill_total), 2)
	account = _get(line, "expense_account")
	if not account:
		return None
	hits = [i for i in bill_items if _get(i, "expense_account") == account]
	return (
		round(sum(_num(_get(i, "base_net_amount") or _get(i, "amount")) for i in hits), 2) if hits else None
	)


def fill_actuals(costs, invoice, bill_total, bill_items):
	"""Fill blank actual amounts on the cost lines that link ``invoice``. Returns lines changed."""
	on_bill = [c for c in costs if _get(c, "purchase_invoice") == invoice]
	changed = 0
	for line in on_bill:
		if _get(line, "actual_amount") not in (None, "", 0, 0.0):
			continue
		amount = bill_amount_for(line, on_bill, bill_total, bill_items)
		if amount is not None:
			_set(line, "actual_amount", amount)
			changed += 1
	return changed


def estimate_costs(goods_value, settings, hts_lines=(), mode=None):
	"""Seed cost lines for a new shipment.

	``hts_lines``: [{"value", "duty_pct", "tariff_pct"}] per PO line with an HTS code.
	Freight and the rest use the settings' % of goods value or flat amount; duty and
	additional tariffs use the HTS rates when any line has them.
	"""
	duty = sum(_num(r.get("value")) * _num(r.get("duty_pct")) / 100 for r in hts_lines)
	tariff = sum(_num(r.get("value")) * _num(r.get("tariff_pct")) / 100 for r in hts_lines)
	lines = []
	for cost_type in COST_TYPES:
		rule = cost_defaults(cost_type, settings)
		if cost_type == "Duty" and duty:
			amount = duty
		elif cost_type == "Tariff (additional)" and tariff:
			amount = tariff
		else:
			amount = _num(goods_value) * _num(rule.get("estimate_pct_of_value")) / 100 + _num(
				rule.get("estimate_flat_amount")
			)
		if not amount:
			continue
		lines.append(
			{
				"cost_type": cost_type,
				"description": f"Estimate ({mode})" if mode else "Estimate",
				"estimated_amount": round(amount, 2),
				"include_in_landed_cost": 1 if rule.get("include_in_landed_cost") else 0,
				"expense_account": rule.get("expense_account"),
				"allocation": rule.get("allocation") or "By value",
			}
		)
	return lines


# ---------------------------------------------------------------------------
# Settings and lead times
# ---------------------------------------------------------------------------


def read_settings():
	"""ilL-Purchasing-Settings as a plain dict, with code defaults for anything unset."""
	out = dict(DEFAULTS, group_leads={}, cost_defaults={})
	try:
		if frappe.db.exists("DocType", SETTINGS):
			doc = frappe.get_cached_doc(SETTINGS)
			for key in DEFAULTS:
				value = doc.get(key)
				if value not in (None, ""):
					out[key] = value
			out["group_leads"] = {
				r.item_group: int(r.lead_time_days or 0)
				for r in doc.get("default_lead_times") or []
				if r.item_group
			}
			for r in doc.get("cost_type_defaults") or []:
				if r.cost_type:
					out["cost_defaults"][r.cost_type] = {
						"include_in_landed_cost": int(r.include_in_landed_cost or 0),
						"expense_account": r.expense_account,
						"allocation": r.allocation or FALLBACK_COSTS.get(r.cost_type, {}).get("allocation"),
						"estimate_pct_of_value": _num(r.estimate_pct_of_value),
						"estimate_flat_amount": _num(r.get("estimate_flat_amount")),
					}
	except Exception:
		frappe.log_error(title="Purchasing settings unreadable; using defaults")
	return out


class LeadTimes:
	"""Bulk-loaded lead-time sources for a set of items and suppliers (no per-row queries)."""

	def __init__(self, items, suppliers=(), settings=None, today=None):
		self.today = as_date(today or frappe.utils.nowdate())
		self.settings = settings if settings is not None else read_settings()
		items = sorted({i for i in items if i})
		self.items, self.item_supplier, self.suppliers = {}, {}, {}
		self.quotes, self.by_sq, self.groups = {}, {}, {}
		if items:
			for r in frappe.get_all(
				"Item",
				filters={"name": ["in", items]},
				fields=_fields("Item", ["name", "item_name", "item_group", "lead_time_days"]),
				limit_page_length=0,
			):
				self.items[r.name] = r
			for r in frappe.get_all(
				"Item Default",
				filters={"parent": ["in", items], "parenttype": "Item", "default_supplier": ["is", "set"]},
				fields=["parent", "default_supplier"],
				limit_page_length=0,
			):
				self.item_supplier.setdefault(r.parent, r.default_supplier)
			self._load_quotes(items)
		wanted = sorted({s for s in suppliers if s} | set(self.item_supplier.values()))
		if wanted and _has_field("Supplier", "ill_default_lead_time_days"):
			for r in frappe.get_all(
				"Supplier",
				filters={"name": ["in", wanted]},
				fields=["name", "ill_default_lead_time_days"],
				limit_page_length=0,
			):
				self.suppliers[r.name] = r.ill_default_lead_time_days
		if self.settings.get("group_leads"):
			for r in frappe.get_all("Item Group", fields=["name", "parent_item_group"], limit_page_length=0):
				self.groups[r.name] = r.parent_item_group

	def _load_quotes(self, items):
		rows = frappe.get_all(
			"Supplier Quotation Item",
			filters={"item_code": ["in", items], "docstatus": 1},
			fields=["parent", "item_code", "lead_time_days"],
			limit_page_length=0,
		)
		if not rows:
			return
		heads = {
			h.name: h
			for h in frappe.get_all(
				"Supplier Quotation",
				filters={"name": ["in", list({r.parent for r in rows})], "docstatus": 1},
				fields=["name", "supplier", "valid_till", "transaction_date", "status"],
				limit_page_length=0,
			)
		}
		latest = {}
		for r in rows:
			self.by_sq[(r.parent, r.item_code)] = r.lead_time_days
			head = heads.get(r.parent)
			if not head or head.status in ("Expired", "Stopped", "Cancelled"):
				continue
			valid = as_date(head.valid_till)
			if valid and valid < self.today:
				continue
			key = (r.item_code, head.supplier)
			when = as_date(head.transaction_date)
			if r.lead_time_days and (key not in latest or (when and when >= latest[key][0])):
				latest[key] = (when, r.lead_time_days)
		self.quotes = {k: v[1] for k, v in latest.items()}

	def supplier_for(self, item):
		return self.item_supplier.get(item)

	def get(self, item, supplier=None, po_row=None, po=None):
		"""(days, source) by the plan 3.7 precedence."""
		supplier = supplier or self.item_supplier.get(item)
		quote = None
		sq = _get(po_row, "supplier_quotation")
		if sq:
			quote = self.by_sq.get((sq, item))
		if not quote:
			quote = self.quotes.get((item, supplier))
		info = self.items.get(item) or {}
		return resolve_lead(
			[
				(_get(po_row, "ill_est_lead_time_days"), "po line"),
				(_get(po, "ill_est_lead_time_days"), "po"),
				(quote, "quote"),
				(self.suppliers.get(supplier), "supplier"),
				(info.get("lead_time_days"), "item"),
				(
					group_lead(info.get("item_group"), self.groups, self.settings.get("group_leads") or {}),
					"group default",
				),
			]
		)


def lead_time(item, supplier, po_row=None, po=None):
	"""(days, source) for one item from one supplier. Sources: see LEAD_SOURCES, or "none"."""
	return LeadTimes([item], [supplier] if supplier else []).get(item, supplier, po_row=po_row, po=po)


# ---------------------------------------------------------------------------
# Shared write helpers
# ---------------------------------------------------------------------------


def comment(doctype, name, text):
	"""Leave a "Command Center:" Info comment, like the gateway's audit trail."""
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": doctype,
			"reference_name": name,
			"content": "Command Center: " + text,
		}
	).insert(ignore_permissions=True)  # audit trail only


def _tracked(doctype):
	return _has_field(doctype, "ill_vendor_status")


def _log(what):
	frappe.log_error(title=f"Purchasing hook failed: {what}")


# ---------------------------------------------------------------------------
# Document hooks (all best-effort)
# ---------------------------------------------------------------------------


def prefill_po_tracking(doc, method=None):
	"""Purchase Order before_insert: lead time, ETA, freight mode and vendor status."""
	try:
		if not doc.meta.has_field("ill_vendor_status"):
			return
		rows = doc.get("items") or []
		leads = LeadTimes([r.item_code for r in rows], [doc.supplier] if doc.supplier else [])
		best = (None, "none")
		for row in rows:
			days, source = leads.get(row.item_code, doc.supplier, po_row=row)
			if days and (not best[0] or days > best[0]) and source not in ("po line", "po"):
				best = (days, source)
		if not doc.get("ill_est_lead_time_days") and best[0]:
			doc.ill_est_lead_time_days = best[0]
		lead = doc.get("ill_est_lead_time_days")
		if not doc.get("ill_eta") and lead:
			doc.ill_eta = eta_from_lead(doc.transaction_date or frappe.utils.nowdate(), lead)
		if (
			not doc.get("ill_freight_mode")
			and doc.supplier
			and _has_field("Supplier", "ill_default_freight_mode")
		):
			mode = frappe.db.get_value("Supplier", doc.supplier, "ill_default_freight_mode")
			if mode:
				doc.ill_freight_mode = mode
		if not doc.get("ill_vendor_status"):
			doc.ill_vendor_status = "Not sent"
	except Exception:
		_log("prefill_po_tracking")


def on_po_submit(doc, method=None):
	"""Purchase Order on_submit: make sure there is an ETA."""
	try:
		if not doc.meta.has_field("ill_eta") or doc.get("ill_eta"):
			return
		lead = doc.get("ill_est_lead_time_days")
		if not lead:
			rows = doc.get("items") or []
			leads = LeadTimes([r.item_code for r in rows], [doc.supplier] if doc.supplier else [])
			lead = max((leads.get(r.item_code, doc.supplier, po_row=r)[0] or 0 for r in rows), default=0)
		eta = eta_from_lead(doc.transaction_date, lead) if lead else as_date(doc.get("schedule_date"))
		if eta:
			doc.db_set("ill_eta", eta, update_modified=False)
	except Exception:
		_log("on_po_submit")


def on_communication(doc, method=None):
	"""Communication after_insert: an email sent from a submitted PO marks it Sent."""
	try:
		if (
			doc.reference_doctype != "Purchase Order"
			or doc.sent_or_received != "Sent"
			or not doc.reference_name
		):
			return
		if not _tracked("Purchase Order"):
			return
		po = frappe.db.get_value(
			"Purchase Order", doc.reference_name, ["name", "docstatus", "ill_vendor_status"], as_dict=True
		)
		if not po or po.docstatus != 1 or (po.ill_vendor_status or "Not sent") != "Not sent":
			return
		today = frappe.utils.nowdate()
		frappe.db.set_value(
			"Purchase Order",
			po.name,
			{"ill_vendor_status": "Sent", "ill_sent_on": today},
			update_modified=False,
		)
		comment("Purchase Order", po.name, f"marked Sent to vendor (email sent {today})")
	except Exception:
		_log("on_communication")


def on_receipt_submit(doc, method=None):
	"""Purchase Receipt on_submit: fully received POs are Delivered; join the open shipment."""
	try:
		pos = sorted({r.purchase_order for r in doc.get("items") or [] if r.get("purchase_order")})
		if not pos:
			return
		if _tracked("Purchase Order"):
			for po in frappe.get_all(
				"Purchase Order",
				filters={"name": ["in", pos]},
				fields=["name", "per_received", "ill_vendor_status"],
				limit_page_length=0,
			):
				if _num(po.per_received) >= 100 and forward_status(po.ill_vendor_status, "Delivered"):
					frappe.db.set_value(
						"Purchase Order", po.name, "ill_vendor_status", "Delivered", update_modified=False
					)
					comment("Purchase Order", po.name, f"marked Delivered (received on {doc.name})")
		if not frappe.db.exists("DocType", SHIPMENT):
			return
		parents = frappe.get_all(
			SHIPMENT_PO,
			filters={"purchase_order": ["in", pos], "parenttype": SHIPMENT},
			pluck="parent",
			limit_page_length=0,
		)
		if not parents:
			return
		open_shipments = frappe.get_all(
			SHIPMENT,
			filters={"name": ["in", list(set(parents))], "status": ["not in", list(SHIPMENT_CLOSED)]},
			pluck="name",
			limit_page_length=0,
		)
		if len(open_shipments) != 1:
			return  # none, or ambiguous: the team links it by hand
		shipment = frappe.get_doc(SHIPMENT, open_shipments[0])
		if any(r.purchase_receipt == doc.name for r in shipment.get("receipts") or []):
			return
		shipment.append("receipts", {"purchase_receipt": doc.name})
		shipment.flags.ignore_permissions = True  # tracking link only
		shipment.save()
		comment(SHIPMENT, shipment.name, f"receipt {doc.name} added when it was submitted")
	except Exception:
		_log("on_receipt_submit")


def on_invoice_submit(doc, method=None):
	"""Purchase Invoice on_submit: fill the actual amount on shipment cost lines that link it."""
	try:
		if not frappe.db.exists("DocType", SHIPMENT):
			return
		parents = frappe.get_all(
			SHIPMENT_COST,
			filters={"purchase_invoice": doc.name, "parenttype": SHIPMENT},
			pluck="parent",
			limit_page_length=0,
		)
		for name in sorted(set(parents)):
			shipment = frappe.get_doc(SHIPMENT, name)
			items = [
				{"expense_account": r.expense_account, "base_net_amount": r.base_net_amount}
				for r in doc.get("items") or []
			]
			if fill_actuals(shipment.get("costs") or [], doc.name, doc.base_net_total, items):
				shipment.flags.ignore_permissions = True
				shipment.save()
				comment(SHIPMENT, name, f"actual cost filled from bill {doc.name}")
	except Exception:
		_log("on_invoice_submit")


# ---------------------------------------------------------------------------
# ilL-Inbound-Shipment controller logic
# ---------------------------------------------------------------------------


def validate_shipment(doc, settings=None):
	settings = settings or read_settings()
	pos = doc.get("purchase_orders") or []
	missing = [r.purchase_order for r in pos if r.purchase_order and not r.get("po_value")]
	if missing:
		values = {
			r.name: r
			for r in frappe.get_all(
				"Purchase Order",
				filters={"name": ["in", missing]},
				fields=["name", "base_net_total", "supplier"],
				limit_page_length=0,
			)
		}
		for r in pos:
			hit = values.get(r.purchase_order)
			if hit:
				r.po_value = hit.base_net_total
				r.supplier = r.supplier or hit.supplier
	if not doc.get("supplier") and pos:
		doc.supplier = pos[0].get("supplier")
	costs = doc.get("costs") or []
	for row in costs:
		fill_cost_defaults(row, settings)
	bills = sorted(
		{r.purchase_invoice for r in costs if r.get("purchase_invoice") and not r.get("actual_amount")}
	)
	if bills:
		heads = {
			b.name: b
			for b in frappe.get_all(
				"Purchase Invoice",
				filters={"name": ["in", bills], "docstatus": 1},
				fields=["name", "base_net_total"],
				limit_page_length=0,
			)
		}
		items = {}
		for r in frappe.get_all(
			"Purchase Invoice Item",
			filters={"parent": ["in", list(heads)]} if heads else {"name": ["in", []]},
			fields=["parent", "expense_account", "base_net_amount"],
			limit_page_length=0,
		):
			items.setdefault(r.parent, []).append(r)
		for name, head in heads.items():
			fill_actuals(costs, name, head.base_net_total, items.get(name, []))
	for key, value in shipment_totals(pos, costs).items():
		doc.set(key, value)
	if doc.status == "Delivered" and not doc.get("delivered_on"):
		doc.delivered_on = frappe.utils.nowdate()


def shipment_write_back(doc):
	"""Move linked POs forward (Shipped / Delivered) and carry the shipment ETA onto them."""
	try:
		before = doc.get_doc_before_save()
		status_changed = not before or before.status != doc.status
		eta_changed = not before or str(before.get("eta") or "") != str(doc.get("eta") or "")
		if not (status_changed or eta_changed) or doc.status == "Cancelled" or not _tracked("Purchase Order"):
			return
		names = [r.purchase_order for r in doc.get("purchase_orders") or [] if r.purchase_order]
		if not names:
			return
		target = shipment_vendor_status(doc.status)
		for po in frappe.get_all(
			"Purchase Order",
			filters={"name": ["in", names], "docstatus": ["<", 2]},
			fields=["name", "ill_vendor_status", "ill_eta", "per_received"],
			limit_page_length=0,
		):
			updates = {}
			nxt = forward_status(po.ill_vendor_status, target) if target else None
			if nxt:
				updates["ill_vendor_status"] = nxt
			if (
				doc.get("eta")
				and _num(po.per_received) < 100
				and str(po.ill_eta or "") != str(doc.eta)
				and (eta_changed or not po.ill_eta)
			):
				updates["ill_eta"] = doc.eta
			if updates:
				frappe.db.set_value("Purchase Order", po.name, updates, update_modified=False)
				text = ", ".join(f"{k.replace('ill_', '').replace('_', ' ')} {v}" for k, v in updates.items())
				comment("Purchase Order", po.name, f"{text} from inbound shipment {doc.name}")
	except Exception:
		_log("shipment_write_back")
