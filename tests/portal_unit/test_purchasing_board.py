"""Purchasing board (Command Center Purchasing): lanes, lead times, ETA, shortages, landed cost, writes."""

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".api.purchasing_board"
PURCHASING = ROOT + ".api.purchasing"
TODAY = date(2026, 11, 18)


def po(**kw):
	base = {"docstatus": 1, "status": "To Receive and Bill", "per_received": 0, "per_billed": 0}
	base.update(kw)
	return base


class Lanes(unittest.TestCase):
	def test_po_lane_every_status_combination(self):
		with load_service(MODULE) as (pb, _):
			cases = [
				(po(docstatus=0, status="Draft"), "draft"),
				(po(docstatus=2, status="Cancelled"), None),
				(po(status="On Hold", per_received=50), "on_hold"),
				(po(status="Completed", per_received=100, per_billed=100), "done"),
				(po(status="Closed"), "done"),
				(po(status="Delivered"), "done"),
				(po(status="To Bill", per_received=100, per_billed=40), "to_bill"),
				(po(per_received=100, per_billed=100), "done"),
				(po(per_received=30), "partly_received"),
				(po(ill_vendor_status="Shipped"), "in_transit"),
				(po(ill_vendor_status="Delivered"), "in_transit"),
				(po(ill_vendor_status="Confirmed"), "confirmed"),
				(po(ill_vendor_status="In production"), "confirmed"),
				(po(ill_vendor_status="Sent"), "awaiting_confirmation"),
				(po(ill_vendor_status="Not sent"), "not_sent"),
				(po(), "not_sent"),
			]
			for row, lane in cases:
				with self.subTest(row=row):
					self.assertEqual(pb.po_lane(row), lane)
			# received beats the vendor status
			self.assertEqual(pb.po_lane(po(per_received=50, ill_vendor_status="Sent")), "partly_received")

	def test_quote_lane_expiry_edges(self):
		with load_service(MODULE) as (pb, _):
			sq = {"doctype": "Supplier Quotation", "docstatus": 1, "status": "Submitted"}
			self.assertEqual(pb.quote_lane(dict(sq, valid_till="2026-11-17"), TODAY, 7), "expired")
			self.assertEqual(pb.quote_lane(dict(sq, valid_till="2026-11-18"), TODAY, 7), "expiring")
			self.assertEqual(pb.quote_lane(dict(sq, valid_till="2026-11-25"), TODAY, 7), "expiring")
			self.assertEqual(pb.quote_lane(dict(sq, valid_till="2026-11-26"), TODAY, 7), "quoted")
			self.assertEqual(pb.quote_lane(dict(sq), TODAY, 7), "quoted")
			self.assertEqual(pb.quote_lane(dict(sq, status="Expired"), TODAY, 7), "expired")
			self.assertEqual(pb.quote_lane(dict(sq, po="PO-1", valid_till="2026-01-01"), TODAY, 7), "ordered")
			self.assertEqual(pb.quote_lane(dict(sq, docstatus=2), TODAY, 7), "lost")
			rfq = {"doctype": "Request for Quotation", "docstatus": 1}
			self.assertEqual(pb.quote_lane(dict(rfq, docstatus=0), TODAY, 7), "rfq_draft")
			pending = [
				{"supplier": "A", "quote_status": "Pending"},
				{"supplier": "B", "quote_status": "Received"},
			]
			self.assertEqual(pb.quote_lane(dict(rfq, suppliers=pending), TODAY, 7), "awaiting_reply")
			self.assertEqual(pb.quote_lane(dict(rfq, suppliers=pending, sqs=["SQ-1"]), TODAY, 7), "quoted")
			self.assertEqual(
				pb.quote_lane(dict(rfq, suppliers=[{"quote_status": "Received"}]), TODAY, 7), "quoted"
			)

	def test_mr_shipment_and_bill_lanes(self):
		with load_service(MODULE) as (pb, _):
			self.assertEqual(pb.mr_lane({"docstatus": 0}), "draft")
			self.assertEqual(pb.mr_lane({"docstatus": 1, "status": "Pending"}), "to_quote")
			self.assertEqual(pb.mr_lane({"docstatus": 1, "status": "Pending", "rfqs": ["R"]}), "quoted")
			self.assertEqual(pb.mr_lane({"docstatus": 1, "status": "Partially Ordered"}), "ordered")
			self.assertEqual(pb.mr_lane({"docstatus": 1, "status": "Partially Received"}), "receiving")
			self.assertEqual(pb.mr_lane({"docstatus": 1, "status": "Received"}), "done")
			self.assertEqual(pb.shipment_lane("In transit"), "moving")
			self.assertEqual(pb.shipment_lane("Cleared"), "customs")
			self.assertEqual(pb.shipment_lane("Costs final"), "final")
			self.assertIsNone(pb.shipment_lane("Cancelled"))
			bill = {"docstatus": 1, "status": "Unpaid", "outstanding_amount": 100, "due_date": "2026-11-30"}
			self.assertEqual(pb.bill_lane(bill, TODAY), "unpaid")
			self.assertEqual(pb.bill_lane(dict(bill, due_date="2026-11-01"), TODAY), "overdue")
			self.assertEqual(pb.bill_lane(dict(bill, status="Partly Paid"), TODAY), "partly_paid")
			self.assertEqual(pb.bill_lane(dict(bill, outstanding_amount=0), TODAY), "paid")
			self.assertEqual(pb.bill_lane(dict(bill, docstatus=0), TODAY), "draft")


