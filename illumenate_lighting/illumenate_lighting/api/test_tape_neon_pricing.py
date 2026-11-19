# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Standard Selling rates per stock unit (tape_neon_pricing.stock_unit_rate / selling_amount)."""

import unittest
from unittest.mock import patch

import frappe

from illumenate_lighting.illumenate_lighting.api.tape_neon_pricing import selling_amount, stock_unit_rate


def _price(rate, uom=None, valid_from=None, valid_upto=None):
	return frappe._dict(price_list_rate=rate, uom=uom, valid_from=valid_from, valid_upto=valid_upto)


class TestStockUnitRate(unittest.TestCase):
	def _rate(self, stock_uom, prices):
		with (
			patch.object(frappe.db, "get_value", return_value=stock_uom),
			patch.object(frappe, "get_all", return_value=prices),
		):
			return stock_unit_rate("ITEM-001")

	def test_ignores_prices_in_another_unit(self):
		self.assertEqual(self._rate("Inch", [_price(20.0, "Foot"), _price(1.6667, "Inch")]), 1.6667)

	def test_blank_price_uom_means_stock_unit(self):
		self.assertEqual(self._rate("Ea", [_price(75.0)]), 75.0)

	def test_skips_prices_outside_their_validity(self):
		prices = [_price(9.0, "Ea", valid_upto="2000-01-01"), _price(12.0, "Ea")]
		self.assertEqual(self._rate("Ea", prices), 12.0)

	def test_none_without_a_stock_unit_price(self):
		self.assertIsNone(self._rate("Inch", [_price(20.0, "Foot")]))

	def test_none_without_a_stock_uom(self):
		self.assertIsNone(self._rate(None, [_price(5.0)]))


class TestSellingAmount(unittest.TestCase):
	def test_multiplies_the_stock_unit_rate(self):
		with patch(
			"illumenate_lighting.illumenate_lighting.api.tape_neon_pricing.stock_unit_rate", return_value=1.5
		):
			self.assertEqual(selling_amount("ITEM-001", 24), 36.0)

	def test_still_requires_a_stock_unit_price(self):
		with patch(
			"illumenate_lighting.illumenate_lighting.api.tape_neon_pricing.stock_unit_rate", return_value=None
		):
			with self.assertRaisesRegex(ValueError, "stock UOM is required"):
				selling_amount("ITEM-001", 1)
