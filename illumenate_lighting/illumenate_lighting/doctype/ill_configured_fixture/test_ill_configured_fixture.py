# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

import json

import frappe
from frappe.tests.utils import FrappeTestCase


class TestilLConfiguredFixture(FrappeTestCase):
	"""Tests for ilL-Configured-Fixture document."""

	def setUp(self):
		"""Set up test data."""
		self.template_code = "TEST-TEMPLATE"
		self.finish_code = "FINISH-01"
		self.lens_appearance_code = "LENS-CLEAR"
		self.mounting_method_code = "MOUNT-SURFACE"
		self.endcap_color_code = "ENDCAP-WHITE"
		self.environment_rating_code = "ENV-DRY"
		self.profile_family = "SH01"  # Use SH01 for realistic part number

		# Ensure basic attributes exist
		self._ensure({"doctype": "ilL-Attribute-Finish", "finish_name": self.finish_code, "code": "WH"})
		self._ensure(
			{"doctype": "ilL-Attribute-Lens Appearance", "label": self.lens_appearance_code, "code": "MC"}
		)
		self._ensure(
			{"doctype": "ilL-Attribute-Mounting Method", "label": self.mounting_method_code, "code": "SV"}
		)
		self._ensure(
			{"doctype": "ilL-Attribute-Endcap Color", "code": self.endcap_color_code, "display_name": "White"}
		)
		self._ensure(
			{"doctype": "ilL-Attribute-Environment Rating", "label": self.environment_rating_code, "code": "I"}
		)

		# Create fixture template
		if not frappe.db.exists("ilL-Fixture-Template", self.template_code):
			frappe.get_doc({
				"doctype": "ilL-Fixture-Template",
				"template_code": self.template_code,
				"template_name": "Test Template",
				"is_active": 1,
				"default_profile_family": self.profile_family,
			}).insert(ignore_permissions=True)

	def _ensure(self, data: dict, ignore_links: bool = False):
		"""Insert a document if it does not already exist and return it."""
		doc = frappe.get_doc(data)
		doc.flags.ignore_links = ignore_links
		doc.insert(ignore_if_duplicate=True, ignore_links=ignore_links)
		return frappe.get_doc(data["doctype"], doc.name)

	def test_part_number_includes_j_suffix_for_multi_segment(self):
		"""Test that multi-segment fixtures have '-J' suffix in part number."""
		# Create a multi-segment fixture
		fixture = frappe.get_doc({
			"doctype": "ilL-Configured-Fixture",
			"fixture_template": self.template_code,
			"is_multi_segment": 1,
			"finish": self.finish_code,
			"lens_appearance": self.lens_appearance_code,
			"mounting_method": self.mounting_method_code,
			"environment_rating": self.environment_rating_code,
			"endcap_color": self.endcap_color_code,
			"requested_overall_length_mm": 3048,  # 120 inches
			"user_segments": [
				{
					"segment_index": 1,
					"requested_length_mm": 1524,  # 60 inches
					"end_type": "Jumper",
					"start_power_feed_type": "END",
				},
				{
					"segment_index": 2,
					"requested_length_mm": 1524,  # 60 inches
					"end_type": "Endcap",
					"start_power_feed_type": "",
				},
			],
		})
		fixture.insert(ignore_permissions=True)

		# Part number should contain "-J" for multi-segment fixtures
		self.assertIn("-J", fixture.name, f"Multi-segment fixture name should contain '-J': {fixture.name}")

		# Clean up
		frappe.delete_doc("ilL-Configured-Fixture", fixture.name, force=True)

	def test_part_number_no_j_suffix_for_single_segment(self):
		"""Test that single-segment fixtures do NOT have '-J' suffix."""
		# Create a single-segment fixture
		fixture = frappe.get_doc({
			"doctype": "ilL-Configured-Fixture",
			"fixture_template": self.template_code,
			"is_multi_segment": 0,
			"finish": self.finish_code,
			"lens_appearance": self.lens_appearance_code,
			"mounting_method": self.mounting_method_code,
			"environment_rating": self.environment_rating_code,
			"endcap_color": self.endcap_color_code,
			"requested_overall_length_mm": 3048,  # 120 inches
		})
		fixture.insert(ignore_permissions=True)

		# Part number should NOT contain "-J" pattern for single-segment fixtures
		# Check that it doesn't contain the multi-segment pattern "-J-" or end with "-J"
		self.assertNotIn("-J-", fixture.name, f"Single-segment fixture name should not contain '-J-': {fixture.name}")
		self.assertFalse(
			fixture.name.endswith("-J"),
			f"Single-segment fixture name should not end with '-J': {fixture.name}"
		)

		# Clean up
		frappe.delete_doc("ilL-Configured-Fixture", fixture.name, force=True)

	def test_different_segment_configs_get_unique_part_numbers(self):
		"""Test that fixtures with same total length but different segment layouts get unique part numbers."""
		# Create fixture with 2 segments of 60" each (total 120")
		fixture_2x60 = frappe.get_doc({
			"doctype": "ilL-Configured-Fixture",
			"fixture_template": self.template_code,
			"is_multi_segment": 1,
			"finish": self.finish_code,
			"lens_appearance": self.lens_appearance_code,
			"mounting_method": self.mounting_method_code,
			"environment_rating": self.environment_rating_code,
			"endcap_color": self.endcap_color_code,
			"requested_overall_length_mm": 3048,  # 120 inches
			"user_segments": [
				{
					"segment_index": 1,
					"requested_length_mm": 1524,  # 60 inches
					"end_type": "Jumper",
					"start_power_feed_type": "END",
				},
				{
					"segment_index": 2,
					"requested_length_mm": 1524,  # 60 inches
					"end_type": "Endcap",
					"start_power_feed_type": "",
				},
			],
		})
		fixture_2x60.insert(ignore_permissions=True)

		# Create fixture with 3 segments of 40" each (total 120")
		fixture_3x40 = frappe.get_doc({
			"doctype": "ilL-Configured-Fixture",
			"fixture_template": self.template_code,
			"is_multi_segment": 1,
			"finish": self.finish_code,
			"lens_appearance": self.lens_appearance_code,
			"mounting_method": self.mounting_method_code,
			"environment_rating": self.environment_rating_code,
			"endcap_color": self.endcap_color_code,
			"requested_overall_length_mm": 3048,  # 120 inches
			"user_segments": [
				{
					"segment_index": 1,
					"requested_length_mm": 1016,  # 40 inches
					"end_type": "Jumper",
					"start_power_feed_type": "END",
				},
				{
					"segment_index": 2,
					"requested_length_mm": 1016,  # 40 inches
					"end_type": "Jumper",
					"start_power_feed_type": "",
				},
				{
					"segment_index": 3,
					"requested_length_mm": 1016,  # 40 inches
					"end_type": "Endcap",
					"start_power_feed_type": "",
				},
			],
		})
		fixture_3x40.insert(ignore_permissions=True)

		# Both should have unique names
		self.assertNotEqual(
			fixture_2x60.name,
			fixture_3x40.name,
			"Different segment configurations with same total length should have unique part numbers"
		)

		# Both should have the "-J" suffix
		self.assertIn("-J", fixture_2x60.name)
		self.assertIn("-J", fixture_3x40.name)

		# Clean up
		frappe.delete_doc("ilL-Configured-Fixture", fixture_2x60.name, force=True)
		frappe.delete_doc("ilL-Configured-Fixture", fixture_3x40.name, force=True)

	def test_config_hash_includes_segments_for_multi_segment(self):
		"""Test that config_hash is different for different segment configurations."""
		# Create fixture with 2 segments
		fixture_2seg = frappe.get_doc({
			"doctype": "ilL-Configured-Fixture",
			"fixture_template": self.template_code,
			"is_multi_segment": 1,
			"finish": self.finish_code,
			"lens_appearance": self.lens_appearance_code,
			"mounting_method": self.mounting_method_code,
			"environment_rating": self.environment_rating_code,
			"endcap_color": self.endcap_color_code,
			"requested_overall_length_mm": 3048,
			"user_segments": [
				{"segment_index": 1, "requested_length_mm": 1524, "end_type": "Jumper"},
				{"segment_index": 2, "requested_length_mm": 1524, "end_type": "Endcap"},
			],
		})
		fixture_2seg.insert(ignore_permissions=True)

		# Create fixture with 3 segments
		fixture_3seg = frappe.get_doc({
			"doctype": "ilL-Configured-Fixture",
			"fixture_template": self.template_code,
			"is_multi_segment": 1,
			"finish": self.finish_code,
			"lens_appearance": self.lens_appearance_code,
			"mounting_method": self.mounting_method_code,
			"environment_rating": self.environment_rating_code,
			"endcap_color": self.endcap_color_code,
			"requested_overall_length_mm": 3048,
			"user_segments": [
				{"segment_index": 1, "requested_length_mm": 1016, "end_type": "Jumper"},
				{"segment_index": 2, "requested_length_mm": 1016, "end_type": "Jumper"},
				{"segment_index": 3, "requested_length_mm": 1016, "end_type": "Endcap"},
			],
		})
		fixture_3seg.insert(ignore_permissions=True)

		# Config hashes should be different
		self.assertNotEqual(
			fixture_2seg.config_hash,
			fixture_3seg.config_hash,
			"Different segment configurations should have different config_hash values"
		)

		# Clean up
		frappe.delete_doc("ilL-Configured-Fixture", fixture_2seg.name, force=True)
		frappe.delete_doc("ilL-Configured-Fixture", fixture_3seg.name, force=True)

	def _ensure_feed_direction(self, direction_name, code):
		"""Helper to ensure a feed direction attribute exists."""
		return self._ensure({
			"doctype": "ilL-Attribute-Feed-Direction",
			"direction_name": direction_name,
			"code": code,
		})

	def test_single_segment_feed_direction_codes(self):
		"""Test that single-segment fixtures populate feed direction SKU codes correctly."""
		self._ensure_feed_direction("End", "E")

		fixture = frappe.get_doc({
			"doctype": "ilL-Configured-Fixture",
			"fixture_template": self.template_code,
			"is_multi_segment": 0,
			"finish": self.finish_code,
			"lens_appearance": self.lens_appearance_code,
			"mounting_method": self.mounting_method_code,
			"environment_rating": self.environment_rating_code,
			"endcap_color": self.endcap_color_code,
			"requested_overall_length_mm": 1524,
			"feed_direction_start": "End",
		})
		fixture.insert(ignore_permissions=True)

		self.assertEqual(fixture.sku_feed_direction_start_code, "E")
		self.assertEqual(fixture.sku_feed_direction_end_code, "C")
		self.assertEqual(fixture.feed_direction_end, "Endcap")

		frappe.delete_doc("ilL-Configured-Fixture", fixture.name, force=True)

	def test_multi_segment_user_segment_feed_direction_codes(self):
		"""Test that multi-segment fixtures auto-populate feed direction codes in user segments."""
		self._ensure_feed_direction("End", "E")
		self._ensure_feed_direction("Back", "B")

		fixture = frappe.get_doc({
			"doctype": "ilL-Configured-Fixture",
			"fixture_template": self.template_code,
			"is_multi_segment": 1,
			"finish": self.finish_code,
			"lens_appearance": self.lens_appearance_code,
			"mounting_method": self.mounting_method_code,
			"environment_rating": self.environment_rating_code,
			"endcap_color": self.endcap_color_code,
			"requested_overall_length_mm": 3048,
			"user_segments": [
				{
					"segment_index": 1,
					"requested_length_mm": 1524,
					"end_type": "Jumper",
					"start_feed_direction": "End",
					"end_feed_direction": "Back",
				},
				{
					"segment_index": 2,
					"requested_length_mm": 1524,
					"end_type": "Endcap",
					"start_feed_direction": "Back",
				},
			],
		})
		fixture.insert(ignore_permissions=True)

		# Verify segment 1 codes
		self.assertEqual(fixture.user_segments[0].start_feed_direction_code, "E")
		self.assertEqual(fixture.user_segments[0].end_feed_direction_code, "B")

		# Verify segment 2 codes (end is Endcap, so end_feed_direction_code should be empty)
		self.assertEqual(fixture.user_segments[1].start_feed_direction_code, "B")
		self.assertEqual(fixture.user_segments[1].end_feed_direction_code, "")

		frappe.delete_doc("ilL-Configured-Fixture", fixture.name, force=True)

	def test_multi_segment_endcap_end_clears_feed_direction_code(self):
		"""Test that end_feed_direction_code is cleared when end_type is Endcap."""
		self._ensure_feed_direction("Left", "L")

		fixture = frappe.get_doc({
			"doctype": "ilL-Configured-Fixture",
			"fixture_template": self.template_code,
			"is_multi_segment": 1,
			"finish": self.finish_code,
			"lens_appearance": self.lens_appearance_code,
			"mounting_method": self.mounting_method_code,
			"environment_rating": self.environment_rating_code,
			"endcap_color": self.endcap_color_code,
			"requested_overall_length_mm": 1524,
			"user_segments": [
				{
					"segment_index": 1,
					"requested_length_mm": 1524,
					"end_type": "Endcap",
					"start_feed_direction": "Left",
					"end_feed_direction": "Left",
				},
			],
		})
		fixture.insert(ignore_permissions=True)

		# start should be populated, end should be cleared because end_type is Endcap
		self.assertEqual(fixture.user_segments[0].start_feed_direction_code, "L")
		self.assertEqual(fixture.user_segments[0].end_feed_direction_code, "")

		frappe.delete_doc("ilL-Configured-Fixture", fixture.name, force=True)

	def tearDown(self):
		"""Clean up test data."""
		# Delete any test fixtures
		test_fixtures = frappe.get_all(
			"ilL-Configured-Fixture",
			filters={"fixture_template": self.template_code},
			pluck="name"
		)
		for fixture_name in test_fixtures:
			try:
				frappe.delete_doc("ilL-Configured-Fixture", fixture_name, force=True)
			except Exception:
				pass