class LeadTimeAndEta(unittest.TestCase):
	def leads(self, purchasing, **attrs):
		lt = object.__new__(purchasing.LeadTimes)
		lt.today = TODAY
		lt.settings = {"group_leads": {"Extrusions": 10}}
		lt.items = {"EXT": Record(item_group="Channels", lead_time_days=attrs.get("item"))}
		lt.item_supplier = {"EXT": "Acme"}
		lt.suppliers = {"Acme": attrs.get("supplier")}
		lt.quotes = {("EXT", "Acme"): attrs["quote"]} if attrs.get("quote") else {}
		lt.by_sq = {}
		lt.groups = {"Channels": "Extrusions", "Extrusions": "All Item Groups"}
		return lt

	def test_each_source_wins_over_the_ones_below_it(self):
		with load_service(PURCHASING) as (purchasing, _):
			row, head = Record(ill_est_lead_time_days=4), Record(ill_est_lead_time_days=6)
			full = self.leads(purchasing, quote=20, supplier=30, item=40)
			self.assertEqual(full.get("EXT", "Acme", po_row=row, po=head), (4, "po line"))
			self.assertEqual(full.get("EXT", "Acme", po_row=Record(), po=head), (6, "po"))
			self.assertEqual(full.get("EXT", "Acme"), (20, "quote"))
			self.assertEqual(self.leads(purchasing, supplier=30, item=40).get("EXT"), (30, "supplier"))
			self.assertEqual(self.leads(purchasing, item=40).get("EXT"), (40, "item"))
			# no own row: the parent group's default applies
			self.assertEqual(self.leads(purchasing).get("EXT"), (10, "group default"))
			lt = self.leads(purchasing)
			lt.settings = {"group_leads": {}}
			self.assertEqual(lt.get("EXT"), (None, "none"))

	def test_zero_and_blank_are_skipped(self):
		with load_service(PURCHASING) as (purchasing, _):
			self.assertEqual(
				purchasing.resolve_lead([(0, "po line"), ("", "po"), ("12", "quote")]), (12, "quote")
			)
			self.assertEqual(purchasing.group_lead("A", {"A": "B", "B": "A"}, {}), None)  # loop-safe

	def test_eta_precedence_and_blank_required_by(self):
		with load_service(MODULE) as (pb, _):
			head = {"transaction_date": "2026-11-01", "schedule_date": "2026-11-20", "ill_eta": "2026-11-25"}
			self.assertEqual(pb.eta({"ill_eta": "2026-12-01"}, head, 10), (date(2026, 12, 1), "line"))
			self.assertEqual(pb.eta({}, head, 10), (date(2026, 11, 25), "po"))
			self.assertEqual(pb.eta({}, dict(head, ill_eta=None), 10), (date(2026, 11, 20), "required by"))
			no_date = {"transaction_date": "2026-11-01", "schedule_date": None}
			self.assertEqual(pb.eta({}, no_date, 10), (date(2026, 11, 11), "lead time"))
			self.assertEqual(pb.eta({}, no_date, None), (None, "none"))

	def test_late_flags(self):
		with load_service(MODULE) as (pb, _):
			self.assertEqual(
				pb.late_flags("2026-11-10", "2026-11-30", TODAY), {"overdue": True, "will_miss": False}
			)
			self.assertEqual(
				pb.late_flags("2026-12-05", "2026-11-30", TODAY), {"overdue": False, "will_miss": True}
			)
			self.assertEqual(
				pb.late_flags("2026-11-10", None, TODAY, received=True),
				{"overdue": False, "will_miss": False},
			)


