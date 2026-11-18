"""Production Board (Command Center Manufacturing): status, parts, capacity, shipping."""

import unittest
from datetime import date, datetime, time
from unittest.mock import patch

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".api.production_board"


class Status(unittest.TestCase):
	def test_status_rules(self):
		with load_service(MODULE) as (pb, _):
			order = Record(status="To Deliver and Bill", ill_build_points=10)

			def wo(status, made=0):
				return Record(status=status, qty=1, produced_qty=made, material_transferred_for_manufacturing=0)

			self.assertEqual(pb.order_status(order, [], False), pb.PEND_PROD)
			self.assertEqual(pb.order_status(Record(status="To Deliver", ill_build_points=0), [], False), pb.PEND_SHIP)
			self.assertEqual(pb.order_status(order, [wo("Not Started")], False), pb.PEND_PROD)
			self.assertEqual(pb.order_status(order, [wo("Not Started")], True), pb.WFP)
			self.assertEqual(pb.order_status(order, [wo("Not Started"), wo("In Process")], True), pb.IN_PROD)
			self.assertEqual(pb.order_status(order, [wo("Completed", made=1), wo("Completed", made=1)], False), pb.PEND_SHIP)
			self.assertEqual(pb.order_status(order, [wo("Stopped")], False), pb.HELD)
			self.assertEqual(pb.order_status(Record(status="On Hold"), [wo("In Process")], False), pb.HELD)
			self.assertEqual(
				pb.order_status(Record(status="To Deliver", ill_production_status_override="Paint"), [], False), pb.PAINT
			)


class Parts(unittest.TestCase):
	def test_stock_goes_to_earliest_ship_date_and_pos_set_eta(self):
		with load_service(MODULE) as (pb, _):
			needs = {"SO-A": {"EXT": 10}, "SO-B": {"EXT": 10}, "SO-C": {"TAPE": 5}}
			incoming = {"EXT": [(date(2026, 11, 25), 4), (date(2026, 11, 20), 4)]}
			result = pb.allocate(["SO-A", "SO-B", "SO-C"], needs, {"EXT": 12}, incoming)
			self.assertEqual(result["SO-A"]["short"], {})
			self.assertEqual(result["SO-B"]["short"], {"EXT": 8})  # 2 left after SO-A
			self.assertEqual(result["SO-B"]["eta"], date(2026, 11, 25))  # needs both POs
			self.assertEqual(result["SO-C"]["no_po"], ["TAPE"])
			self.assertIsNone(result["SO-C"]["eta"])

	def test_later_order_waits_for_po_quantity_left_over(self):
		with load_service(MODULE) as (pb, _):
			incoming = {"EXT": [(date(2026, 11, 20), 5), (date(2026, 12, 4), 5)]}
			result = pb.allocate(["A", "B"], {"A": {"EXT": 5}, "B": {"EXT": 5}}, {}, incoming)
			self.assertEqual(result["A"]["eta"], date(2026, 11, 20))
			self.assertEqual(result["B"]["eta"], date(2026, 12, 4))


class Capacity(unittest.TestCase):
	def test_workdays_skip_weekends_and_holidays(self):
		with load_service(MODULE) as (pb, _):
			days = pb.workdays(date(2026, 11, 25), 3, {date(2026, 11, 26), date(2026, 11, 27)})
			self.assertEqual(days, [date(2026, 11, 25), date(2026, 11, 30), date(2026, 12, 1)])
			self.assertEqual(pb.next_workday(date(2026, 11, 20), set()), date(2026, 11, 23))

	def test_burndown_matches_workbook(self):
		"""Feb workbook: 1,790.05 points, 316.49 a day, today partly done; clears on day 6."""
		with load_service(MODULE) as (pb, _):
			days = pb.workdays(date(2026, 2, 6), 8, set())
			rows, clear = pb.burndown(1790.05, 316.4916, 13.187, days)
			self.assertAlmostEqual(rows[0]["remaining"], 1776.86, places=2)
			self.assertAlmostEqual(rows[1]["remaining"], 1460.37, places=2)
			self.assertEqual(clear, "2026-02-16")

	def test_overtime_daily_and_monday_weekend(self):
		with load_service(MODULE) as (pb, _):
			days = pb.workdays(date(2026, 11, 20), 3, set())  # Fri, Mon, Tue
			rows, _ = pb.burndown(1000, 100, 50, days, ot_daily=10, ot_days=1, ot_weekend=30)
			self.assertEqual([r["capacity"] for r in rows], [60, 130, 100])

	def test_shift_left_fraction(self):
		with load_service(MODULE) as (pb, _):
			now = datetime(2026, 11, 18, 12, 30)
			self.assertAlmostEqual(pb.shift_left_fraction(now, time(16, 30), 8), 0.5)
			self.assertEqual(pb.shift_left_fraction(datetime(2026, 11, 18, 17, 0), time(16, 30), 8), 0)


