# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Unit tests for computed virtual fields in _get_source_value().

These tests use unittest.mock to avoid requiring a full Frappe environment.
"""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

# Stub out frappe and its sub-modules so the import succeeds without the framework
_frappe_mock = MagicMock()
sys.modules.setdefault("frappe", _frappe_mock)
sys.modules.setdefault("frappe.utils", MagicMock())
sys.modules.setdefault("frappe.utils.file_manager", MagicMock())

from illumenate_lighting.illumenate_lighting.api.spec_submittal import _get_source_value  # noqa: E402


class TestGetSourceValueComputedFields(unittest.TestCase):
	"""Test computed virtual fields (__start_leader_cable_len_mm, __end_length_indicator)."""

	# ── __start_leader_cable_len_mm ──────────────────────────────────────

	def test_start_leader_cable_len_mm_with_segments(self):
		"""Returns first segment's start_leader_len_mm when segments exist."""
		seg = SimpleNamespace(start_leader_len_mm=305)
		cf = SimpleNamespace(name="CF-001", segments=[seg])

		result = _get_source_value(
			"ilL-Configured-Fixture",
			"__start_leader_cable_len_mm",
			configured_fixture=cf,
		)
		self.assertEqual(result, 305)

	def test_start_leader_cable_len_mm_no_segments(self):
		"""Returns None when segments list is empty."""
		cf = SimpleNamespace(name="CF-002", segments=[])

		result = _get_source_value(
			"ilL-Configured-Fixture",
			"__start_leader_cable_len_mm",
			configured_fixture=cf,
		)
		self.assertIsNone(result)

	def test_start_leader_cable_len_mm_segments_none(self):
		"""Returns None when segments attribute is None."""
		cf = SimpleNamespace(name="CF-003", segments=None)

		result = _get_source_value(
			"ilL-Configured-Fixture",
			"__start_leader_cable_len_mm",
			configured_fixture=cf,
		)
		self.assertIsNone(result)

	def test_start_leader_cable_len_mm_multiple_segments(self):
		"""Returns FIRST segment's start_leader_len_mm even when multiple exist."""
		seg1 = SimpleNamespace(start_leader_len_mm=610)
		seg2 = SimpleNamespace(start_leader_len_mm=0)
		cf = SimpleNamespace(name="CF-004", segments=[seg1, seg2])

		result = _get_source_value(
			"ilL-Configured-Fixture",
			"__start_leader_cable_len_mm",
			configured_fixture=cf,
		)
		self.assertEqual(result, 610)

	# ── __end_length_indicator ───────────────────────────────────────────

	def test_end_length_indicator_single_segment(self):
		"""Returns empty string for single-segment fixture."""
		cf = SimpleNamespace(name="CF-010", is_multi_segment=0)

		result = _get_source_value(
			"ilL-Configured-Fixture",
			"__end_length_indicator",
			configured_fixture=cf,
		)
		self.assertEqual(result, "")

	def test_end_length_indicator_multi_segment(self):
		"""Returns 'J' for multi-segment fixture."""
		cf = SimpleNamespace(name="CF-011", is_multi_segment=1)

		result = _get_source_value(
			"ilL-Configured-Fixture",
			"__end_length_indicator",
			configured_fixture=cf,
		)
		self.assertEqual(result, "J")

	def test_end_length_indicator_falsy_multi_segment(self):
		"""Returns empty string when is_multi_segment is falsy (False/None/0)."""
		for falsy in (False, None, 0, ""):
			with self.subTest(is_multi_segment=falsy):
				cf = SimpleNamespace(name="CF-012", is_multi_segment=falsy)
				result = _get_source_value(
					"ilL-Configured-Fixture",
					"__end_length_indicator",
					configured_fixture=cf,
				)
				self.assertEqual(result, "")

	# ── Regular fields still work ────────────────────────────────────────

	def test_regular_field_still_resolves(self):
		"""Non-computed fields still resolve via getattr fallback."""
		cf = SimpleNamespace(name="CF-020", finish="BRASS")

		result = _get_source_value(
			"ilL-Configured-Fixture",
			"finish",
			configured_fixture=cf,
		)
		self.assertEqual(result, "BRASS")


if __name__ == "__main__":
	unittest.main()
