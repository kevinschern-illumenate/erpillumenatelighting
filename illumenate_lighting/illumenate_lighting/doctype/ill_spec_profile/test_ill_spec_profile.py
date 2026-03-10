# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

import sys
import unittest
from unittest.mock import MagicMock

# Mock frappe so the module can be imported outside a Frappe bench
sys.modules.setdefault("frappe", MagicMock())
sys.modules.setdefault("frappe.model", MagicMock())
sys.modules.setdefault("frappe.model.document", MagicMock())

from illumenate_lighting.illumenate_lighting.doctype.ill_spec_profile.ill_spec_profile import (
	_format_dimension,
	compute_profile_dimensions,
)


class TestFormatDimension(unittest.TestCase):
	def test_format_dimension_one_inch(self):
		self.assertEqual(_format_dimension(25.4), '1.00" (25.40mm)')

	def test_format_dimension_two_inches(self):
		self.assertEqual(_format_dimension(50.8), '2.00" (50.80mm)')

	def test_format_dimension_fractional_inch(self):
		self.assertEqual(_format_dimension(15.2), '0.60" (15.20mm)')

	def test_format_dimension_round_mm(self):
		self.assertEqual(_format_dimension(100), '3.94" (100.00mm)')


class TestComputeProfileDimensions(unittest.TestCase):
	"""Test compute_profile_dimensions() — the canonical dimensions formatter.

	This function is called:
	- by ilLSpecProfile._calculate_dimensions on save (to populate the stored field), and
	- by the Webflow sync paths as an on-the-fly fallback when a profile has not
	  yet been re-saved with the computed ``dimensions`` field.
	"""

	def test_both_width_and_height(self):
		result = compute_profile_dimensions(25.4, 50.8)
		self.assertEqual(result, '1.00" (25.40mm) x 2.00" (50.80mm)')

	def test_width_only(self):
		result = compute_profile_dimensions(25.4, None)
		self.assertEqual(result, '1.00" (25.40mm) (W)')

	def test_height_only(self):
		result = compute_profile_dimensions(None, 50.8)
		self.assertEqual(result, '2.00" (50.80mm) (H)')

	def test_no_dimensions(self):
		result = compute_profile_dimensions(None, None)
		self.assertEqual(result, "")

	def test_zero_values_treated_as_absent(self):
		"""Verify that 0.0 width/height produce an empty dimensions string."""
		result = compute_profile_dimensions(0, 0)
		self.assertEqual(result, "")

	def test_width_zero_height_set(self):
		result = compute_profile_dimensions(0, 50.8)
		self.assertEqual(result, '2.00" (50.80mm) (H)')