class Shortages(unittest.TestCase):
	def test_hand_worked_example_with_draft_orders(self):
		with load_service(MODULE) as (pb, _):
			demand = [
				{"item": "EXT", "qty": 10, "need_by": "2026-12-10", "src": "Sales Order", "doc": "SO-1"},
				{"item": "EXT", "qty": 6, "need_by": "2026-11-30", "src": "Work Order", "doc": "WO-1"},
				{
					"item": "EXT",
					"qty": 5,
					"need_by": "2026-11-25",
					"src": "Sales Order",
					"doc": "SO-D",
					"draft": True,
				},
				{
					"item": "TAPE",
					"qty": 4,
					"need_by": "2026-12-01",
					"src": "Sales Order",
					"doc": "SO-D",
					"draft": True,
				},
				{"item": "PSU", "qty": 2, "need_by": "2026-12-01", "src": "Sales Order", "doc": "SO-1"},
			]
			stock = {"EXT": 3, "TAPE": 1, "PSU": 5}
			incoming = {"EXT": [(date(2026, 12, 1), 4)]}
			info = {
				"EXT": {"lead": 10, "lead_src": "group default", "supplier": "Acme", "group": "Extrusions"},
				"TAPE": {"lead": 35, "lead_src": "item", "supplier": None, "group": "Tape"},
			}
			rows = pb.shortages(demand, stock, incoming, info.get, TODAY, 3, {"EXT": {"mr": "MR-1"}})
			self.assertEqual([r["item"] for r in rows], ["EXT", "TAPE"])  # PSU is covered
			ext, tape = rows
			# firm 16 - 3 on hand - 4 on order = 9; with the draft order 21 - 7 = 14
			self.assertEqual((ext["short_firm"], ext["short_all"]), (9, 14))
			self.assertEqual(ext["need_by"], "2026-11-30")  # earliest firm need
			self.assertEqual(ext["order_by"], "2026-11-17")  # 30 Nov - 10 lead - 3 safety
			self.assertTrue(ext["late"])
			self.assertEqual(ext["mr"], "MR-1")
			self.assertEqual(ext["on_order"], 4)
			self.assertEqual([d["doc"] for d in ext["docs"]], ["SO-1", "WO-1", "SO-D"])
			self.assertTrue(ext["docs"][2]["draft"])
			# only short if the draft order goes ahead
			self.assertEqual((tape["short_firm"], tape["short_all"]), (0, 3))
			self.assertFalse(tape["late"])
			for key in (
				"item",
				"group",
				"lead",
				"lead_src",
				"on_hand",
				"on_order",
				"supplier",
				"need_by",
				"order_by",
				"late",
				"short_firm",
				"short_all",
				"draft_po",
				"mr",
				"manufactured",
				"docs",
			):
				self.assertIn(key, ext)

	def test_reorder_breaches_and_suggested_level(self):
		with load_service(MODULE) as (pb, _):
			bins = [
				{"item_code": "EXT", "warehouse": "Stores - ilL", "projected_qty": 4},
				{"item_code": "TAPE", "warehouse": "Stores - ilL", "projected_qty": 50},
			]
			rules = [
				{
					"parent": "EXT",
					"warehouse": "Stores - ilL",
					"warehouse_reorder_level": 20,
					"warehouse_reorder_qty": 10,
				},
				{
					"parent": "TAPE",
					"warehouse": "Stores - ilL",
					"warehouse_reorder_level": 20,
					"warehouse_reorder_qty": 10,
				},
				{
					"parent": "PSU",
					"warehouse": "Stores - ilL",
					"warehouse_reorder_level": 5,
					"warehouse_reorder_qty": 10,
				},
			]
			rows = pb.reorder_breaches(bins, rules)
			self.assertEqual([(r["item"], r["suggest_qty"]) for r in rows], [("EXT", 16), ("PSU", 10)])
			self.assertEqual(pb.suggest_reorder_level(2.5, 10, 3), 33)
			self.assertEqual(pb.suggest_reorder_level(2, 10, 0), 20)
			self.assertIsNone(pb.suggest_reorder_level(0, 10, 3))


class LandedCost(unittest.TestCase):
	def test_allocate_like_the_landed_cost_voucher(self):
		with load_service(MODULE) as (pb, _):
			items = [{"qty": 1, "amount": 100}, {"qty": 1, "amount": 100}, {"qty": 1, "amount": 100}]
			self.assertEqual(
				pb.allocate_costs(100, items, "value"), [33.33, 33.33, 33.34]
			)  # last takes the remainder
			items = [{"qty": 10, "amount": 50}, {"qty": 30, "amount": 50}, {"qty": 60, "amount": 900}]
			self.assertEqual(pb.allocate_costs(250, items, "By qty"), [25.0, 75.0, 150.0])
			self.assertEqual(pb.allocate_costs(250, items, "By value"), [12.5, 12.5, 225.0])
			self.assertEqual(sum(pb.allocate_costs(99.99, items, "value")), 99.99)
			self.assertEqual(pb.landed_unit_cost(10, 100, 150), 11.5)
			self.assertEqual(pb.uplift_pct(10, 11.5), 15.0)

	def test_three_way_match(self):
		with load_service(MODULE) as (pb, _):
			po_rows = [{"item": "EXT", "qty": 100, "rate": 10}]
			ok = pb.three_way(
				po_rows,
				[{"item": "EXT", "qty": 100, "rate": 10}],
				[{"item": "EXT", "qty": 100, "rate": 10.1}],
			)
			self.assertEqual(ok["match"], "matches")  # 1% and $10
			price = pb.three_way(
				po_rows,
				[{"item": "EXT", "qty": 100, "rate": 10}],
				[{"item": "EXT", "qty": 100, "rate": 10.6}],
			)
			self.assertEqual((price["match"], price["price"]), ("price_off", 60.0))
			qty = pb.three_way(
				po_rows, [{"item": "EXT", "qty": 90, "rate": 10}], [{"item": "EXT", "qty": 100, "rate": 10}]
			)
			self.assertEqual((qty["match"], qty["qty"]), ("qty_off", 10))

	def test_scrub_blanks_every_money_key(self):
		with load_service(MODULE) as (pb, _):
			board = {
				"summary": {
					"pos": {"count": 3, "amount": 10},
					"landed": {"est_open_amount": 5, "needs_lcv": 1},
				},
				"pos": [{"name": "PO-1", "amount": 5, "lines": [{"qty": 2}]}],
				"shipments": [
					{
						"goods_value": 1,
						"est_cost": 2,
						"actual_cost": 3,
						"variance": 4,
						"landed_pct": 5,
						"costs": [{"est": 1, "actual": 2}],
					}
				],
				"bills": [{"outstanding": 9, "variance": {"qty": 1, "price": 30}}],
				"quote_compare": [{"rows": [{"rate": 4, "lead_days": 3}]}],
				"landed": {"by_item": [{"purchase_rate": 1, "landed_rate": 2}], "in_stock_amount": 7},
				"suppliers": [{"open_amount": 4, "open_pos": 2}],
				"receipts": [{"lcv_amount": 3}],
			}
			out = pb.scrub(board)
			self.assertEqual(out["summary"]["pos"], {"count": 3, "amount": None})
			self.assertEqual(out["summary"]["landed"]["needs_lcv"], 1)
			self.assertIsNone(out["summary"]["landed"]["est_open_amount"])
			self.assertEqual(out["pos"][0]["lines"][0]["qty"], 2)
			ship = out["shipments"][0]
			self.assertTrue(
				all(
					ship[k] is None
					for k in ("goods_value", "est_cost", "actual_cost", "variance", "landed_pct")
				)
			)
			self.assertEqual(ship["costs"][0], {"est": None, "actual": None})
			self.assertEqual(out["bills"][0]["variance"], {"qty": None, "price": None})
			self.assertIsNone(out["quote_compare"][0]["rows"][0]["rate"])
			self.assertEqual(out["quote_compare"][0]["rows"][0]["lead_days"], 3)
			self.assertIsNone(out["landed"]["in_stock_amount"])
			self.assertEqual(out["suppliers"][0], {"open_amount": None, "open_pos": 2})
			self.assertIsNone(out["receipts"][0]["lcv_amount"])