class Board(unittest.TestCase):
	def _board(self, money=True):
		with load_service(MODULE) as (pb, _):
			settings = patch.object(
				pb.build_points,
				"settings",
				return_value={
					"points_per_person_day": 57.5,
					"headcount": 5.5,
					"paid_hours_per_day": 8.5,
					"shift_hours": 8,
					"shift_end_time": "16:30:00",
					"monthly_revenue_goal": 100000,
				},
			)
			orders = [
				Record(name="SO-1", customer_name="A", status="To Deliver", net_total=25251.88, total_commission=4800.38, per_delivered=0, delivery_date="2026-11-20", ill_build_points=322, ill_runs_2c=23, ill_wet=92, ill_fmc=69),
				Record(name="SO-2", customer_name="B", status="To Deliver", net_total=1000, total_commission=0, per_delivered=0, delivery_date="2026-11-10", ill_estimated_ship_date="2026-11-16", ill_build_points=40),
				Record(name="SO-3", customer_name="C", status="To Deliver", net_total=5000, total_commission=500, per_delivered=0, delivery_date="2026-11-19", ill_build_points=30),
			]
			wos = [
				Record(name="WO-1", sales_order="SO-1", status="In Process", qty=1, produced_qty=0),
				Record(name="WO-2", sales_order="SO-2", status="Not Started", qty=1, produced_qty=0),
				Record(name="WO-3", sales_order="SO-3", status="Not Started", qty=1, produced_qty=0),
			]
			shipped = [
				{"amount": 2000, "com": 200, "shipped": "2026-11-18", "on_time": True, "not_warehouse_fault": False},
				{"amount": 1000, "com": 100, "shipped": "2026-11-03", "on_time": False, "not_warehouse_fault": False},
			]
			with settings, patch.object(pb, "holiday_dates", return_value=set()), patch.object(
				pb, "open_orders", return_value=orders
			), patch.object(pb, "work_orders_for", return_value=wos), patch.object(
				pb, "material_needs", return_value={"SO-3": {"EXT": 4}}
			), patch.object(pb, "stock_on_hand", return_value={}), patch.object(
				pb, "incoming_purchases", return_value={"EXT": [(date(2026, 12, 3), 10)]}
			), patch.object(pb, "shipments_this_month", return_value=shipped):
				return pb.build_board(now=datetime(2026, 11, 18, 12, 30), money=money), pb

	def test_board_numbers(self):
		board, pb = self._board()
		statuses = {r["so"]: r["status"] for r in board["queue"] + board["wfp"]}
		self.assertEqual(statuses, {"SO-1": pb.IN_PROD, "SO-2": pb.PEND_PROD, "SO-3": pb.WFP})
		first = next(r for r in board["queue"] if r["so"] == "SO-1")
		self.assertAlmostEqual(first["worth"], 63.51, places=2)  # workbook Worth for SO 67312
		self.assertEqual(first["counts"]["wet"], 92)
		wfp = board["wfp"][0]
		self.assertEqual(wfp["eta"], "2026-12-03")
		self.assertTrue(wfp["going_to_miss"])
		self.assertFalse(wfp["this_month"])
		capacity = board["capacity"]
		self.assertEqual(capacity["whse_points"], 362)
		self.assertEqual(capacity["wfp_month_points"], 0)  # parts arrive next month
		self.assertAlmostEqual(capacity["capacity_per_day"], 316.25)
		self.assertAlmostEqual(capacity["left_today"], 158.12, places=2)  # half the shift left
		self.assertEqual(capacity["date_clear"], "2026-11-19")
		self.assertEqual(board["due"]["past_due"]["count"], 1)  # SO-2 ship date 11/16
		self.assertEqual(board["shipped"]["mtd"]["amount"], 3000)
		self.assertEqual(board["shipped"]["on_time_pct"], 0.5)
		self.assertEqual(board["goal"]["available_to_ship"], 26251.88)  # SO-3 waits into December
		self.assertEqual(board["goal"]["shipping_days_left"], 8)

	def test_money_hidden_without_role(self):
		board, _ = self._board(money=False)
		self.assertIsNone(board["queue"][0]["amount"])
		self.assertIsNone(board["queue"][0]["worth"])
		self.assertIsNone(board["pipeline"]["in_prod"]["amount"])
		self.assertIsNone(board["shipped"]["mtd"]["amount"])
		self.assertIsNone(board["goal"]["gap"])
		self.assertEqual(board["pipeline"]["in_prod"]["points"], 322)

	def test_view_role_required(self):
		with load_service(MODULE) as (pb, frappe):
			frappe.get_roles.return_value = ["Dealer"]
			with self.assertRaises(PermissionError):
				pb.get_board()


