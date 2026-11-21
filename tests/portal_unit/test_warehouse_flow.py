"""Warehouse flow (Command Center Manufacturing → Flow, Shipping pick list)."""

import unittest
from datetime import date
from unittest.mock import patch

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".api.warehouse_flow"
TODAY = date(2026, 11, 19)


def wo(name, status="Not Started", docstatus=1, **kw):
	return Record(
		{
			"name": name,
			"status": status,
			"docstatus": docstatus,
			"qty": 1,
			"produced_qty": 0,
			"material_transferred_for_manufacturing": 0,
			**kw,
		}
	)


class Helpers(unittest.TestCase):
	def test_wo_lanes(self):
		with load_service(MODULE) as (wf, _):
			self.assertEqual(wf.wo_lane(wo("A", "Draft", 0), False), "draft")
			self.assertEqual(wf.wo_lane(wo("A"), False), "to_pick")
			self.assertEqual(wf.wo_lane(wo("A"), True), "waiting_parts")
			self.assertEqual(wf.wo_lane(wo("A", "In Process"), True), "in_process")
			self.assertEqual(
				wf.wo_lane(wo("A", material_transferred_for_manufacturing=1), False), "in_process"
			)
			self.assertEqual(wf.wo_lane(wo("A", "Completed"), False), "completed")
			self.assertEqual(wf.wo_lane(wo("A", "Stopped"), False), "stopped")

	def test_pick_lines_use_transferred_or_consumed(self):
		with load_service(MODULE) as (wf, _):
			req = [
				Record(
					item_code="TAPE",
					required_qty=100,
					transferred_qty=40,
					consumed_qty=10,
					stock_uom="Inch",
					source_warehouse="Stores",
				),
				Record(item_code="PSU", required_qty=2, transferred_qty=2, consumed_qty=0, stock_uom="Ea"),
			]
			rows = wf.wo_pick_lines(Record(skip_transfer=0), req)
			self.assertEqual([(r["item"], r["qty"]) for r in rows], [("TAPE", 60)])
			rows = wf.wo_pick_lines(Record(skip_transfer=1, source_warehouse="Main"), req)
			self.assertEqual(
				[(r["item"], r["qty"], r["warehouse"]) for r in rows],
				[("TAPE", 90, "Stores"), ("PSU", 2, "Main")],
			)

	def test_qty_summary_counts_pieces_and_lengths(self):
		with load_service(MODULE) as (wf, _):
			s = wf.qty_summary(
				[
					{"qty": 6, "uom": "Ea"},
					{"qty": 2, "uom": "Nos"},
					{"qty": 244.5, "uom": "Inch"},
					{"qty": 0, "uom": "Ea"},
				]
			)
			self.assertEqual(s, {"lines": 3, "pieces": 8, "other": [{"uom": "Inch", "qty": 244.5}]})

	def test_coverage_by_line_then_by_item(self):
		with load_service(MODULE) as (wf, _):
			lines = [
				Record(
					name="L1",
					item_code="FIX",
					qty=2,
					stock_qty=2,
					conversion_factor=1,
					delivered_qty=0,
					bom_no="BOM-FIX",
				),
				Record(
					name="L2",
					item_code="FIX",
					qty=3,
					stock_qty=3,
					conversion_factor=1,
					delivered_qty=0,
					bom_no="BOM-FIX",
				),
				Record(name="L3", item_code="NEON", qty=1, stock_qty=1, conversion_factor=1, delivered_qty=0),
				Record(name="L4", item_code="PSU", qty=1, stock_qty=1, conversion_factor=1, delivered_qty=0),
				Record(
					name="L5",
					item_code="BUILT",
					qty=1,
					stock_qty=1,
					conversion_factor=1,
					delivered_qty=1,
					bom_no="B",
				),
			]
			wos = [
				Record(
					name="W1",
					sales_order_item="L1",
					production_item="FIX",
					qty=2,
					status="Not Started",
					docstatus=1,
				),
				Record(
					name="W2",
					sales_order_item=None,
					production_item="FIX",
					qty=1,
					status="Draft",
					docstatus=0,
				),
				Record(
					name="W3",
					sales_order_item="L2",
					production_item="FIX",
					qty=3,
					status="Cancelled",
					docstatus=2,
				),
			]
			meta = {"NEON": {"default_bom": "BOM-NEON"}, "PSU": {"default_bom": None}}
			build, missing = wf.needs_work_orders(lines, wos, meta)
			self.assertEqual([b["name"] for b in build], ["L1", "L2", "L3", "L5"])  # PSU has no BOM
			# L2 gets the loose draft (1 of 3), L3 has nothing, L5 already delivered
			self.assertEqual([(m["line"], m["missing"]) for m in missing], [("L2", 2), ("L3", 1)])

	def test_ship_pick_lines(self):
		with load_service(MODULE) as (wf, _):
			lines = [
				Record(
					name="L1",
					item_code="TAPE",
					item_name="Tape",
					qty=10,
					delivered_qty=4,
					picked_qty=0,
					conversion_factor=1,
					stock_uom="Inch",
					warehouse="Stores",
				),
				Record(name="L2", item_code="KIT", qty=4, delivered_qty=2, picked_qty=0),
				Record(name="L3", item_code="SAMPLE", qty=1, delivered_qty=0, picked_qty=0),
				Record(name="L4", item_code="DROP", qty=5, delivered_qty=0, delivered_by_supplier=1),
				Record(name="L5", item_code="PSU", qty=2, delivered_qty=0, picked_qty=2, stock_uom="Ea"),
			]
			packed = [
				Record(
					parent_detail_docname="L2",
					item_code="CH",
					qty=4,
					picked_qty=0,
					uom="Ea",
					warehouse="Stores",
				),
				Record(parent_detail_docname="L2", item_code="EC", qty=8, picked_qty=1, uom="Ea"),
			]
			meta = {"KIT": {"is_stock_item": 0}, "SAMPLE": {"is_stock_item": 0}, "TAPE": {"is_stock_item": 1}}
			rows = wf.ship_pick_lines(lines, packed, meta)
			self.assertEqual([(r["item"], r["qty"]) for r in rows], [("TAPE", 6), ("CH", 2), ("EC", 3)])
			self.assertEqual(rows[1]["kit"], "KIT")

	def test_order_step_precedence(self):
		with load_service(MODULE) as (wf, _):
			order = Record(status="To Deliver")
			lanes = lambda *ls: [{"lane": x} for x in ls]  # noqa: E731
			self.assertEqual(wf.order_step(Record(status="On Hold"), [], []), "held")
			self.assertEqual(wf.order_step(order, [], lanes("stopped", "in_process")), "held")
			self.assertEqual(wf.order_step(order, [{"line": "L1"}], lanes("draft")), "needs_wo")
			self.assertEqual(wf.order_step(order, [], lanes("draft", "in_process")), "draft_wo")
			self.assertEqual(wf.order_step(order, [], lanes("in_process", "waiting_parts")), "building")
			self.assertEqual(wf.order_step(order, [], lanes("to_pick", "waiting_parts")), "waiting_parts")
			self.assertEqual(wf.order_step(order, [], lanes("to_pick", "completed")), "to_pick")
			self.assertEqual(wf.order_step(order, [], lanes("completed")), "to_ship")
			self.assertEqual(wf.order_step(order, [], []), "to_ship")
			self.assertEqual(
				wf.order_step(Record(ill_stage_override="Paint"), [], lanes("to_pick")),
				"building",
			)