def raw_board():
	"""One record per interesting lane."""
	return {
		"mrs": [
			{
				"name": "MR-1",
				"status": "Pending",
				"docstatus": 1,
				"transaction_date": "2026-11-10",
				"schedule_date": "2026-11-20",
				"items": [{"item_code": "EXT", "qty": 10, "ordered_qty": 0}],
			},
			{
				"name": "MR-2",
				"status": "Pending",
				"docstatus": 1,
				"transaction_date": "2026-11-17",
				"items": [{"item_code": "TAPE", "qty": 5}],
			},
		],
		"rfqs": [
			{
				"name": "RFQ-1",
				"docstatus": 1,
				"status": "Submitted",
				"transaction_date": "2026-11-01",
				"suppliers": [{"supplier": "Acme", "quote_status": "Pending", "email_sent": 1}],
				"items": [{"item_code": "TAPE", "material_request": "MR-2"}],
			},
		],
		"sqs": [
			{
				"name": "SQ-1",
				"supplier": "Acme",
				"docstatus": 1,
				"status": "Submitted",
				"valid_till": "2026-11-20",
				"grand_total": 500,
				"items": [{"item_code": "EXT", "rate": 5, "lead_time_days": 21}],
			},
			{
				"name": "SQ-2",
				"supplier": "Beta",
				"docstatus": 1,
				"status": "Submitted",
				"valid_till": "2026-12-30",
				"grand_total": 400,
				"items": [{"item_code": "EXT", "rate": 4, "lead_time_days": 30}],
			},
		],
		"pos": [
			{
				"name": "PO-NS",
				"supplier": "Acme",
				"docstatus": 1,
				"status": "To Receive and Bill",
				"transaction_date": "2026-11-01",
				"ill_vendor_status": "Not sent",
				"ill_eta": "2026-11-15",
				"base_net_total": 1000,
				"per_received": 0,
				"per_billed": 0,
				"items": [{"name": "L1", "item_code": "EXT", "qty": 100, "rate": 10, "sales_order": "SO-1"}],
			},
			{
				"name": "PO-TR",
				"supplier": "Paint Co",
				"docstatus": 1,
				"status": "To Receive and Bill",
				"transaction_date": "2026-11-05",
				"ill_vendor_status": "Shipped",
				"ill_eta": "2026-12-10",
				"base_net_total": 2000,
				"per_received": 0,
				"items": [{"name": "L2", "item_code": "TAPE", "qty": 10, "rate": 200, "sales_order": "SO-1"}],
			},
			{
				"name": "PO-DR",
				"supplier": "Acme",
				"docstatus": 0,
				"status": "Draft",
				"creation": "2026-11-01",
				"transaction_date": "2026-11-01",
				"items": [{"name": "L3", "item_code": "PSU", "qty": 1, "supplier_quotation": "SQ-9"}],
			},
			{
				"name": "PO-TB",
				"supplier": "Acme",
				"docstatus": 1,
				"status": "To Bill",
				"transaction_date": "2026-10-01",
				"ill_eta": "2026-10-20",
				"base_net_total": 1000,
				"per_received": 100,
				"per_billed": 0,
				"items": [{"name": "L4", "item_code": "EXT", "qty": 100, "rate": 10}],
			},
		],
		"receipts": [
			{
				"name": "PR-1",
				"supplier": "Acme",
				"docstatus": 1,
				"status": "To Bill",
				"posting_date": "2026-10-25",
				"base_net_total": 1000,
				"per_billed": 0,
				"items": [{"item_code": "EXT", "qty": 100, "rate": 10, "purchase_order": "PO-TB"}],
			},
		],
		"invoices": [
			{
				"name": "PI-1",
				"supplier": "Acme",
				"docstatus": 1,
				"status": "Overdue",
				"posting_date": "2026-10-30",
				"due_date": "2026-11-10",
				"grand_total": 1060,
				"outstanding_amount": 1060,
				"items": [
					{
						"item_code": "EXT",
						"qty": 100,
						"rate": 10.6,
						"purchase_order": "PO-TB",
						"purchase_receipt": "PR-1",
					}
				],
			},
			{
				"name": "PI-F",
				"supplier": "Forwarder",
				"docstatus": 1,
				"status": "Unpaid",
				"posting_date": "2026-11-01",
				"due_date": "2026-12-01",
				"grand_total": 120,
				"outstanding_amount": 120,
				"items": [{"item_code": "FREIGHT-IN", "qty": 1, "rate": 120}],
			},
		],
		"lcvs": [],
		"shipments": [
			{
				"name": "SHP-1",
				"status": "Delivered",
				"supplier": "Acme",
				"delivered_on": "2026-10-10",
				"eta": "2026-10-09",
				"purchase_orders": [{"purchase_order": "PO-TB", "po_value": 1000}],
				"receipts": [{"purchase_receipt": "PR-1"}],
				"costs": [
					{
						"name": "c1",
						"cost_type": "Freight",
						"estimated_amount": 80,
						"actual_amount": 120,
						"purchase_invoice": "PI-F",
						"include_in_landed_cost": 1,
						"expense_account": "Freight In - ilL",
						"allocation": "By qty",
					},
					{
						"name": "c2",
						"cost_type": "Duty",
						"estimated_amount": 30,
						"include_in_landed_cost": 1,
						"expense_account": "Duties - ilL",
						"allocation": "By value",
					},
				],
				"landed_cost_vouchers": [],
			},
			{
				"name": "SHP-2",
				"status": "In transit",
				"supplier": "Paint Co",
				"eta": "2026-11-12",
				"purchase_orders": [{"purchase_order": "PO-TR", "po_value": 2000}],
				"receipts": [],
				"costs": [],
			},
		],
		"items": {
			"EXT": {
				"item_name": "Extrusion",
				"item_group": "Extrusions",
				"default_supplier": "Acme",
				"is_stock_item": 1,
				"customs_tariff_number": "7604",
				"country_of_origin": "China",
			},
			"TAPE": {"item_name": "Tape", "item_group": "Tape", "is_stock_item": 1},
			"PSU": {"item_name": "Power", "default_bom": None, "is_stock_item": 1},
			"FIX": {"item_name": "Fixture", "default_bom": "BOM-FIX"},
		},
		"bins": [{"item_code": "EXT", "warehouse": "Stores - ilL", "projected_qty": 2}],
		"reorder_rows": [
			{
				"parent": "EXT",
				"warehouse": "Stores - ilL",
				"warehouse_reorder_level": 10,
				"warehouse_reorder_qty": 20,
			}
		],
		"demand": [{"item": "TAPE", "qty": 20, "need_by": "2026-12-01", "src": "Sales Order", "doc": "SO-1"}],
		"stock": {"EXT": 2, "TAPE": 1},
		"incoming": {"TAPE": [(date(2026, 12, 10), 10)]},
		"usage": {"EXT": 1.0},
		"so_dates": {"SO-1": "2026-12-01"},
		"paint_suppliers": {"Paint Co"},
		"qbo_since": "2026-10-01",
		"landed_history": [
			{
				"parent": "PR-0",
				"item_code": "EXT",
				"qty": 100,
				"rate": 10,
				"landed_cost_voucher_amount": 150,
				"posting_date": "2026-09-01",
			}
		],
		"open_docs": {"PSU": {"draft_po": "PO-DR"}},
	}


