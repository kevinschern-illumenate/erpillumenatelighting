"""Configured quote / order lines carry the MSRP the portal shows, on the document's own price list."""

import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

LISTS = {
	"Standard Selling": Record(enabled=1, selling=1, currency="USD"),
	"MSRP": Record(enabled=1, selling=1, currency="USD"),
	"CAD Selling": Record(enabled=1, selling=1, currency="CAD"),
	"Old List": Record(enabled=0, selling=1, currency="USD"),
}


def generator(prices=None):
	"""manufacturing_generator with Price Lists and an Item Price table in memory."""
	prices = prices if prices is not None else []
	context = load_service(ROOT + ".api.manufacturing_generator")
	module, frappe = context.__enter__()
	frappe.log_error = MagicMock()
	frappe.db.get_value.side_effect = lambda doctype, name, *args, **kwargs: (
		LISTS.get(name) if doctype == "Price List" else None
	)

	def get_all(doctype, filters=None, **kwargs):
		rows = [
			p
			for p in prices
			if p.item_code == filters["item_code"] and p.price_list == filters["price_list"]
		]
		return rows[:1]

	frappe.get_all.side_effect = get_all

	def set_value(doctype, name, values, value=None):
		values = values if isinstance(values, dict) else {values: value}
		next(p for p in prices if p.name == name).update(values)

	frappe.db.set_value.side_effect = set_value

	def new_doc(doctype):
		doc = Record(name=f"IP-{len(prices) + 1}", valid_from="2026-10-22")
		doc.__dict__ = doc
		doc.insert = lambda **kwargs: prices.append(doc)
		return doc

	frappe.new_doc = new_doc
	return context, module, prices


class ItemPriceWriter(unittest.TestCase):
	def setUp(self):
		self.context, self.module, self.prices = generator()

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def test_zero_msrp_is_never_written(self):
		messages = []
		self.module._create_item_price_at_msrp("CF-1", 0.0, messages)
		self.assertEqual(self.prices, [])
		self.assertEqual(messages[0]["severity"], "warning")

	def test_new_price_applies_to_back_dated_documents(self):
		self.module._create_item_price_at_msrp("CF-1", 199.0, [])
		self.assertEqual(len(self.prices), 1)
		self.assertEqual(self.prices[0].price_list_rate, 199.0)
		self.assertIsNone(self.prices[0].valid_from)

	def test_a_zero_price_is_replaced_by_the_msrp(self):
		self.prices.append(Record(name="IP-0", item_code="CF-1", price_list="Standard Selling", price_list_rate=0, valid_from=None))
		self.module._create_item_price_at_msrp("CF-1", 199.0, [])
		self.assertEqual(self.prices[0].price_list_rate, 199.0)

	def test_disabled_list_is_reported_not_written(self):
		messages = []
		self.module._create_item_price_at_msrp("CF-1", 199.0, messages, price_list="Old List")
		self.assertEqual(self.prices, [])
		self.assertEqual(messages[0]["severity"], "error")


class MirrorToDocumentList(unittest.TestCase):
	def setUp(self):
		self.context, self.module, self.prices = generator(
			[Record(name="IP-PS", item_code="PS-60", price_list="Standard Selling", price_list_rate=85.0, valid_from=None)]
		)

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def on(self, price_list, item="PS-60"):
		return [p for p in self.prices if p.price_list == price_list and p.item_code == item]

	def test_power_supply_gets_its_standard_selling_price_on_the_quote_list(self):
		self.assertTrue(self.module.mirror_selling_price("PS-60", "MSRP"))
		self.assertEqual(self.on("MSRP")[0].price_list_rate, 85.0)

	def test_a_price_already_on_the_quote_list_is_kept_for_catalog_items(self):
		self.prices.append(Record(name="IP-X", item_code="PS-60", price_list="MSRP", price_list_rate=70.0, valid_from=None))
		self.assertFalse(self.module.mirror_selling_price("PS-60", "MSRP"))
		self.assertEqual(self.on("MSRP")[0].price_list_rate, 70.0)

	def test_configured_items_follow_their_current_msrp(self):
		self.prices.append(Record(name="IP-C", item_code="CF-1", price_list="MSRP", price_list_rate=150.0, valid_from=None))
		self.assertTrue(self.module.mirror_selling_price("CF-1", "MSRP", 199.0, overwrite=True))
		self.assertEqual(self.on("MSRP", "CF-1")[0].price_list_rate, 199.0)

	def test_standard_list_other_currency_and_unpriced_items_are_left_alone(self):
		self.assertFalse(self.module.mirror_selling_price("PS-60", "Standard Selling"))
		self.assertFalse(self.module.mirror_selling_price("PS-60", "CAD Selling"))
		self.assertFalse(self.module.mirror_selling_price("UNPRICED", "MSRP"))
		self.assertEqual(len(self.prices), 1)


class EnsureConfiguredItemPrice(unittest.TestCase):
	def test_explicit_zero_falls_back_to_the_current_estimate_and_reaches_the_quote_list(self):
		context, module, prices = generator()
		try:
			with (
				patch.object(module, "_ensure_brand_exists"),
				patch.object(module, "_configured_doc_msrp", return_value=240.0),
			):
				module.frappe.db.get_value.side_effect = lambda doctype, name, *a, **k: (
					LISTS.get(name) if doctype == "Price List" else module.ILLUMENATE_BRAND
				)
				doc = Record(doctype="ilL-Configured-Fixture", build_schema_version=2)
				self.assertTrue(module.ensure_configured_item_price("CF-1", doc, msrp=0.0, price_list="MSRP"))
			self.assertEqual(
				sorted((p.price_list, p.price_list_rate) for p in prices),
				[("MSRP", 240.0), ("Standard Selling", 240.0)],
			)
		finally:
			context.__exit__(None, None, None)


class RowPricing(unittest.TestCase):
	def test_power_supply_and_sheet_accessory_rows_are_not_configured_items(self):
		with load_service(ROOT + ".api.quote_order_configurator") as (module, _frappe):
			self.assertTrue(module._is_configured({"source_doctype": "ilL-Configured-Fixture"}))
			self.assertTrue(module._is_configured({"configured_group": "GRP-1"}))
			self.assertFalse(module._is_configured({"power_supply": {"is_power_supply_line": True}}))
			self.assertFalse(
				module._is_configured(
					{"source_doctype": "ilL-Configured-LED-Sheet", "configuration_snapshot": {"accessory_for": "S-1"}}
				)
			)

	def test_zero_prices_fall_through_to_the_engine_msrp(self):
		with load_service(ROOT + ".api.quote_order_configurator") as (module, frappe):
			frappe.get_all.return_value = [Record(price_list_rate=0)]
			self.assertIsNone(module._get_selling_rate("CF-1", "MSRP"))
			self.assertIsNone(module._artifact_msrp({"msrp_unit": 0.0}))
			self.assertEqual(module._artifact_msrp({"msrp_unit": 0.0, "total_msrp": 310.0}), 310.0)


if __name__ == "__main__":
	unittest.main()
