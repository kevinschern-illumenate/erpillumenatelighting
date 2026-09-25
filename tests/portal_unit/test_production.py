import unittest

from illumenate_lighting.illumenate_lighting.portal.production import production_coverage


class ProductionCoverage(unittest.TestCase):
	def test_one_completed_line_does_not_complete_unstarted_line(self):
		lines = [dict(name=name, item_code=name, qty=5, ill_bom="BOM") for name in ("A", "B")]
		work = [{"name": "WO", "sales_order_item": "A", "qty": 5, "produced_qty": 5}]
		coverage = production_coverage(lines, work)
		self.assertFalse(coverage["complete"])
		self.assertEqual([row["complete"] for row in coverage["lines"]], [True, False])

	def test_unique_item_mapping_and_stock_uom_conversion(self):
		lines = [dict(name="A", item_code="A", qty=2, conversion_factor=12, ill_bom="BOM")]
		coverage = production_coverage(
			lines, [{"name": "WO", "production_item": "A", "qty": 24, "produced_qty": 24}]
		)
		self.assertTrue(coverage["complete"])
		self.assertEqual(coverage["lines"][0]["produced_qty"], 2)

	def test_ambiguous_legacy_work_order_never_double_counts(self):
		lines = [dict(name=name, item_code="A", qty=1, ill_bom="BOM") for name in ("one", "two")]
		coverage = production_coverage(
			lines, [{"name": "WO", "production_item": "A", "qty": 2, "produced_qty": 2}]
		)
		self.assertFalse(coverage["complete"])
		self.assertEqual(coverage["unmapped_work_orders"], ["WO"])

	def test_standard_item_is_not_invented_manufacturing(self):
		coverage = production_coverage([dict(name="stock", item_code="STOCK", qty=10)], [])
		self.assertFalse(coverage["complete"])
		self.assertEqual(coverage["lines"][0]["path"], "standard_item")
		self.assertIsNone(coverage["lines"][0]["complete"])