SETTINGS = {
	"quote_expiry_warn_days": 7,
	"vendor_confirm_warn_days": 3,
	"receipt_bill_warn_days": 14,
	"lcv_warn_days": 30,
	"safety_days": 3,
	"default_warehouse": "Stores - ilL",
	"company": "ilLumenate Lighting",
}


def lead_fn(item, supplier=None, po_row=None, po=None):
	return {"EXT": (10, "group default"), "TAPE": (35, "item")}.get(item, (None, "none"))


class Board(unittest.TestCase):
	def test_assemble_lanes_decisions_and_summary(self):
		with load_service(MODULE) as (pb, _):
			board = pb.assemble(raw_board(), SETTINGS, TODAY, lead_fn, money=True, can_edit=True)
			for key in (
				"today",
				"money",
				"can_edit",
				"settings",
				"summary",
				"decisions",
				"shortages",
				"reorder",
				"mrs",
				"quotes",
				"quote_compare",
				"pos",
				"shipments",
				"receipts",
				"bills",
				"landed",
				"gaps",
				"suppliers",
			):
				self.assertIn(key, board)
			pos = {p["name"]: p for p in board["pos"]}
			self.assertEqual(pos["PO-NS"]["lane"], "not_sent")
			self.assertTrue(pos["PO-NS"]["overdue"])
			self.assertEqual(pos["PO-TR"]["lane"], "in_transit")
			self.assertTrue(pos["PO-TR"]["will_miss"])
			self.assertEqual(pos["PO-TR"]["will_miss_so"], "SO-1")
			self.assertTrue(pos["PO-TR"]["paint"])
			self.assertEqual(pos["PO-TR"]["shipments"], ["SHP-2"])
			self.assertEqual(pos["PO-DR"]["lane"], "draft")
			self.assertEqual(pos["PO-TB"]["lane"], "to_bill")
			self.assertEqual(pos["PO-NS"]["lead_days"], 10)
			mrs = {m["name"]: m for m in board["mrs"]}
			self.assertEqual(mrs["MR-1"]["lane"], "to_quote")
			self.assertEqual(mrs["MR-2"]["lane"], "quoted")
			quotes = {q["name"]: q for q in board["quotes"]}
			self.assertEqual(quotes["SQ-1"]["lane"], "expiring")
			self.assertEqual(quotes["RFQ-1"]["lane"], "awaiting_reply")
			self.assertEqual(board["quote_compare"][0]["item"], "EXT")
			cheapest = [r for r in board["quote_compare"][0]["rows"] if r["cheapest"]]
			self.assertEqual(cheapest[0]["sq"], "SQ-2")
			ship = {s["name"]: s for s in board["shipments"]}
			self.assertTrue(ship["SHP-1"]["needs_lcv"])
			self.assertEqual(ship["SHP-1"]["variance"], 40)
			bills = {b["name"]: b for b in board["bills"]}
			self.assertEqual(bills["PI-1"]["match"], "price_off")
			self.assertEqual(bills["PI-1"]["lane"], "overdue")
			self.assertTrue(bills["PI-1"]["not_in_qbo"])
			self.assertEqual(bills["PI-F"]["kind"], "freight/duty")
			self.assertEqual(board["receipts"][0]["lcv_status"], "needs_lcv")
			self.assertEqual(board["landed"]["pending"][0]["missing_bills"], ["Duty"])
			self.assertFalse(board["landed"]["pending"][0]["ready"])
			self.assertEqual(board["landed"]["by_item"][0]["uplift_pct"], 15.0)
			self.assertEqual(board["reorder"][0]["suggest_qty"], 20)
			self.assertEqual(board["reorder"][0]["suggested_level"], 13)
			self.assertEqual(board["shortages"][0]["item"], "TAPE")
			gaps = board["gaps"]
			self.assertIn("TAPE", [g["item"] for g in gaps["no_supplier"]])
			self.assertIn("PSU", [g["item"] for g in gaps["no_lead"]])
			self.assertNotIn("FIX", [g["item"] for gap in gaps.values() for g in gap])  # manufactured
			self.assertIn("TAPE", [g["item"] for g in gaps["no_hts"]])
			ids = {d["id"]: d for d in board["decisions"]}
			for key in (
				"po_not_sent",
				"po_overdue",
				"po_will_miss",
				"po_draft_old",
				"quote_expiring",
				"rfq_no_reply",
				"mr_unactioned",
				"reorder_breach",
				"receipt_no_bill",
				"bill_overdue",
				"bill_not_in_qbo",
				"needs_lcv",
				"cost_variance",
				"shipment_eta_passed",
			):
				self.assertIn(key, ids)
			self.assertEqual(ids["po_not_sent"]["tab"], "pos")
			self.assertEqual(ids["po_not_sent"]["lane"], "not_sent")
			self.assertEqual(ids["needs_lcv"]["tone"], "bad")  # delivered over 30 days ago
			self.assertTrue(all(d["count"] > 0 for d in board["decisions"]))
			self.assertEqual(board["summary"]["pos"]["not_sent"], 1)
			self.assertEqual(board["summary"]["landed"]["needs_lcv"], 1)

	def test_money_hidden_and_view_role_required(self):
		with load_service(MODULE) as (pb, frappe):
			board = pb.assemble(raw_board(), SETTINGS, TODAY, lead_fn, money=False)
			self.assertIsNone(board["pos"][0]["amount"])
			self.assertIsNone(board["summary"]["bills"]["unpaid_amount"])
			self.assertEqual(board["summary"]["bills"]["overdue"], 1)
			frappe.get_roles.return_value = ["Dealer"]
			with self.assertRaises(PermissionError):
				pb.get_board()
			frappe.get_roles.return_value = ["Command Center Viewer"]
			with patch.object(pb, "build_board", return_value={}) as build:
				pb.get_board()
				build.assert_called_once_with(money=False, can_edit=False)
			frappe.get_roles.return_value = ["Purchase Manager"]
			with patch.object(pb, "build_board", return_value={}) as build:
				pb.get_board()
				build.assert_called_once_with(money=True, can_edit=True)