if __name__ == "__main__":
	unittest.main()


class Phase3Helpers(unittest.TestCase):
	def test_hold_reason_and_paint_status(self):
		with load_service(MODULE) as (pb, _):
			order = Record(status="To Deliver", ill_build_points=5)
			started = [Record(status="Not Started", qty=1, produced_qty=0)]
			self.assertEqual(pb.order_status(Record(order, ill_hold_reason="Hold for Ship"), started, False), pb.HELD)
			self.assertEqual(pb.order_status(order, started, True, paint_open=True), pb.PAINT)
			done = [Record(status="Completed", qty=1, produced_qty=1)]
			self.assertEqual(pb.order_status(order, done, False, paint_open=True), pb.PEND_SHIP)

	def test_inbound_same_next_and_rush(self):
		with load_service(MODULE) as (pb, _):
			fri = date(2026, 11, 20)
			received = [
				{"received": fri, "esd": fri, "amount": 100, "com": 10},
				{"received": fri, "esd": date(2026, 11, 23), "amount": 0, "com": 0},  # Monday = next workday
				{"received": fri, "esd": date(2026, 11, 25), "amount": 50, "com": 5},  # 3rd workday = rush
				{"received": fri, "esd": date(2026, 11, 26), "amount": 50, "com": 5},
			]
			(row,) = pb.inbound_days(received, [fri], set())
			self.assertEqual((row["count"], row["amount"], row["zero"]), (4, 200, 1))
			self.assertEqual((row["same_day"], row["next_day"], row["rush"]), (1, 1, 3))
			self.assertEqual(row["com_pct"], 0.1)

	def test_month_helpers_and_scrub(self):
		with load_service(MODULE) as (pb, _):
			self.assertEqual(pb.add_months(date(2026, 11, 1), 2), date(2027, 1, 1))
			rows = [{"d": "2026-12-05", "amount": 10, "com": 1}, {"d": "2027-01-02", "amount": 5, "com": 0}]
			totals = pb.month_totals(rows, "d", [date(2026, 12, 1), date(2027, 1, 1)])
			self.assertEqual([t["amount"] for t in totals], [10, 5])
			board = {"a": [{"amount": 1, "shipped": "2026-11-18", "points": 3, "x_amount": 9}], "goal": {"gap": 5}}
			pb.scrub(board)
			self.assertEqual(board, {"a": [{"amount": None, "shipped": "2026-11-18", "points": 3, "x_amount": None}], "goal": {"gap": None}})


