"""Webflow Product rules of 2026-11-05 (plan 4.17): features, 16:9 and power supply links."""

import json
import unittest

from test_services import ROOT, load_service

MODULE = ROOT + ".webflow_product_rules"


class Features(unittest.TestCase):
	def test_rows_become_the_features_json_in_order(self):
		with load_service(MODULE) as (module, _frappe):
			value = module.features_json(
				[
					{"title": " IDEAL FOR ", "description": "Coves"},
					{"title": "", "description": ""},
					{"title": "FINISH", "description": None},
				]
			)
		self.assertEqual(
			json.loads(value),
			[{"title": "IDEAL FOR", "description": "Coves"}, {"title": "FINISH", "description": ""}],
		)

	def test_no_rows_clear_features(self):
		with load_service(MODULE) as (module, _frappe):
			self.assertIsNone(module.features_json([]))

	def test_existing_json_is_read_back_into_rows(self):
		with load_service(MODULE) as (module, _frappe):
			self.assertEqual(
				module.feature_rows('[{"title": "A", "description": "B"}, "C"]'),
				[{"title": "A", "description": "B"}, {"title": "C", "description": ""}],
			)
			self.assertEqual(module.feature_rows(None), [])
			self.assertIsNone(module.feature_rows("{not json"))
			self.assertIsNone(module.feature_rows("[1, 2]"))


class AspectRatio(unittest.TestCase):
	def test_16_9_within_one_percent(self):
		with load_service(MODULE) as (module, _frappe):
			self.assertTrue(module.is_16_9(1920, 1080))
			self.assertTrue(module.is_16_9(1919, 1080))
			self.assertFalse(module.is_16_9(1600, 1200))
			self.assertTrue(module.is_16_9(0, 0))


class PowerSupplyLinks(unittest.TestCase):
	def test_calculated_rows_are_replaced_and_hand_rows_kept(self):
		with load_service(MODULE) as (module, _frappe):
			rows = [
				{"related_product": "ps-old", "relationship_type": "Recommended With", "is_calculated": 1},
				{"related_product": "ps-hand", "relationship_type": "Recommended With", "is_calculated": 0},
				{"related_product": "tape-b", "relationship_type": "Recommended With", "is_calculated": 1},
				{"related_product": "ps-univ", "relationship_type": "Works With", "is_calculated": 0},
			]
			result = module.calculated_compatibility(
				rows, ["ps-univ", "ps-hand"], {"ps-old", "ps-hand", "ps-univ"}
			)
		self.assertEqual(
			[(r["related_product"], r["relationship_type"], r["is_calculated"]) for r in result],
			[
				("ps-hand", "Recommended With", 0),
				# A reverse row on a power supply (pointing at a tape) is not this product's to manage.
				("tape-b", "Recommended With", 1),
				("ps-univ", "Works With", 0),
				("ps-univ", "Recommended With", 1),
			],
		)


if __name__ == "__main__":
	unittest.main()