class Writes(unittest.TestCase):
	def test_writes_refuse_without_edit_role(self):
		with load_service(MODULE) as (pb, frappe):
			frappe.get_roles.return_value = ["Command Center Viewer"]
			calls = [
				lambda: pb.update_po_tracking("PO-1", {"ill_eta": "2026-12-01"}),
				lambda: pb.update_po_line_tracking("PO-1", []),
				lambda: pb.set_item_lead_time("EXT", 10),
				lambda: pb.draft_material_request([{"item": "EXT", "qty": 1}]),
				lambda: pb.make_rfq("MR-1", ["Acme"]),
				lambda: pb.make_supplier_quotation(material_request="MR-1", supplier="Acme"),
				lambda: pb.make_po(supplier_quotation="SQ-1"),
				lambda: pb.make_receipt("PO-1"),
				lambda: pb.make_invoice(po="PO-1"),
				lambda: pb.create_shipment(["PO-1"], {}),
				lambda: pb.update_shipment("SHP-1", {}),
				lambda: pb.make_landed_cost_voucher("SHP-1"),
				lambda: pb.apply_reorder_level("EXT", "Stores - ilL", 10, 20),
				lambda: pb.set_supplier_lead_time("Acme", 10),
			]
			for call in calls:
				with self.assertRaises(PermissionError):
					call()
			frappe.get_doc.assert_not_called()

	def test_po_tracking_allowlist_and_never_submits(self):
		with load_service(MODULE) as (pb, frappe):
			frappe.get_roles.return_value = ["Command Center Editor"]
			doc = MagicMock(docstatus=1)
			doc.name = "PO-1"
			doc.get.side_effect = lambda key: {"ill_eta": None}.get(key)
			frappe.get_doc.return_value = doc
			with self.assertRaisesRegex(ValueError, "grand_total"):
				pb.update_po_tracking("PO-1", '{"grand_total": 1}')
			with patch.object(pb, "purchasing") as purchasing:
				result = pb.update_po_tracking(
					"PO-1", {"ill_eta": "2026-12-01", "ill_vendor_status": "Confirmed"}
				)
				self.assertEqual(result["changed"], 2)
				doc.check_permission.assert_called_with("write")
				doc.save.assert_called_once()
				doc.submit.assert_not_called()
				self.assertIn("tracking edited", purchasing.comment.call_args.args[2])
			with self.assertRaisesRegex(ValueError, "rate"):
				pb.update_po_line_tracking("PO-1", [{"name": "x", "rate": 1}])

	def test_conversions_create_drafts_only(self):
		with load_service(MODULE) as (pb, frappe):
			frappe.get_roles.return_value = ["Purchase User"]
			made = MagicMock(doctype="Material Request")
			made.name = "MR-NEW"
			frappe.get_doc.return_value = made
			with patch.object(pb, "purchasing") as purchasing:
				purchasing.read_settings.return_value = {"company": "C", "default_warehouse": "W"}
				result = pb.draft_material_request(
					[{"item": "EXT", "qty": 2.2, "schedule_date": "2026-12-01"}]
				)
			made.insert.assert_called_once()
			made.submit.assert_not_called()
			self.assertEqual(result["name"], "MR-NEW")
			doc = frappe.get_doc.call_args.args[0]
			self.assertEqual(doc["items"][0]["qty"], 3)
			self.assertNotIn("sales_order", doc["items"][0])
			self.assertEqual(doc["set_warehouse"], "W")
			with self.assertRaises(ValueError):
				pb.draft_material_request([])

	def test_receipt_and_invoice_need_a_submitted_po(self):
		with load_service(MODULE) as (pb, frappe):
			frappe.get_roles.return_value = ["Purchase User"]
			frappe.get_doc.return_value = MagicMock(docstatus=0)
			with self.assertRaisesRegex(ValueError, "Submit purchase order"):
				pb.make_receipt("PO-1")
			with self.assertRaisesRegex(ValueError, "Submit purchase order"):
				pb.make_invoice(po="PO-1")
			with self.assertRaisesRegex(ValueError, "Submit purchase receipt"):
				pb.make_invoice(purchase_receipt="PR-1")
			with self.assertRaisesRegex(ValueError, "Submit"):
				pb.make_po(supplier_quotation="SQ-1")


