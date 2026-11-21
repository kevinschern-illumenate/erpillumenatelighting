"""CAD toolkit plan 5.4: order lines against shipped lines, from ERP data."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".report.cad_bom_match.cad_bom_match"


class BomMatch(unittest.TestCase):
	def test_match_counts_lines_by_item_and_quantity(self):
		with load_service(MODULE) as (module, _frappe):
			result = module.match({"A": 2, "B": 1, "C": 4}, {"A": 2, "B": 0.5, "C": 5, "D": 1})
		self.assertEqual(result["matched_lines"], 1)
		self.assertEqual((result["short"], result["over"], result["extra"]), ("B", "C", "D"))
		self.assertEqual(result["match_pct"], 25.0)

	def test_execute_keeps_drawing_jobs_and_summarizes(self):
		with load_service(MODULE) as (module, frappe):
			frappe._dict = Record
			frappe.get_meta.return_value.has_field.return_value = True
			frappe.db.exists.return_value = True
			frappe.utils.add_days = lambda value, days: value

			def get_all(doctype, filters=None, fields=None, pluck=None, order_by=None):
				if doctype == "Sales Order":
					return [
						Record(name="SO-1", customer="C1", transaction_date="2026-11-01", ill_fixture_schedule="S1-v2", per_delivered=100),
						Record(name="SO-2", customer="C1", transaction_date="2026-11-02", ill_fixture_schedule="S9", per_delivered=0),
					]
				if doctype == "ilL-CAD-Import":
					return [Record(schedule="S1", source_tool="dxf")]
				if doctype == "ilL-Project-Fixture-Schedule":
					names = filters["name"][1]
					parents = {"S1": None, "S1-v2": "S1", "S9": None}
					return [Record(name=name, version_parent=parents[name]) for name in names]
				if doctype == "Sales Order Item":
					return [Record(parent="SO-1", item_code="A", qty=2), Record(parent="SO-1", item_code="B", qty=1)]
				if doctype == "Delivery Note Item":
					return [Record(against_sales_order="SO-1", item_code="A", qty=1), Record(against_sales_order="SO-1", item_code="A", qty=1), Record(against_sales_order="SO-1", item_code="B", qty=1)]
				return []

			frappe.get_all = MagicMock(side_effect=get_all)
			_columns, rows, _message, _chart, summary = module.execute({"from_date": "2026-10-01", "to_date": "2026-11-20"})
		self.assertEqual([row["sales_order"] for row in rows], ["SO-1"])
		self.assertEqual((rows[0]["matched_lines"], rows[0]["match_pct"]), (2, 100.0))
		self.assertTrue(rows[0]["drawing_import"])
		self.assertEqual(rows[0]["drawing_tool"], "dxf")
		self.assertEqual(summary[1]["value"], "100.0%")
		with load_service(MODULE) as (module, frappe):
			frappe._dict = Record
			frappe.get_meta.return_value.has_field.return_value = True
			frappe.db.exists.return_value = True
			frappe.utils.add_days = lambda value, days: value
			frappe.get_all = MagicMock(side_effect=get_all)
			self.assertEqual(module.execute({"source_tool": "bluebeam"})[1], [])
			self.assertEqual(len(module.execute({"source_tool": "dxf"})[1]), 1)


if __name__ == "__main__":
	unittest.main()
