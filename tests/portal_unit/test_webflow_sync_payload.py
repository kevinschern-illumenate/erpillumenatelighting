"""The template part of the Webflow sync payload (plan 4.16, 4.19)."""

import unittest

from test_services import ROOT, load_service

MODULE = ROOT + ".webflow_sync_payload"


class Shapes(unittest.TestCase):
	def test_specifications_keep_label_value_and_table_order(self):
		with load_service(MODULE) as (module, _frappe):
			rows = module.specification_rows(
				[
					{"spec_label": "Length", "spec_value": "8 ft", "display_order": 40},
					{"spec_label": "CRI", "spec_value": "90"},
				]
			)
		self.assertEqual(
			rows,
			[
				{"spec_label": "Length", "spec_value": "8 ft", "order": 1},
				{"spec_label": "CRI", "spec_value": "90", "order": 2},
			],
		)

	def test_configurator_has_the_five_signed_off_fields_or_nothing(self):
		with load_service(MODULE) as (module, _frappe):
			row = {
				"option_step": 1,
				"option_type": "Finish",
				"option_label": "Finish",
				"option_description": "x",
				"is_required": 1,
				"depends_on_step": None,
				"allowed_values_json": "[]",
			}
			self.assertEqual(
				module.configurator_rows([row], True),
				[
					{
						"option_step": 1,
						"option_label": "Finish",
						"is_required": 1,
						"depends_on_step": None,
						"allowed_values_json": "[]",
					}
				],
			)
			self.assertEqual(module.configurator_rows([row], False), [])

	def test_certifications_in_order_with_code_and_badge(self):
		with load_service(MODULE) as (module, _frappe):
			rows = module.certification_rows(
				[
					{"certification": "UL", "badge_image": "/files/spec-sheet-dark.svg"},
					{"certification": None},
					{"certification": "ETL"},
				],
				{"UL": {"certification_code": "cULus", "badge_image": "/files/ul.svg"}},
			)
		self.assertEqual(
			rows,
			[
				{
					"certification": "UL",
					"certification_code": "cULus",
					"badge_image": "/files/ul.svg",
					"order": 1,
				},
				{"certification": "ETL", "certification_code": "ETL", "badge_image": None, "order": 2},
			],
		)

	def test_price_per_foot_falls_back_to_base_price(self):
		with load_service(MODULE) as (module, _frappe):
			self.assertEqual(module.price_per_foot({"price_per_ft_msrp": 12.5, "base_price_msrp": 99}), 12.5)
			self.assertEqual(module.price_per_foot({"price_per_ft_msrp": 0, "base_price_msrp": 99}), 99.0)
			self.assertIsNone(module.price_per_foot({}))


if __name__ == "__main__":
	unittest.main()
