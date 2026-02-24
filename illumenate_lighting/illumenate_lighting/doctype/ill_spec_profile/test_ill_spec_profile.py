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