class Row(dict):
	"""A child row / document stand-in: attribute access and ``set`` like Frappe's."""

	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value

	def set(self, key, value):
		self[key] = value


class Bill(Row):
	"""A mapped draft Purchase Invoice, as ERPNext's make_purchase_invoice returns it."""

	def __init__(self, schedule, **fields):
		super().__init__(doctype="Purchase Invoice", name="ACC-PINV-NEW", payment_schedule=schedule, **fields)
		self.inserted = False
		self.submitted = False

	def remove(self, row):
		self["payment_schedule"].remove(row)
		for idx, other in enumerate(self["payment_schedule"], 1):
			other.idx = idx

	def insert(self):
		# ERPNext's validate_due_date (accounts_controller + party.validate_due_date):
		# set_due_date takes the latest row, then it may not be before bill_date or posting_date.
		dates = [r.due_date for r in self.payment_schedule if r.due_date]
		if len(set(map(str, dates))) != len(dates):
			raise ValueError("Rows with duplicate due dates in other rows were found")
		if dates:
			self.due_date = max(dates, key=str)
		if str(self.due_date) < str(self.bill_date or self.posting_date):
			raise ValueError("Due Date cannot be before Supplier Invoice Date")
		self.inserted = True

	def submit(self):
		self.submitted = True