class Flow(unittest.TestCase):
	def _flow(self):
		with load_service(MODULE) as (wf, _):
			orders = [
				Record(
					name="SO-A",
					customer_name="A",
					status="To Deliver",
					delivery_date="2026-11-25",
					per_delivered=0,
				),
				Record(
					name="SO-B",
					customer_name="B",
					status="To Deliver",
					delivery_date="2026-11-18",
					ill_estimated_ship_date="2026-11-20",
					per_delivered=0,
				),
				Record(
					name="SO-C",
					customer_name="C",
					status="To Deliver",
					delivery_date="2026-11-10",
					per_delivered=0,
				),
			]
			so_items = [
				Record(
					parent="SO-A",
					name="A1",
					item_code="FIX",
					qty=1,
					stock_qty=1,
					conversion_factor=1,
					delivered_qty=0,
					bom_no="BOM-FIX",
				),
				Record(
					parent="SO-B",
					name="B1",
					item_code="FIX",
					qty=1,
					stock_qty=1,
					conversion_factor=1,
					delivered_qty=0,
					bom_no="BOM-FIX",
				),
				Record(
					parent="SO-C",
					name="C1",
					item_code="EXT",
					qty=10,
					stock_qty=10,
					conversion_factor=1,
					delivered_qty=0,
					picked_qty=0,
					stock_uom="Ea",
				),
				Record(
					parent="SO-C",
					name="C2",
					item_code="NEON",
					qty=1,
					stock_qty=1,
					conversion_factor=1,
					delivered_qty=0,
					bom_no="BOM-N",
					stock_uom="Ea",
				),
			]
			wos = [
				Record(
					name="WO-A",
					sales_order="SO-A",
					sales_order_item="A1",
					production_item="FIX",
					status="Not Started",
					docstatus=1,
					qty=1,
					produced_qty=0,
				),
				Record(
					name="WO-B",
					sales_order="SO-B",
					sales_order_item="B1",
					production_item="FIX",
					status="Not Started",
					docstatus=1,
					qty=1,
					produced_qty=0,
				),
				Record(
					name="WO-C",
					sales_order="SO-C",
					sales_order_item="C2",
					production_item="NEON",
					status="Completed",
					docstatus=1,
					qty=1,
					produced_qty=1,
				),
				Record(
					name="WO-OLD",
					sales_order="SO-GONE",
					production_item="FIX",
					status="Draft",
					docstatus=0,
					qty=1,
					produced_qty=0,
				),
			]
			required = [
				Record(parent="WO-A", item_code="EXT", required_qty=4, transferred_qty=0, stock_uom="Ea"),
				Record(parent="WO-B", item_code="EXT", required_qty=4, transferred_qty=0, stock_uom="Ea"),
			]
			data = {
				"orders": orders,
				"so_items": so_items,
				"packed": [],
				"item_meta": {"EXT": {"is_stock_item": 1}},
				"wos": wos,
				"required": required,
				"stock": {"EXT": 6},
				"incoming": {"EXT": [(date(2026, 12, 1), 50)]},
				"pick_lists": [
					Record(name="PL-1", purpose="Delivery", status="Open", docstatus=1),
					Record(name="PL-OLD", purpose="Delivery", status="Open", docstatus=1),
				],
				"pick_locations": [
					Record(parent="PL-1", sales_order="SO-C", qty=2, stock_qty=2, stock_uom="Ea"),
					Record(parent="PL-OLD", sales_order="SO-GONE", qty=1, stock_qty=1, stock_uom="Ea"),
				],
				"draft_dns": [
					Record(
						name="DN-OLD", customer_name="Z", posting_date="2026-10-01", sales_orders=["SO-GONE"]
					)
				],
				"shipped": [{"name": "DN-9", "customer": "Y", "posting_date": "2026-11-18"}],
			}
			return wf.build_flow(data, TODAY)

	def test_stock_goes_to_earlier_ship_date_and_steps(self):
		flow = self._flow()
		wos = {w["name"]: w for w in flow["work_orders"]}
		# SO-B ships 11/20 (estimated ship date) before SO-A on 11/25, so it gets the 4 EXT first.
		self.assertEqual(wos["WO-B"]["lane"], "to_pick")
		self.assertEqual(wos["WO-A"]["lane"], "waiting_parts")
		self.assertEqual(wos["WO-A"]["short"], [{"item": "EXT", "qty": 2}])
		self.assertEqual(wos["WO-A"]["eta"], "2026-12-01")
		self.assertFalse(wos["WO-OLD"]["so_open"])
		steps = {o["so"]: o["step"] for o in flow["orders"]}
		self.assertEqual(steps, {"SO-A": "waiting_parts", "SO-B": "to_pick", "SO-C": "to_ship"})
		self.assertEqual([o["so"] for o in flow["orders"]], ["SO-C", "SO-B", "SO-A"])  # by ship date

	def test_ship_pick_gets_stock_left_after_work_orders(self):
		flow = self._flow()
		c = next(o for o in flow["orders"] if o["so"] == "SO-C")
		# all 6 EXT went to WO-B / WO-A; the neon its work order built is picked for shipping too
		self.assertEqual(
			[(p["item"], p["qty"], p["short"]) for p in c["pick"]], [("EXT", 10, 10), ("NEON", 1, 1)]
		)
		self.assertTrue(c["pick_short"])
		self.assertTrue(c["past_due"])
		self.assertEqual(c["pick_lists"], ["PL-1"])

	def test_summary(self):
		s = self._flow()["summary"]
		self.assertEqual(s["orders"], 3)
		self.assertEqual((s["build_orders"], s["covered"], s["uncovered"], s["stock_only"]), (3, 3, 0, 0))
		self.assertEqual(s["wo_lanes"]["draft"], 1)
		self.assertEqual(s["wo_no_open_order"], 1)
		self.assertEqual(s["pick_production"]["work_orders"], 1)  # WO-A waits for parts
		self.assertEqual(s["pick_production"]["pieces"], 4)
		self.assertEqual(
			s["pick_shipping"], {"orders": 1, "short_orders": 1, "lines": 2, "pieces": 11, "other": []}
		)
		self.assertEqual(
			(s["pick_lists_open"], s["pick_lists_stale"], s["draft_dns"], s["draft_dns_stale"]), (1, 1, 0, 1)
		)
		self.assertEqual(s["shipped_week"], 1)
		self.assertEqual(s["past_due"], 1)

	def test_view_role_required(self):
		with load_service(MODULE) as (wf, frappe):
			frappe.get_roles.return_value = ["Dealer"]
			with self.assertRaises(PermissionError):
				wf.get_flow()

	def test_stock_user_can_read(self):
		with load_service(MODULE) as (wf, frappe):
			frappe.get_roles.return_value = ["Stock User"]
			with patch.object(wf, "read_flow", return_value={"orders": []}) as read:
				flow = wf.get_flow()
			read.assert_called_once()
			self.assertEqual(flow["summary"]["orders"], 0)


if __name__ == "__main__":
	unittest.main()
