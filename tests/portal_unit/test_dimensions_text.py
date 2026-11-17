# ruff: noqa: RUF001  (the expected text contains the curly inch mark and the multiplication sign)
"""The Dimensions specification (owner, 2026-11-12)."""

import unittest

from test_services import ROOT, load_service


class DimensionsText(unittest.TestCase):
	def test_fixture_length_width_height(self):
		with load_service(ROOT + ".template_calculations") as (module, _frappe):
			self.assertEqual(
				module.dimensions_text(15, 15, 304.8),
				"12.00” (304.8mm) × 0.59” (15mm) × 0.59” (15mm)",
			)

	def test_kit_width_height(self):
		with load_service(ROOT + ".template_calculations") as (module, _frappe):
			self.assertEqual(module.dimensions_text(16, 16), "0.63” (16mm) × 0.63” (16mm)")

	def test_the_profiles_text_is_the_fallback(self):
		with load_service(ROOT + ".template_calculations") as (module, _frappe):
			self.assertEqual(module.dimensions_text(None, 15, None, '1.00" x 0.50"'), '1.00" x 0.50"')
			self.assertEqual(
				module.dimensions_text(None, None, 304.8, '1.00" x 0.50"'), '12.00” (304.8mm) × 1.00" x 0.50"'
			)
			self.assertIsNone(module.dimensions_text(None, None))


if __name__ == "__main__":
	unittest.main()