def po_terms(due="2026-10-08", portion=100, amount=500.0):
	"""A schedule row copied from a PO with no payment terms template (due = the PO date)."""
	return Row(
		idx=1,
		due_date=due,
		invoice_portion=portion,
		payment_amount=amount,
		base_payment_amount=amount,
		outstanding=amount,
		base_outstanding=amount,
	)


class InvoiceDueDates(unittest.TestCase):
	"""Draft bills from old receipts / orders: ERPNext copies the PO's lapsed due date."""

	def draft(self, bill, **kw):
		mapper = MagicMock(return_value=bill)
		extras = {
			"erpnext.stock.doctype.purchase_receipt.purchase_receipt": MagicMock(
				make_purchase_invoice=mapper
			),
			"erpnext.buying.doctype.purchase_order.purchase_order": MagicMock(make_purchase_invoice=mapper),
		}
		with load_service(MODULE, extras) as (pb, frappe):
			frappe.get_roles.return_value = ["Purchase User"]
			frappe.get_doc.return_value = MagicMock(docstatus=1)
			with patch.object(pb, "purchasing") as purchasing:
				result = pb.make_invoice(**kw)
		return result, mapper, purchasing.comment.call_args.args[2]

	def test_receipt_bill_with_lapsed_po_terms_validates_as_a_draft(self):
		# MAT-PRE-2026-00049: received 2026-10-28 against a PO from 2026-10-08, billed today.
		bill = Bill(
			[po_terms("2026-10-08")], posting_date="2026-11-23", bill_date=None, due_date="2026-10-08"
		)
		with self.assertRaisesRegex(ValueError, "Supplier Invoice Date"):
			Bill([po_terms()], posting_date="2026-11-23", bill_date=None).insert()  # the bug, unfixed
		result, mapper, comment = self.draft(bill, purchase_receipt="MAT-PRE-2026-00049")
		mapper.assert_called_once_with("MAT-PRE-2026-00049")
		self.assertEqual(result, {"name": "ACC-PINV-NEW", "doctype": "Purchase Invoice"})
		self.assertTrue(bill.inserted)
		self.assertFalse(bill.submitted)
		self.assertEqual(str(bill.payment_schedule[0].due_date), "2026-11-23")
		self.assertEqual(str(bill.due_date), "2026-11-23")
		self.assertEqual(bill.payment_schedule[0].payment_amount, 500.0)
		self.assertIsNone(bill.bill_date)  # the accountant still sets the supplier invoice date
		self.assertIn("now due 2026-11-23", comment)

	def test_po_bill_has_the_same_fix(self):
		bill = Bill([po_terms("2026-09-30")], posting_date="2026-11-23", bill_date=None)
		_, mapper, comment = self.draft(bill, po="PUR-ORD-2026-00031")
		mapper.assert_called_once_with("PUR-ORD-2026-00031")
		self.assertTrue(bill.inserted)
		self.assertFalse(bill.submitted)
		self.assertEqual(str(bill.due_date), "2026-11-23")
		self.assertIn("from PUR-ORD-2026-00031", comment)

	def test_current_terms_are_left_alone(self):
		# Net 30 recalculated by ERPNext from today's posting date: nothing to move.
		bill = Bill([po_terms("2026-12-23")], posting_date="2026-11-23", due_date="2026-12-23")
		_, _, comment = self.draft(bill, purchase_receipt="MAT-PRE-2026-00048")
		self.assertTrue(bill.inserted)
		self.assertEqual(bill.payment_schedule[0].due_date, "2026-12-23")
		self.assertEqual(bill.due_date, "2026-12-23")
		self.assertNotIn("due", comment)
		with load_service(MODULE) as (pb, _):
			self.assertIsNone(pb.refresh_due_dates(Bill([], posting_date="2026-11-23")))
			self.assertIsNone(pb.refresh_due_dates(Bill([po_terms()], posting_date=None)))

	def test_lapsed_rows_merge_and_bill_date_is_the_base(self):
		with load_service(MODULE) as (pb, _):
			deposit = po_terms("2026-09-01", portion=30, amount=150.0)
			on_ship = po_terms("2026-10-01", portion=40, amount=200.0)
			on_ship.idx = 2
			net = po_terms("2026-12-01", portion=30, amount=150.0)
			net.idx = 3
			bill = Bill([deposit, on_ship, net], posting_date="2026-11-23", bill_date="2026-11-01")
			moved = pb.refresh_due_dates(bill)
			self.assertEqual(moved.isoformat(), "2026-11-01")
			self.assertEqual(len(bill.payment_schedule), 2)
			first, last = bill.payment_schedule
			self.assertEqual((first.idx, str(first.due_date)), (1, "2026-11-01"))
			self.assertEqual(first.invoice_portion, 70)
			self.assertEqual((first.payment_amount, first.outstanding, first.base_outstanding), (350.0,) * 3)
			self.assertEqual((last.idx, last.due_date, last.invoice_portion), (2, "2026-12-01", 30))
			self.assertEqual(str(bill.due_date), "2026-12-01")
			bill.insert()  # validates
			self.assertTrue(bill.inserted)


if __name__ == "__main__":
	unittest.main()