class Phase3Board(unittest.TestCase):
	def test_sections(self):
		with load_service(MODULE) as (pb, _):
			settings = patch.object(
				pb.build_points,
				"settings",
				return_value={"points_per_person_day": 57.5, "headcount": 5.5, "monthly_revenue_goal": 1000},
			)
			orders = [
				Record(name="SO-BUILD", status="To Deliver", net_total=1000, total_commission=100, per_delivered=0, delivery_date="2026-11-25", ill_build_points=10),
				Record(name="SO-REL", status="To Deliver", net_total=5000, total_commission=500, per_delivered=0, delivery_date="2026-12-20", ill_hold_reason="Hold for Release", ill_likely_ship_date="2026-12-10", ill_runs_2c=4, ill_assembly=2),
				Record(name="SO-HFS", status="To Deliver", net_total=2000, total_commission=0, per_delivered=0, delivery_date="2026-11-30", ill_hold_reason="Hold for Ship"),
				Record(name="SO-PRO", status="To Deliver", net_total=300, total_commission=0, per_delivered=0, delivery_date="2026-11-24", ill_proforma_will_call="Proforma"),
				Record(name="SO-PAINT", status="To Deliver", net_total=700, total_commission=0, per_delivered=0, delivery_date="2026-11-26", ill_build_points=4),
			]
			wos = [
				Record(name="WO-1", sales_order="SO-BUILD", status="Not Started", qty=1, produced_qty=0),
				Record(name="WO-2", sales_order="SO-PAINT", status="Not Started", qty=1, produced_qty=0),
			]
			shipped = [{"amount": 400, "com": 40, "shipped": "2026-11-17", "on_time": True, "not_warehouse_fault": False, "prowc": "Will Call"}]
			received = [{"received": date(2026, 11, 17), "esd": date(2026, 11, 17), "amount": 900, "com": 90}]
			paint = {"SO-PAINT": [{"po": "PO-1", "sent": "2026-11-10", "due_back": "2026-11-19", "item": "CH", "item_name": "Channel", "qty": 3}]}
			with settings, patch.object(pb, "holiday_dates", return_value=set()), patch.object(pb, "open_orders", return_value=orders), patch.object(
				pb, "work_orders_for", return_value=wos
			), patch.object(pb, "material_needs", return_value={}), patch.object(pb, "stock_on_hand", return_value={}), patch.object(
				pb, "incoming_purchases", return_value={}
			), patch.object(pb, "shipments_this_month", return_value=shipped), patch.object(
				pb, "received_orders", return_value=received
			), patch.object(pb, "paint_jobs", return_value=paint), patch.object(
				pb, "goals", return_value={date(2026, 12, 1): 9000}
			):
				board = pb.build_board(now=datetime(2026, 11, 18, 9, 0))
				hidden = pb.build_board(now=datetime(2026, 11, 18, 9, 0), money=False)
		queue = {r["so"] for r in board["queue"]}
		self.assertEqual(queue, {"SO-BUILD", "SO-PRO", "SO-PAINT"})  # holds are off the queue
		self.assertEqual(next(r for r in board["queue"] if r["so"] == "SO-PAINT")["status"], pb.PAINT)
		releases = board["releases"]
		self.assertEqual([r["so"] for r in releases["rows"]], ["SO-REL"])
		self.assertEqual(releases["points"], 4 + 2 * 4.0)  # release weights: assembly 4
		self.assertEqual(releases["months"][1]["amount"], 5000)
		self.assertEqual(board["ship_holds"]["rows"][0]["days_until"], 12)
		nov, dec, _ = board["reporting"]
		self.assertEqual(nov["goal_amount"], 1000)  # falls back to the single goal
		self.assertEqual(dec["goal_amount"], 9000)
		self.assertEqual(nov["shipped_amount"], 400)
		self.assertEqual(nov["scheduled_amount"], 1000 + 2000 + 300 + 700)  # includes hold for ship
		self.assertEqual(dec["release_amount"], 5000)
		# 30-day average counts quiet days as zero: 900 over 29 earlier workdays, x 8 workdays left.
		self.assertAlmostEqual(nov["run_rate_amount"], round(round(900 / 29, 2) * 8, 2))
		self.assertEqual(board["inbound"]["today_amount"], 0)
		self.assertEqual(board["prowc"]["proforma"]["open_amount"], 300)
		self.assertEqual(board["prowc"]["will_call"]["completed_amount"], 400)
		self.assertEqual(board["paint"]["total_amount"], 700)
		self.assertIsNone(hidden["reporting"][0]["projected_amount"])
		self.assertIsNone(hidden["releases"]["rows"][0]["amount"])
		self.assertEqual(hidden["releases"]["points"], 12)
