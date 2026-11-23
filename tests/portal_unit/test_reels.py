"""Reel count kit (api/reels.py): scan routing, length rules, the count and the summary."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

TAPE = {
	"name": "TAPE-24V-2700K",
	"ill_reel_tracked": 1,
	"ill_standard_reel_length_mm": 30480,
	"ill_reel_scrap_line_mm": 610,
	"ill_reel_remnant_line_mm": 3048,
	"ill_reel_weight_g_per_m": 20,
	"ill_reel_core_weight_g": 150,
}


class Reels(unittest.TestCase):
	def setUp(self):
		self.ctx = load_service(ROOT + ".api.reels")
		self.reels, self.frappe = self.ctx.__enter__()
		self.addCleanup(self.ctx.__exit__, None, None, None)

	def test_route_scan(self):
		route = self.reels.route_scan
		self.assertEqual(route(" r-00041 \n"), {"kind": "reel", "value": "R-00041"})
		self.assertEqual(route("LOC-B3"), {"kind": "location", "value": "B3"})
		self.assertEqual(
			route("https://erp.test/app/work-order/MFG-WO-2026-00412"),
			{"kind": "work_order", "value": "MFG-WO-2026-00412"},
		)
		self.assertEqual(
			route("https://erp.test/app/work-order/WO%20A?x=1"), {"kind": "work_order", "value": "WO A"}
		)
		self.assertEqual(route("0123456789012"), {"kind": "item", "value": "0123456789012"})
		self.assertEqual(route("R-12")["kind"], "item")  # too short to be a reel ID
		self.assertEqual(route("")["kind"], "empty")

	def test_classify(self):
		classify = self.reels.classify
		self.assertEqual(classify(30480, TAPE, sealed=True), "Sealed")
		self.assertEqual(classify(20000, TAPE), "Open")
		self.assertEqual(classify(2000, TAPE), "Remnant")
		self.assertEqual(classify(0, TAPE), "Empty")
		self.assertEqual(classify(2000, {}), "Remnant")  # default remnant line is 10 ft

	def test_scrap_line(self):
		self.assertTrue(self.reels.under_scrap_line(300, TAPE))
		self.assertFalse(self.reels.under_scrap_line(610, TAPE))
		self.assertFalse(self.reels.under_scrap_line(0, TAPE))

	def test_weight_to_length(self):
		self.assertEqual(self.reels.weight_to_length(150 + 20 * 12.5, TAPE), 12500)
		with self.assertRaisesRegex(ValueError, "no more than the empty reel"):
			self.reels.weight_to_length(100, TAPE)
		with self.assertRaisesRegex(ValueError, "weight per metre"):
			self.reels.weight_to_length(500, {"name": "X"})

	def test_count_length(self):
		self.assertEqual(self.reels.count_length("Full", TAPE), 30480)
		self.assertEqual(self.reels.count_length("Measured", TAPE, length_mm="4000"), 4000)
		self.assertEqual(self.reels.count_length("Weighed", TAPE, weight_g=350), 10000)
		with self.assertRaisesRegex(ValueError, "standard reel length"):
			self.reels.count_length("Full", {"name": "X"})
		with self.assertRaisesRegex(ValueError, "Enter the length"):
			self.reels.count_length("Measured", TAPE)

	def test_stock_qty(self):
		self.assertAlmostEqual(self.reels.stock_qty(30480, "Foot"), 100)
		self.assertAlmostEqual(self.reels.stock_qty(1000, "Meter"), 1)
		with self.assertRaisesRegex(ValueError, "length stock UOM"):
			self.reels.stock_qty(100, "Nos")

	def test_summarize(self):
		reels = [
			{"item_code": "TAPE-A", "warehouse": "Stores", "current_length_mm": 30480},
			{"item_code": "TAPE-A", "warehouse": "Stores", "current_length_mm": 3048},
			{"item_code": "NEON-B", "warehouse": "Stores", "current_length_mm": 15240},
		]
		rows = self.reels.summarize(
			reels,
			{("TAPE-A", "Stores"): 120},
			{"TAPE-A": {"stock_uom": "Foot", "item_name": "Tape A"}, "NEON-B": {"stock_uom": "Foot"}},
		)
		self.assertEqual([r["item_code"] for r in rows], ["NEON-B", "TAPE-A"])
		tape = rows[1]
		self.assertEqual(tape["reels"], 2)
		self.assertEqual(tape["counted_qty"], 110)
		self.assertEqual(tape["erpnext_qty"], 120)
		self.assertEqual(tape["difference"], -10)
		self.assertEqual(tape["length"], "110'")
		self.assertEqual(rows[0]["difference"], 50)

	def test_feet_inches_matches_labels(self):
		with load_service(ROOT + ".api.labels") as (labels, _frappe):
			for mm in (0.5, 25.4, 304.8, 3124.2, 30480, 15239.9):
				self.assertEqual(self.reels.feet_inches(mm), labels.feet_inches(mm))

	def test_validate_reel_shows_the_length(self):
		doc = Record(item_code="TAPE", status="Open", current_length_mm=3124.2)
		self.reels.validate_reel(doc)
		self.assertEqual(doc.__dict__["length_display"], "10' 3\"")
		tag = Record(item_code=None, status="Tag only", current_length_mm=0)
		self.reels.validate_reel(tag)
		self.assertEqual(tag.__dict__["length_display"], "")

	def test_counting_needs_the_flag_and_a_role(self):
		self.frappe.db.get_single_value.return_value = 0
		with self.assertRaisesRegex(ValueError, "Turn on Reels"):
			self.reels.count_reel("R-00001", "TAPE")
		self.frappe.db.get_single_value.return_value = 1
		self.frappe.get_roles.return_value = ["Dealer"]
		with self.assertRaises(PermissionError):
			self.reels.count_reel("R-00001", "TAPE")

	def test_count_turns_a_tag_into_a_sealed_reel_with_a_count_movement(self):
		self.frappe.db.get_single_value.side_effect = lambda _d, field: {
			"reels_enabled": 1,
			"reels_default_warehouse": "Stores",
		}.get(field)
		self.frappe.get_roles.return_value = ["Stock User"]
		self.frappe.utils.nowdate = lambda: "2026-12-15"
		reel = MagicMock()
		reel.name, reel.status, reel.current_length_mm, reel.starting_length_mm = "R-00001", "Tag only", 0, 0
		reel.location = reel.warehouse = reel.supplier_lot = None
		self.frappe.db.get_value.side_effect = lambda doctype, name, fields, **kw: (
			Record(TAPE, item_name="Tape", stock_uom="Foot") if doctype == "Item" else "R-00001"
		)
		movements = []
		self.frappe.get_doc.side_effect = lambda arg, *rest: (
			reel if arg == "ilL-Reel" else movements.append(arg) or MagicMock()
		)
		result = self.reels.count_reel("R-00001", "TAPE-24V-2700K", method="Full")
		self.assertEqual(reel.status, "Sealed")
		self.assertEqual(reel.current_length_mm, 30480)
		self.assertEqual(reel.starting_length_mm, 30480)
		self.assertEqual(reel.warehouse, "Stores")
		reel.save.assert_called_once()
		self.assertEqual(movements[0]["movement_type"], "Count")
		self.assertEqual(movements[0]["length_mm"], 30480)
		self.assertFalse(result["under_scrap_line"])


if __name__ == "__main__":
	unittest.main()
