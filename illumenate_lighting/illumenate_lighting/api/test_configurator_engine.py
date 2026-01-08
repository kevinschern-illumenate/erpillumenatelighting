# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Tests for Configurator Engine API
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase


class TestConfiguratorEngine(FrappeTestCase):
	"""Test cases for the configurator engine API"""

	def setUp(self):
		"""Set up test data"""
		# Create a test fixture template if it doesn't exist
		if not frappe.db.exists("ilL-Fixture-Template", "TEST-TEMPLATE"):
			template = frappe.get_doc(
				{
					"doctype": "ilL-Fixture-Template",
					"name": "TEST-TEMPLATE",
				}
			)
			template.insert(ignore_if_duplicate=True)

	def test_validate_and_quote_basic(self):
		"""Test basic validate_and_quote functionality"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Test with valid inputs
		result = validate_and_quote(
			fixture_template_code="TEST-TEMPLATE",
			finish_code="FINISH-01",
			lens_appearance_code="LENS-CLEAR",
			mounting_method_code="MOUNT-SURFACE",
			endcap_style_code="ENDCAP-FLAT",
			endcap_color_code="ENDCAP-WHITE",
			power_feed_type_code="POWER-WIRE",
			environment_rating_code="ENV-DRY",
			tape_offering_id="TAPE-001",
			requested_overall_length_mm=1000,
			qty=1,
		)

		# Check response structure
		self.assertIn("is_valid", result)
		self.assertIn("messages", result)
		self.assertIn("computed", result)
		self.assertIn("resolved_items", result)
		self.assertIn("pricing", result)
		self.assertIn("configured_fixture_id", result)

		# Check that validation passed
		self.assertTrue(result["is_valid"])

		# Check computed fields exist
		computed = result["computed"]
		self.assertIn("endcap_allowance_mm_per_side", computed)
		self.assertIn("leader_allowance_mm_per_fixture", computed)
		self.assertIn("internal_length_mm", computed)
		self.assertIn("tape_cut_length_mm", computed)
		self.assertIn("manufacturable_overall_length_mm", computed)
		self.assertIn("difference_mm", computed)
		self.assertIn("segments", computed)
		self.assertIn("runs", computed)
		self.assertIn("runs_count", computed)
		self.assertIn("total_watts", computed)
		self.assertIn("assembly_mode", computed)

		# Check resolved items
		resolved = result["resolved_items"]
		self.assertIn("profile_item", resolved)
		self.assertIn("lens_item", resolved)
		self.assertIn("endcap_item", resolved)
		self.assertIn("mounting_item", resolved)
		self.assertIn("leader_item", resolved)
		self.assertIn("driver_plan", resolved)

		# Check pricing
		pricing = result["pricing"]
		self.assertIn("msrp_unit", pricing)
		self.assertIn("tier_unit", pricing)
		self.assertIn("adder_breakdown", pricing)
		self.assertIsInstance(pricing["adder_breakdown"], list)

		# Check that a configured fixture was created
		self.assertIsNotNone(result["configured_fixture_id"])

	def test_validate_and_quote_missing_template(self):
		"""Test validation with non-existent fixture template"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		result = validate_and_quote(
			fixture_template_code="NON-EXISTENT",
			finish_code="FINISH-01",
			lens_appearance_code="LENS-CLEAR",
			mounting_method_code="MOUNT-SURFACE",
			endcap_style_code="ENDCAP-FLAT",
			endcap_color_code="ENDCAP-WHITE",
			power_feed_type_code="POWER-WIRE",
			environment_rating_code="ENV-DRY",
			tape_offering_id="TAPE-001",
			requested_overall_length_mm=1000,
			qty=1,
		)

		# Should fail validation
		self.assertFalse(result["is_valid"])
		self.assertTrue(len(result["messages"]) > 0)

		# Check error message
		error_messages = [msg for msg in result["messages"] if msg["severity"] == "error"]
		self.assertTrue(len(error_messages) > 0)
		self.assertIn("not found", error_messages[0]["text"].lower())

	def test_validate_and_quote_invalid_length(self):
		"""Test validation with invalid length"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		result = validate_and_quote(
			fixture_template_code="TEST-TEMPLATE",
			finish_code="FINISH-01",
			lens_appearance_code="LENS-CLEAR",
			mounting_method_code="MOUNT-SURFACE",
			endcap_style_code="ENDCAP-FLAT",
			endcap_color_code="ENDCAP-WHITE",
			power_feed_type_code="POWER-WIRE",
			environment_rating_code="ENV-DRY",
			tape_offering_id="TAPE-001",
			requested_overall_length_mm=0,
			qty=1,
		)

		# Should fail validation
		self.assertFalse(result["is_valid"])

		# Check error message about length
		error_messages = [msg for msg in result["messages"] if msg["severity"] == "error"]
		self.assertTrue(len(error_messages) > 0)
		length_errors = [msg for msg in error_messages if "length" in msg["text"].lower()]
		self.assertTrue(len(length_errors) > 0)

	def test_validate_and_quote_missing_required_field(self):
		"""Test validation with missing required field"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		result = validate_and_quote(
			fixture_template_code="TEST-TEMPLATE",
			finish_code="",  # Missing
			lens_appearance_code="LENS-CLEAR",
			mounting_method_code="MOUNT-SURFACE",
			endcap_style_code="ENDCAP-FLAT",
			endcap_color_code="ENDCAP-WHITE",
			power_feed_type_code="POWER-WIRE",
			environment_rating_code="ENV-DRY",
			tape_offering_id="TAPE-001",
			requested_overall_length_mm=1000,
			qty=1,
		)

		# Should fail validation
		self.assertFalse(result["is_valid"])

		# Check error message about required field
		error_messages = [msg for msg in result["messages"] if msg["severity"] == "error"]
		self.assertTrue(len(error_messages) > 0)
		finish_errors = [msg for msg in error_messages if "finish_code" in msg.get("field", "")]
		self.assertTrue(len(finish_errors) > 0)

	def test_configured_fixture_reuse(self):
		"""Test that identical configurations reuse the same document"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Create first configuration
		result1 = validate_and_quote(
			fixture_template_code="TEST-TEMPLATE",
			finish_code="FINISH-01",
			lens_appearance_code="LENS-CLEAR",
			mounting_method_code="MOUNT-SURFACE",
			endcap_style_code="ENDCAP-FLAT",
			endcap_color_code="ENDCAP-WHITE",
			power_feed_type_code="POWER-WIRE",
			environment_rating_code="ENV-DRY",
			tape_offering_id="TAPE-001",
			requested_overall_length_mm=1000,
			qty=1,
		)

		# Create second identical configuration
		result2 = validate_and_quote(
			fixture_template_code="TEST-TEMPLATE",
			finish_code="FINISH-01",
			lens_appearance_code="LENS-CLEAR",
			mounting_method_code="MOUNT-SURFACE",
			endcap_style_code="ENDCAP-FLAT",
			endcap_color_code="ENDCAP-WHITE",
			power_feed_type_code="POWER-WIRE",
			environment_rating_code="ENV-DRY",
			tape_offering_id="TAPE-001",
			requested_overall_length_mm=1000,
			qty=1,
		)

		# Should reuse the same configured fixture
		self.assertEqual(result1["configured_fixture_id"], result2["configured_fixture_id"])

	def test_response_schema_completeness(self):
		"""Test that response contains all required schema fields"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		result = validate_and_quote(
			fixture_template_code="TEST-TEMPLATE",
			finish_code="FINISH-01",
			lens_appearance_code="LENS-CLEAR",
			mounting_method_code="MOUNT-SURFACE",
			endcap_style_code="ENDCAP-FLAT",
			endcap_color_code="ENDCAP-WHITE",
			power_feed_type_code="POWER-WIRE",
			environment_rating_code="ENV-DRY",
			tape_offering_id="TAPE-001",
			requested_overall_length_mm=1000,
			qty=1,
		)

		# Verify all top-level fields
		required_top_level = [
			"is_valid",
			"messages",
			"computed",
			"resolved_items",
			"pricing",
			"configured_fixture_id",
		]
		for field in required_top_level:
			self.assertIn(field, result, f"Missing top-level field: {field}")

		# Verify computed fields
		required_computed = [
			"endcap_allowance_mm_per_side",
			"leader_allowance_mm_per_fixture",
			"internal_length_mm",
			"tape_cut_length_mm",
			"manufacturable_overall_length_mm",
			"difference_mm",
			"segments",
			"runs",
			"runs_count",
			"total_watts",
			"assembly_mode",
		]
		for field in required_computed:
			self.assertIn(field, result["computed"], f"Missing computed field: {field}")

		# Verify resolved_items fields
		required_resolved = [
			"profile_item",
			"lens_item",
			"endcap_item",
			"mounting_item",
			"leader_item",
			"driver_plan",
		]
		for field in required_resolved:
			self.assertIn(field, result["resolved_items"], f"Missing resolved_items field: {field}")

		# Verify pricing fields
		required_pricing = ["msrp_unit", "tier_unit", "adder_breakdown"]
		for field in required_pricing:
			self.assertIn(field, result["pricing"], f"Missing pricing field: {field}")

	def tearDown(self):
		"""Clean up test data"""
		# Clean up any test configured fixtures
		frappe.db.delete("ilL-Configured-Fixture", {"fixture_template": "TEST-TEMPLATE"})
		frappe.db.commit()
