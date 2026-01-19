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
		self.template_code = "TEST-TEMPLATE"
		self.finish_code = "FINISH-01"
		self.lens_appearance_code = "LENS-CLEAR"
		self.mounting_method_code = "MOUNT-SURFACE"
		self.endcap_style_code = "ENDCAP-FLAT"
		self.endcap_color_code = "ENDCAP-WHITE"
		self.power_feed_type_code = "POWER-WIRE"
		self.environment_rating_code = "ENV-DRY"
		self.profile_family = "PFAM-TEST"
		self.lens_interface_code = "LENS-IFACE"
		self.output_voltage_code = "24V"
		self.cct_code = "CCT-3000K"
		self.cri_code = "CRI-90"
		self.sdcm_code = "SDCM-2"
		self.led_package_code = "LP-1"
		self.output_level_code = "OP-1"

		self._ensure({"doctype": "ilL-Attribute-Finish", "finish_name": self.finish_code, "code": self.finish_code})
		self._ensure(
			{"doctype": "ilL-Attribute-Lens Appearance", "label": self.lens_appearance_code, "code": self.lens_appearance_code}
		)
		self._ensure(
			{"doctype": "ilL-Attribute-Mounting Method", "label": self.mounting_method_code, "code": self.mounting_method_code}
		)
		self._ensure({
			"doctype": "ilL-Attribute-Endcap Style",
			"label": self.endcap_style_code,
			"code": self.endcap_style_code,
			"allowance_mm_per_side": 15,  # Epic 3 Task 3.1: E = endcap_style.allowance_mm_per_side
		})
		self._ensure(
			{"doctype": "ilL-Attribute-Endcap Color", "code": self.endcap_color_code, "display_name": self.endcap_color_code}
		)
		self._ensure(
			{"doctype": "ilL-Attribute-Power Feed Type", "label": self.power_feed_type_code, "code": self.power_feed_type_code}
		)
		self._ensure(
			{"doctype": "ilL-Attribute-Environment Rating", "label": self.environment_rating_code, "code": self.environment_rating_code}
		)
		self._ensure(
			{"doctype": "ilL-Attribute-Lens Interface Type", "label": self.lens_interface_code, "code": self.lens_interface_code, "is_active": 1}
		)
		self._ensure(
			{"doctype": "ilL-Attribute-Output Voltage", "output_voltage_name": self.output_voltage_code, "code": self.output_voltage_code}
		)
		self._ensure({"doctype": "ilL-Attribute-CCT", "cct_name": self.cct_code, "code": self.cct_code, "kelvin": 3000})
		self._ensure({"doctype": "ilL-Attribute-CRI", "cri_name": self.cri_code, "code": self.cri_code})
		self._ensure({"doctype": "ilL-Attribute-SDCM", "sdcm_name": self.sdcm_code, "code": self.sdcm_code, "value": 2})
		self._ensure(
			{"doctype": "ilL-Attribute-LED Package", "package_name": self.led_package_code, "code": self.led_package_code}
		)
		self._ensure(
			{
				"doctype": "ilL-Attribute-Output Level",
				"output_level_name": self.output_level_code,
				"value": 1,
				"sku_code": self.output_level_code,
			}
		)

		self.profile_spec = self._ensure(
			{
				"doctype": "ilL-Spec-Profile",
				"item": "PROFILE-ITEM-01",
				"family": self.profile_family,
				"variant_code": self.finish_code,
				"is_active": 1,
				"lens_interface": self.lens_interface_code,
				"stock_length_mm": 2000,  # Epic 3 Task 3.2: profile_stock_len_mm
			}
		)

		self.lens_spec = self._ensure(
			{
				"doctype": "ilL-Spec-Lens",
				"item": "LENS-ITEM-01",
				"family": "LENS-FAMILY",
				"lens_appearance": self.lens_appearance_code,
				"supported_environment_ratings": [{"environment_rating": self.environment_rating_code}],
			}
		)

		self.tape_spec = self._ensure(
			{
				"doctype": "ilL-Spec-LED Tape",
				"item": "TAPE-SPEC-01",
				"input_voltage": self.output_voltage_code,
				"watts_per_foot": 5,
				"cut_increment_mm": 50,
				"voltage_drop_max_run_length_ft": 16,  # Epic 3 Task 3.3: voltage drop limit
			}
		)

		self.tape_offering_id = (
			f"{self.tape_spec.name}-{self.cct_code}-{self.cri_code}-{self.sdcm_code}-{self.led_package_code}-{self.output_level_code}"
		)
		self.tape_offering = self._ensure(
			{
				"doctype": "ilL-Rel-Tape Offering",
				"name": self.tape_offering_id,
				"tape_spec": self.tape_spec.name,
				"cct": self.cct_code,
				"cri": self.cri_code,
				"sdcm": self.sdcm_code,
				"led_package": self.led_package_code,
				"output_level": self.output_level_code,
				"is_active": 1,
			}
		)

		template_allowed_options = [
			{
				"doctype": "ilL-Child-Template-Allowed-Option",
				"option_type": "Finish",
				"finish": self.finish_code,
				"is_active": 1,
				"is_default": 1,
				"msrp_adder": 25.0,  # Epic 4: Pricing adder for finish option
			},
			{
				"doctype": "ilL-Child-Template-Allowed-Option",
				"option_type": "Lens Appearance",
				"lens_appearance": self.lens_appearance_code,
				"is_active": 1,
				"msrp_adder": 15.0,  # Epic 4: Pricing adder for lens option
			},
			{
				"doctype": "ilL-Child-Template-Allowed-Option",
				"option_type": "Mounting Method",
				"mounting_method": self.mounting_method_code,
				"is_active": 1,
				"msrp_adder": 10.0,  # Epic 4: Pricing adder for mounting option
			},
			{
				"doctype": "ilL-Child-Template-Allowed-Option",
				"option_type": "Endcap Style",
				"endcap_style": self.endcap_style_code,
				"is_active": 1,
				"msrp_adder": 5.0,  # Epic 4: Pricing adder for endcap style option
			},
			{
				"doctype": "ilL-Child-Template-Allowed-Option",
				"option_type": "Power Feed Type",
				"power_feed_type": self.power_feed_type_code,
				"is_active": 1,
				"msrp_adder": 0.0,  # No adder for power feed type
			},
			{
				"doctype": "ilL-Child-Template-Allowed-Option",
				"option_type": "Environment Rating",
				"environment_rating": self.environment_rating_code,
				"is_active": 1,
				"msrp_adder": 0.0,  # No adder for environment rating
			},
		]

		template_allowed_tapes = [
			{
				"doctype": "ilL-Child-Template-Allowed-TapeOffering",
				"tape_offering": self.tape_offering.name,
				"environment_rating": self.environment_rating_code,
			}
		]

		if frappe.db.exists("ilL-Fixture-Template", self.template_code):
			self.template = frappe.get_doc("ilL-Fixture-Template", self.template_code)
			self.template.template_name = "Test Template"
			self.template.is_active = 1
			self.template.default_profile_family = self.profile_family
			# Epic 3 Task 3.1, 3.2, 3.4 fields
			self.template.default_profile_stock_len_mm = 2000
			self.template.leader_allowance_mm_per_fixture = 15
			self.template.assembled_max_len_mm = 2590  # ~8.5ft
			# Epic 4: Pricing fields
			self.template.base_price_msrp = 100.0  # Base price
			self.template.price_per_ft_msrp = 10.0  # $10 per foot
			self.template.pricing_length_basis = "L_tape_cut"  # Use tape cut length for pricing
			self.template.allowed_options = template_allowed_options
			self.template.allowed_tape_offerings = template_allowed_tapes
			self.template.save()
		else:
			self.template = self._ensure(
				{
					"doctype": "ilL-Fixture-Template",
					"template_code": self.template_code,
					"template_name": "Test Template",
					"is_active": 1,
					"default_profile_family": self.profile_family,
					# Epic 3 Task 3.1, 3.2, 3.4 fields
					"default_profile_stock_len_mm": 2000,
					"leader_allowance_mm_per_fixture": 15,
					"assembled_max_len_mm": 2590,  # ~8.5ft
					# Epic 4: Pricing fields
					"base_price_msrp": 100.0,  # Base price
					"price_per_ft_msrp": 10.0,  # $10 per foot
					"pricing_length_basis": "L_tape_cut",  # Use tape cut length for pricing
					"allowed_options": template_allowed_options,
					"allowed_tape_offerings": template_allowed_tapes,
				}
			)

		self._ensure(
			{
				"doctype": "ilL-Rel-Endcap-Map",
				"fixture_template": self.template_code,
				"endcap_style": self.endcap_style_code,
				"endcap_color": self.endcap_color_code,
				"power_feed_type": self.power_feed_type_code,
				"environment_rating": self.environment_rating_code,
				"endcap_item": "ENDCAP-ITEM-01",
				"is_active": 1,
			},
			ignore_links=True,
		)

		self._ensure(
			{
				"doctype": "ilL-Rel-Mounting-Accessory-Map",
				"fixture_template": self.template_code,
				"mounting_method": self.mounting_method_code,
				"environment_rating": self.environment_rating_code,
				"accessory_item": "MOUNT-ITEM-01",
				"qty_rule_type": "PER_FIXTURE",
				"qty_rule_value": 1,
				"min_qty": 0,
				"is_active": 1,
			},
			ignore_links=True,
		)

		self._ensure(
			{
				"doctype": "ilL-Rel-Leader-Cable-Map",
				"tape_spec": self.tape_spec.name,
				"power_feed_type": self.power_feed_type_code,
				"environment_rating": self.environment_rating_code,
				"leader_item": "LEADER-ITEM-01",
				"default_length_mm": 150,
				"is_active": 1,
			},
			ignore_links=True,
		)

	def _ensure(self, data: dict, ignore_links: bool = False):
		"""Insert a document if it does not already exist and return it."""
		doc = frappe.get_doc(data)
		doc.flags.ignore_links = ignore_links
		doc.insert(ignore_if_duplicate=True, ignore_links=ignore_links)
		doc = frappe.get_doc(data["doctype"], doc.name)

		updated = False
		for key, value in data.items():
			if key in {"doctype", "name"}:
				continue
			if value is not None and doc.get(key) != value:
				doc.set(key, value)
				updated = True

		if updated:
			doc.flags.ignore_links = ignore_links
			doc.save()

		return doc

	def test_validate_and_quote_basic(self):
		"""Test basic validate_and_quote functionality"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Test with valid inputs
		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
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
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
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
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
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
			fixture_template_code=self.template_code,
			finish_code="",  # Missing
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
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
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		# Create second identical configuration
		result2 = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		# Should reuse the same configured fixture
		self.assertEqual(result1["configured_fixture_id"], result2["configured_fixture_id"])

	def test_disallowed_option_blocks(self):
		"""Ensure invalid option returns a blocking message"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code="UNALLOWED",
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertFalse(result["is_valid"])
		error_fields = {msg.get("field") for msg in result["messages"] if msg["severity"] == "error"}
		self.assertIn("finish_code", error_fields)

	def test_missing_mapping_returns_error(self):
		"""Engine should fail fast when a mapping row is missing"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		leader_maps = frappe.get_all(
			"ilL-Rel-Leader-Cable-Map", filters={"tape_spec": self.tape_spec.name}, pluck="name"
		) or []
		for row in leader_maps:
			if not row:
				continue
			try:
				if frappe.db.exists("ilL-Rel-Leader-Cable-Map", {"name": row}):
					frappe.delete_doc("ilL-Rel-Leader-Cable-Map", row, force=True)
			except Exception:
				continue

		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertFalse(result["is_valid"])
		error_texts = [msg["text"] for msg in result["messages"] if msg["severity"] == "error"]
		self.assertTrue(any("Leader-Cable-Map" in text for text in error_texts))

	def test_response_schema_completeness(self):
		"""Test that response contains all required schema fields"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
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

		# Verify computed fields (Epic 3 computation layer)
		required_computed = [
			# Task 3.1: Length Math
			"endcap_allowance_mm_per_side",
			"leader_allowance_mm_per_fixture",
			"internal_length_mm",
			"tape_cut_length_mm",
			"manufacturable_overall_length_mm",
			"difference_mm",
			"requested_overall_length_mm",
			# Task 3.2: Segmentation Plan
			"segments_count",
			"profile_stock_len_mm",
			"segments",
			# Task 3.3: Run Splitting
			"runs_count",
			"leader_qty",
			"total_watts",
			"max_run_ft_by_watts",
			"max_run_ft_by_voltage_drop",
			"max_run_ft_effective",
			"runs",
			# Task 3.4: Assembly Mode
			"assembly_mode",
			"assembled_max_len_mm",
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

	def test_length_math_task_3_1(self):
		"""Test Epic 3 Task 3.1: Length math (locked rules)"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# L_req = 1000mm, E = 15mm, A_leader = 15mm, cut_increment = 50mm
		# L_internal = 1000 - 2*15 - 15 = 955mm
		# L_tape_cut = floor(955 / 50) * 50 = 950mm
		# L_mfg = 950 + 2*15 + 15 = 995mm
		# difference = 1000 - 995 = 5mm
		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		computed = result["computed"]

		# Verify length math calculations
		self.assertEqual(computed["endcap_allowance_mm_per_side"], 15.0)
		self.assertEqual(computed["leader_allowance_mm_per_fixture"], 15.0)
		self.assertEqual(computed["internal_length_mm"], 955)  # 1000 - 2*15 - 15
		self.assertEqual(computed["tape_cut_length_mm"], 950)  # floor(955/50)*50
		self.assertEqual(computed["manufacturable_overall_length_mm"], 995)  # 950 + 2*15 + 15
		self.assertEqual(computed["difference_mm"], 5)  # 1000 - 995
		self.assertEqual(computed["requested_overall_length_mm"], 1000)

	def test_segmentation_plan_task_3_2(self):
		"""Test Epic 3 Task 3.2: Segmentation plan (profile + lens)"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Test with a length that requires multiple segments
		# profile_stock_len_mm = 2000mm, L_mfg = 4995mm -> 3 segments
		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=5000,  # Large fixture
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		computed = result["computed"]

		# Verify segmentation
		self.assertEqual(computed["profile_stock_len_mm"], 2000)
		self.assertGreater(computed["segments_count"], 1)
		self.assertEqual(len(computed["segments"]), computed["segments_count"])

		# Verify segment structure
		for segment in computed["segments"]:
			self.assertIn("segment_index", segment)
			self.assertIn("profile_cut_len_mm", segment)
			self.assertIn("lens_cut_len_mm", segment)
			self.assertIn("notes", segment)

	def test_run_splitting_task_3_3(self):
		"""Test Epic 3 Task 3.3: Run splitting (min of voltage-drop max length and 85W limit)"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		computed = result["computed"]

		# Verify run metadata is present
		# watts_per_ft = 5, so max_run_ft_by_watts = 85/5 = 17ft
		# voltage_drop_max_run_length_ft = 16ft
		# max_run_ft_effective = min(17, 16) = 16ft
		self.assertEqual(computed["max_run_ft_by_watts"], 17.0)
		self.assertEqual(computed["max_run_ft_by_voltage_drop"], 16.0)
		self.assertEqual(computed["max_run_ft_effective"], 16.0)

		# Verify runs and leader_qty
		self.assertGreater(computed["runs_count"], 0)
		self.assertEqual(computed["leader_qty"], computed["runs_count"])
		self.assertEqual(len(computed["runs"]), computed["runs_count"])

		# Verify run structure
		for run in computed["runs"]:
			self.assertIn("run_index", run)
			self.assertIn("run_len_mm", run)
			self.assertIn("run_watts", run)
			self.assertIn("leader_len_mm", run)

	def test_assembly_mode_task_3_4(self):
		"""Test Epic 3 Task 3.4: Assembly mode rule"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Test ASSEMBLED mode (L_mfg <= assembled_max_len_mm)
		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,  # Small fixture
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		computed = result["computed"]
		self.assertEqual(computed["assembled_max_len_mm"], 2590)
		self.assertEqual(computed["assembly_mode"], "ASSEMBLED")

		# Test SHIP_PIECES mode (L_mfg > assembled_max_len_mm)
		result_long = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=5000,  # Large fixture > 2590mm
			qty=1,
		)

		self.assertTrue(result_long["is_valid"])
		computed_long = result_long["computed"]
		self.assertEqual(computed_long["assembly_mode"], "SHIP_PIECES")

	def test_pricing_formula_task_4_1(self):
		"""Test Epic 4 Task 4.1: Baseline pricing formula"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Test with a known length to verify pricing calculation
		# L_req = 1000mm, E = 15mm, A_leader = 15mm, cut_increment = 50mm
		# L_internal = 1000 - 2*15 - 15 = 955mm
		# L_tape_cut = floor(955 / 50) * 50 = 950mm
		# L_tape_cut in feet = 950 / 304.8 = 3.117 ft
		#
		# Pricing:
		# - base_price_msrp = $100
		# - price_per_ft_msrp = $10/ft
		# - length_adder = 3.117 * $10 = $31.17 (rounded)
		# - finish_adder = $25
		# - lens_adder = $15
		# - mounting_adder = $10
		# - endcap_style_adder = $5
		# - power_feed_type_adder = $0
		# - environment_rating_adder = $0
		# Total MSRP = 100 + 31.17 + 25 + 15 + 10 + 5 = $186.17 (approximately)

		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		pricing = result["pricing"]

		# Verify pricing structure
		self.assertIn("msrp_unit", pricing)
		self.assertIn("tier_unit", pricing)
		self.assertIn("adder_breakdown", pricing)

		# Verify msrp_unit is a positive number
		self.assertGreater(pricing["msrp_unit"], 0)

		# Verify tier_unit equals msrp_unit (placeholder: MSRP only)
		self.assertEqual(pricing["tier_unit"], pricing["msrp_unit"])

		# Verify adder_breakdown is a list with at least base and length components
		self.assertIsInstance(pricing["adder_breakdown"], list)
		self.assertGreaterEqual(len(pricing["adder_breakdown"]), 2)

		# Check for required components in adder_breakdown
		components = {item["component"] for item in pricing["adder_breakdown"]}
		self.assertIn("base", components)
		self.assertIn("length", components)

		# Verify base price is correct
		base_adder = next(item for item in pricing["adder_breakdown"] if item["component"] == "base")
		self.assertEqual(base_adder["amount"], 100.0)

		# Verify length adder calculation
		# L_tape_cut = 950mm = 3.117 ft, price_per_ft = $10
		# length_adder = 3.117 * 10 = 31.17 (approximately)
		length_adder = next(item for item in pricing["adder_breakdown"] if item["component"] == "length")
		self.assertGreater(length_adder["amount"], 30)
		self.assertLess(length_adder["amount"], 35)
		self.assertIn("L_tape_cut", length_adder["description"])

		# Verify option adders are included
		self.assertIn("finish", components)
		finish_adder = next(item for item in pricing["adder_breakdown"] if item["component"] == "finish")
		self.assertEqual(finish_adder["amount"], 25.0)

	def test_pricing_snapshot_storage_task_4_2(self):
		"""Test Epic 4 Task 4.2: Store pricing snapshot into ilL-Configured-Fixture"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		self.assertIsNotNone(result["configured_fixture_id"])

		# Fetch the configured fixture and verify pricing snapshot
		fixture_doc = frappe.get_doc("ilL-Configured-Fixture", result["configured_fixture_id"])

		# Verify pricing_snapshot child table exists and has data
		self.assertGreaterEqual(len(fixture_doc.pricing_snapshot), 1)

		# Check the latest pricing snapshot
		latest_snapshot = fixture_doc.pricing_snapshot[-1]
		self.assertIsNotNone(latest_snapshot.msrp_unit)
		self.assertIsNotNone(latest_snapshot.tier_unit)
		self.assertIsNotNone(latest_snapshot.adder_breakdown_json)
		self.assertIsNotNone(latest_snapshot.timestamp)

		# Verify the breakdown JSON is valid
		breakdown = json.loads(latest_snapshot.adder_breakdown_json)
		self.assertIsInstance(breakdown, list)
		self.assertGreaterEqual(len(breakdown), 2)

		# Verify msrp_unit matches the API response
		self.assertEqual(float(latest_snapshot.msrp_unit), result["pricing"]["msrp_unit"])
		self.assertEqual(float(latest_snapshot.tier_unit), result["pricing"]["tier_unit"])

	def test_driver_selection_single_driver_sufficient(self):
		"""Test Epic 5 Task 5.1: Driver selection when single driver satisfies constraints"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Create a driver spec with sufficient capacity
		driver_item_code = "TEST-DRIVER-01"
		self._ensure(
			{
				"doctype": "ilL-Spec-Driver",
				"item": driver_item_code,
				"voltage_output": self.output_voltage_code,
				"outputs_count": 4,
				"max_wattage": 100.0,
				"usable_load_factor": 0.8,  # W_usable = 80W
				"dimming_protocol": None,  # No dimming protocol filter
				"cost": 50.0,  # Has cost for selection policy
			},
			ignore_links=True,
		)

		# Create driver eligibility mapping
		self._ensure(
			{
				"doctype": "ilL-Rel-Driver-Eligibility",
				"fixture_template": self.template_code,
				"driver_spec": driver_item_code,
				"is_allowed": 1,
				"is_active": 1,
				"priority": 0,
			},
			ignore_links=True,
		)

		# Test with a small fixture (1 run, low wattage)
		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertTrue(result["is_valid"])

		# Verify driver plan in resolved_items
		driver_plan = result["resolved_items"]["driver_plan"]
		self.assertEqual(driver_plan["status"], "selected")
		self.assertEqual(len(driver_plan["drivers"]), 1)

		driver_alloc = driver_plan["drivers"][0]
		self.assertEqual(driver_alloc["item_code"], driver_item_code)
		self.assertEqual(driver_alloc["qty"], 1)  # Single driver should be sufficient
		self.assertIn("mapping_notes", driver_alloc)

	def test_driver_selection_multiple_drivers_needed(self):
		"""Test Epic 5 Task 5.1: Driver selection when multiple drivers are needed"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Create a driver spec with limited capacity (1 output, 50W usable)
		driver_item_code = "TEST-DRIVER-02"
		self._ensure(
			{
				"doctype": "ilL-Spec-Driver",
				"item": driver_item_code,
				"voltage_output": self.output_voltage_code,
				"outputs_count": 1,  # Only 1 output
				"max_wattage": 62.5,
				"usable_load_factor": 0.8,  # W_usable = 50W
				"dimming_protocol": None,
				"cost": 30.0,
			},
			ignore_links=True,
		)

		# Create driver eligibility mapping
		self._ensure(
			{
				"doctype": "ilL-Rel-Driver-Eligibility",
				"fixture_template": self.template_code,
				"driver_spec": driver_item_code,
				"is_allowed": 1,
				"is_active": 1,
				"priority": 0,
			},
			ignore_links=True,
		)

		# Test with a large fixture that requires multiple runs
		# L_req = 10000mm should produce multiple runs (> 1 run)
		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=10000,
			qty=1,
		)

		self.assertTrue(result["is_valid"])

		# Verify driver plan requires multiple drivers (due to multiple runs)
		driver_plan = result["resolved_items"]["driver_plan"]
		self.assertEqual(driver_plan["status"], "selected")
		self.assertEqual(len(driver_plan["drivers"]), 1)

		driver_alloc = driver_plan["drivers"][0]
		self.assertEqual(driver_alloc["item_code"], driver_item_code)
		# Should need multiple drivers since only 1 output per driver
		self.assertGreater(driver_alloc["qty"], 1)

	def test_driver_selection_no_eligible_drivers(self):
		"""Test Epic 5 Task 5.1: Warning when no eligible drivers configured"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Create a new template without any driver eligibility
		no_driver_template = "TEST-NO-DRIVER-TEMPLATE"

		template_allowed_options = [
			{
				"doctype": "ilL-Child-Template-Allowed-Option",
				"option_type": "Finish",
				"finish": self.finish_code,
				"is_active": 1,
				"is_default": 1,
			},
			{
				"doctype": "ilL-Child-Template-Allowed-Option",
				"option_type": "Lens Appearance",
				"lens_appearance": self.lens_appearance_code,
				"is_active": 1,
			},
			{
				"doctype": "ilL-Child-Template-Allowed-Option",
				"option_type": "Mounting Method",
				"mounting_method": self.mounting_method_code,
				"is_active": 1,
			},
			{
				"doctype": "ilL-Child-Template-Allowed-Option",
				"option_type": "Endcap Style",
				"endcap_style": self.endcap_style_code,
				"is_active": 1,
			},
			{
				"doctype": "ilL-Child-Template-Allowed-Option",
				"option_type": "Power Feed Type",
				"power_feed_type": self.power_feed_type_code,
				"is_active": 1,
			},
			{
				"doctype": "ilL-Child-Template-Allowed-Option",
				"option_type": "Environment Rating",
				"environment_rating": self.environment_rating_code,
				"is_active": 1,
			},
		]

		template_allowed_tapes = [
			{
				"doctype": "ilL-Child-Template-Allowed-TapeOffering",
				"tape_offering": self.tape_offering.name,
				"environment_rating": self.environment_rating_code,
			}
		]

		self._ensure(
			{
				"doctype": "ilL-Fixture-Template",
				"template_code": no_driver_template,
				"template_name": "Test No Driver Template",
				"is_active": 1,
				"default_profile_family": self.profile_family,
				"default_profile_stock_len_mm": 2000,
				"leader_allowance_mm_per_fixture": 15,
				"assembled_max_len_mm": 2590,
				"base_price_msrp": 100.0,
				"price_per_ft_msrp": 10.0,
				"pricing_length_basis": "L_tape_cut",
				"allowed_options": template_allowed_options,
				"allowed_tape_offerings": template_allowed_tapes,
			}
		)

		# Create endcap map for this template
		self._ensure(
			{
				"doctype": "ilL-Rel-Endcap-Map",
				"fixture_template": no_driver_template,
				"endcap_style": self.endcap_style_code,
				"endcap_color": self.endcap_color_code,
				"power_feed_type": self.power_feed_type_code,
				"environment_rating": self.environment_rating_code,
				"endcap_item": "ENDCAP-ITEM-01",
				"is_active": 1,
			},
			ignore_links=True,
		)

		# Create mounting map for this template
		self._ensure(
			{
				"doctype": "ilL-Rel-Mounting-Accessory-Map",
				"fixture_template": no_driver_template,
				"mounting_method": self.mounting_method_code,
				"environment_rating": self.environment_rating_code,
				"accessory_item": "MOUNT-ITEM-01",
				"qty_rule_type": "PER_FIXTURE",
				"qty_rule_value": 1,
				"min_qty": 0,
				"is_active": 1,
			},
			ignore_links=True,
		)

		result = validate_and_quote(
			fixture_template_code=no_driver_template,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertTrue(result["is_valid"])  # Still valid, just no driver selected

		# Verify driver plan status is not "selected"
		driver_plan = result["resolved_items"]["driver_plan"]
		self.assertIn(driver_plan["status"], ["no_eligible_drivers", "none"])

		# Verify warning message about no eligible drivers
		warning_messages = [msg for msg in result["messages"] if msg["severity"] == "warning"]
		self.assertTrue(
			any("No eligible drivers" in msg["text"] for msg in warning_messages),
			f"Expected warning about no eligible drivers. Messages: {result['messages']}"
		)

	def test_driver_plan_persisted_in_configured_fixture(self):
		"""Test Epic 5 Task 5.2: Driver plan persisted into ilL-Configured-Fixture"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Create a driver spec
		driver_item_code = "TEST-DRIVER-PERSIST"
		self._ensure(
			{
				"doctype": "ilL-Spec-Driver",
				"item": driver_item_code,
				"voltage_output": self.output_voltage_code,
				"outputs_count": 4,
				"max_wattage": 100.0,
				"usable_load_factor": 0.8,
				"dimming_protocol": None,
				"cost": 75.0,
			},
			ignore_links=True,
		)

		# Create driver eligibility mapping
		self._ensure(
			{
				"doctype": "ilL-Rel-Driver-Eligibility",
				"fixture_template": self.template_code,
				"driver_spec": driver_item_code,
				"is_allowed": 1,
				"is_active": 1,
				"priority": 0,
			},
			ignore_links=True,
		)

		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		self.assertIsNotNone(result["configured_fixture_id"])

		# Fetch the configured fixture and verify driver allocation persisted
		fixture_doc = frappe.get_doc("ilL-Configured-Fixture", result["configured_fixture_id"])

		# Verify drivers child table has data
		self.assertGreaterEqual(len(fixture_doc.drivers), 1)

		# Check driver allocation details
		driver_alloc = fixture_doc.drivers[0]
		self.assertEqual(driver_alloc.driver_item, driver_item_code)
		self.assertGreaterEqual(driver_alloc.driver_qty, 1)
		self.assertIsNotNone(driver_alloc.outputs_used)
		# Mapping notes should contain run→output mapping text
		self.assertIsNotNone(driver_alloc.mapping_notes)

	def test_configured_fixture_full_persistence_task_6_1(self):
		"""Test Epic 6 Task 6.1: Full configured fixture persistence with all computed children"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Create a driver spec for complete test coverage
		driver_item_code = "TEST-DRIVER-PERSIST-6-1"
		self._ensure(
			{
				"doctype": "ilL-Spec-Driver",
				"item": driver_item_code,
				"voltage_output": self.output_voltage_code,
				"outputs_count": 4,
				"max_wattage": 100.0,
				"usable_load_factor": 0.8,
				"dimming_protocol": None,
				"cost": 75.0,
			},
			ignore_links=True,
		)

		# Create driver eligibility mapping
		self._ensure(
			{
				"doctype": "ilL-Rel-Driver-Eligibility",
				"fixture_template": self.template_code,
				"driver_spec": driver_item_code,
				"is_allowed": 1,
				"is_active": 1,
				"priority": 0,
			},
			ignore_links=True,
		)

		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		self.assertIsNotNone(result["configured_fixture_id"])

		# Fetch the configured fixture
		fixture_doc = frappe.get_doc("ilL-Configured-Fixture", result["configured_fixture_id"])

		# Verify config_hash is set and unique
		self.assertIsNotNone(fixture_doc.config_hash)
		self.assertEqual(len(fixture_doc.config_hash), 32)  # 32 hex chars (128 bits)

		# Verify chosen option links are persisted
		self.assertEqual(fixture_doc.fixture_template, self.template_code)
		self.assertEqual(fixture_doc.finish, self.finish_code)
		self.assertEqual(fixture_doc.lens_appearance, self.lens_appearance_code)
		self.assertEqual(fixture_doc.mounting_method, self.mounting_method_code)
		self.assertEqual(fixture_doc.endcap_style, self.endcap_style_code)
		self.assertEqual(fixture_doc.endcap_color, self.endcap_color_code)
		self.assertEqual(fixture_doc.power_feed_type, self.power_feed_type_code)
		self.assertEqual(fixture_doc.environment_rating, self.environment_rating_code)
		self.assertEqual(fixture_doc.tape_offering, self.tape_offering_id)

		# Verify computed length fields are persisted
		self.assertEqual(fixture_doc.requested_overall_length_mm, 1000)
		self.assertIsNotNone(fixture_doc.endcap_allowance_mm_per_side)
		self.assertIsNotNone(fixture_doc.leader_allowance_mm)
		self.assertIsNotNone(fixture_doc.internal_length_mm)
		self.assertIsNotNone(fixture_doc.tape_cut_length_mm)
		self.assertIsNotNone(fixture_doc.manufacturable_overall_length_mm)

		# Verify run metadata (effective max run) is persisted
		self.assertEqual(fixture_doc.max_run_ft_by_watts, 17.0)
		self.assertEqual(fixture_doc.max_run_ft_by_voltage_drop, 16.0)
		self.assertEqual(fixture_doc.max_run_ft_effective, 16.0)

		# Verify resolved item links are persisted
		self.assertEqual(fixture_doc.profile_item, "PROFILE-ITEM-01")
		self.assertEqual(fixture_doc.lens_item, "LENS-ITEM-01")
		self.assertEqual(fixture_doc.endcap_item, "ENDCAP-ITEM-01")
		self.assertEqual(fixture_doc.mounting_item, "MOUNT-ITEM-01")
		self.assertEqual(fixture_doc.leader_item, "LEADER-ITEM-01")

		# Verify segments child table is persisted
		self.assertGreaterEqual(len(fixture_doc.segments), 1)
		segment = fixture_doc.segments[0]
		self.assertIsNotNone(segment.segment_index)
		self.assertIsNotNone(segment.profile_cut_len_mm)
		self.assertIsNotNone(segment.lens_cut_len_mm)

		# Verify runs child table is persisted
		self.assertGreaterEqual(len(fixture_doc.runs), 1)
		run = fixture_doc.runs[0]
		self.assertIsNotNone(run.run_index)
		self.assertIsNotNone(run.run_len_mm)
		self.assertIsNotNone(run.run_watts)
		self.assertIsNotNone(run.leader_len_mm)

		# Verify drivers child table is persisted
		self.assertGreaterEqual(len(fixture_doc.drivers), 1)
		driver = fixture_doc.drivers[0]
		self.assertIsNotNone(driver.driver_item)
		self.assertIsNotNone(driver.driver_qty)
		self.assertIsNotNone(driver.outputs_used)

		# Verify pricing_snapshot child table is persisted
		self.assertGreaterEqual(len(fixture_doc.pricing_snapshot), 1)
		snapshot = fixture_doc.pricing_snapshot[-1]
		self.assertIsNotNone(snapshot.msrp_unit)
		self.assertIsNotNone(snapshot.tier_unit)
		self.assertIsNotNone(snapshot.adder_breakdown_json)
		self.assertIsNotNone(snapshot.timestamp)

		# Verify pricing breakdown JSON is valid and contains expected components
		breakdown = json.loads(snapshot.adder_breakdown_json)
		self.assertIsInstance(breakdown, list)
		components = {item["component"] for item in breakdown}
		self.assertIn("base", components)
		self.assertIn("length", components)

	# =========================================================================
	# Epic 7 Task 7.1: Unit tests for engine core functions
	# =========================================================================

	def test_length_rounding_exact_cut_increment(self):
		"""Test length rounding when internal length is exact multiple of cut increment (50mm)"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# L_req = 1045mm (chosen so L_internal is exact multiple of 50)
		# L_internal = 1045 - 2*15 - 15 = 1000mm (exact multiple of 50)
		# L_tape_cut = floor(1000 / 50) * 50 = 1000mm
		# L_mfg = 1000 + 2*15 + 15 = 1045mm
		# difference = 1045 - 1045 = 0mm
		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1045,
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		computed = result["computed"]

		# Verify exact cut increment produces zero difference
		self.assertEqual(computed["internal_length_mm"], 1000)  # 1045 - 2*15 - 15 = 1000
		self.assertEqual(computed["tape_cut_length_mm"], 1000)  # floor(1000/50)*50 = 1000
		self.assertEqual(computed["manufacturable_overall_length_mm"], 1045)  # 1000 + 2*15 + 15
		self.assertEqual(computed["difference_mm"], 0)  # 1045 - 1045 = 0

	def test_length_rounding_rounds_down_to_cut_increment(self):
		"""Test that tape cut length always rounds DOWN to nearest cut increment"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# L_req = 1080mm
		# L_internal = 1080 - 2*15 - 15 = 1035mm
		# L_tape_cut = floor(1035 / 50) * 50 = floor(20.7) * 50 = 20 * 50 = 1000mm
		# L_mfg = 1000 + 2*15 + 15 = 1045mm
		# difference = 1080 - 1045 = 35mm
		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1080,
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		computed = result["computed"]

		# Verify rounding down behavior
		self.assertEqual(computed["internal_length_mm"], 1035)  # 1080 - 2*15 - 15
		self.assertEqual(computed["tape_cut_length_mm"], 1000)  # floor(1035/50)*50 = 1000
		self.assertEqual(computed["manufacturable_overall_length_mm"], 1045)  # 1000 + 2*15 + 15
		self.assertEqual(computed["difference_mm"], 35)  # 1080 - 1045 = 35

	def test_length_rounding_small_internal_length(self):
		"""Test length rounding when internal length is less than one cut increment"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# L_req = 74mm (very small fixture)
		# L_internal = 74 - 2*15 - 15 = 29mm (less than cut_increment of 50)
		# L_tape_cut = floor(29 / 50) * 50 = floor(0.58) * 50 = 0 * 50 = 0mm
		# L_mfg = 0 + 2*15 + 15 = 45mm
		# difference = 74 - 45 = 29mm
		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=74,
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		computed = result["computed"]

		# Verify behavior with very small internal length
		self.assertEqual(computed["internal_length_mm"], 29)  # 74 - 2*15 - 15
		self.assertEqual(computed["tape_cut_length_mm"], 0)  # floor(29/50)*50 = 0
		self.assertEqual(computed["manufacturable_overall_length_mm"], 45)  # 0 + 2*15 + 15
		self.assertEqual(computed["difference_mm"], 29)  # 74 - 45 = 29

	def test_run_splitting_voltage_drop_smaller_than_85w_max(self):
		"""Test run splitting when voltage-drop limit is smaller than 85W-derived max"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# With watts_per_ft = 5, max_run_ft_by_watts = 85/5 = 17ft
		# With voltage_drop_max_run_length_ft = 16ft (from tape spec)
		# max_run_ft_effective = min(17, 16) = 16ft (voltage-drop is limiting factor)

		# Request a fixture long enough to require multiple runs
		# 16ft = 4876.8mm, so 10000mm should require 2 runs
		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=10000,
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		computed = result["computed"]

		# Verify voltage-drop is the limiting factor
		self.assertEqual(computed["max_run_ft_by_watts"], 17.0)  # 85/5 = 17
		self.assertEqual(computed["max_run_ft_by_voltage_drop"], 16.0)  # from tape spec
		self.assertEqual(computed["max_run_ft_effective"], 16.0)  # min(17, 16) = 16
		self.assertGreater(computed["runs_count"], 1)  # Should have multiple runs

	def test_run_splitting_85w_max_smaller_than_voltage_drop(self):
		"""Test run splitting when 85W-derived max is smaller than voltage-drop max"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Create a tape spec with higher voltage drop limit and higher watts/ft
		high_watt_tape_spec = self._ensure(
			{
				"doctype": "ilL-Spec-LED Tape",
				"item": "TAPE-HIGH-WATT",
				"input_voltage": self.output_voltage_code,
				"watts_per_foot": 10,  # Higher watts/ft -> lower max_run_ft_by_watts
				"cut_increment_mm": 50,
				"voltage_drop_max_run_length_ft": 20,  # Higher voltage drop limit
			}
		)

		high_watt_tape_offering_id = f"{high_watt_tape_spec.name}-{self.cct_code}-{self.cri_code}-{self.sdcm_code}-{self.led_package_code}-{self.output_level_code}"
		self._ensure(
			{
				"doctype": "ilL-Rel-Tape Offering",
				"name": high_watt_tape_offering_id,
				"tape_spec": high_watt_tape_spec.name,
				"cct": self.cct_code,
				"cri": self.cri_code,
				"sdcm": self.sdcm_code,
				"led_package": self.led_package_code,
				"output_level": self.output_level_code,
				"is_active": 1,
			}
		)

		# Add to template allowed tape offerings
		self.template.append("allowed_tape_offerings", {
			"tape_offering": high_watt_tape_offering_id,
			"environment_rating": self.environment_rating_code,
		})
		self.template.save()

		# Create leader cable map for this tape spec
		self._ensure(
			{
				"doctype": "ilL-Rel-Leader-Cable-Map",
				"tape_spec": high_watt_tape_spec.name,
				"power_feed_type": self.power_feed_type_code,
				"environment_rating": self.environment_rating_code,
				"leader_item": "LEADER-ITEM-01",
				"default_length_mm": 150,
				"is_active": 1,
			},
			ignore_links=True,
		)

		# With watts_per_ft = 10, max_run_ft_by_watts = 85/10 = 8.5ft
		# With voltage_drop_max_run_length_ft = 20ft
		# max_run_ft_effective = min(8.5, 20) = 8.5ft (85W is limiting factor)
		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=high_watt_tape_offering_id,
			requested_overall_length_mm=5000,
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		computed = result["computed"]

		# Verify 85W limit is the limiting factor
		self.assertEqual(computed["max_run_ft_by_watts"], 8.5)  # 85/10 = 8.5
		self.assertEqual(computed["max_run_ft_by_voltage_drop"], 20.0)  # from tape spec
		self.assertEqual(computed["max_run_ft_effective"], 8.5)  # min(8.5, 20) = 8.5
		self.assertGreater(computed["runs_count"], 1)  # Should have multiple runs

	def test_run_splitting_fallback_to_85w_when_no_voltage_drop(self):
		"""Test run splitting falls back to 85W when voltage-drop max is not set"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Create a tape spec WITHOUT voltage drop limit
		no_vd_tape_spec = self._ensure(
			{
				"doctype": "ilL-Spec-LED Tape",
				"item": "TAPE-NO-VD",
				"input_voltage": self.output_voltage_code,
				"watts_per_foot": 5,
				"cut_increment_mm": 50,
				"voltage_drop_max_run_length_ft": None,  # No voltage drop limit set
			}
		)

		no_vd_tape_offering_id = f"{no_vd_tape_spec.name}-{self.cct_code}-{self.cri_code}-{self.sdcm_code}-{self.led_package_code}-{self.output_level_code}"
		self._ensure(
			{
				"doctype": "ilL-Rel-Tape Offering",
				"name": no_vd_tape_offering_id,
				"tape_spec": no_vd_tape_spec.name,
				"cct": self.cct_code,
				"cri": self.cri_code,
				"sdcm": self.sdcm_code,
				"led_package": self.led_package_code,
				"output_level": self.output_level_code,
				"is_active": 1,
			}
		)

		# Add to template allowed tape offerings
		self.template.append("allowed_tape_offerings", {
			"tape_offering": no_vd_tape_offering_id,
			"environment_rating": self.environment_rating_code,
		})
		self.template.save()

		# Create leader cable map for this tape spec
		self._ensure(
			{
				"doctype": "ilL-Rel-Leader-Cable-Map",
				"tape_spec": no_vd_tape_spec.name,
				"power_feed_type": self.power_feed_type_code,
				"environment_rating": self.environment_rating_code,
				"leader_item": "LEADER-ITEM-01",
				"default_length_mm": 150,
				"is_active": 1,
			},
			ignore_links=True,
		)

		# With watts_per_ft = 5, max_run_ft_by_watts = 85/5 = 17ft
		# With no voltage_drop_max_run_length_ft, only 85W limit applies
		# max_run_ft_effective = 17ft
		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=no_vd_tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		computed = result["computed"]

		# Verify fallback to 85W limit when no voltage drop max set
		self.assertEqual(computed["max_run_ft_by_watts"], 17.0)  # 85/5 = 17
		self.assertIsNone(computed["max_run_ft_by_voltage_drop"])  # Not set
		self.assertEqual(computed["max_run_ft_effective"], 17.0)  # Falls back to 17

	def test_sh01_max_length_assembled_mode(self):
		"""Test SH01 max-length block case - assembly mode changes at assembled_max_len_mm"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# SH01 has assembled_max_len_mm = 2590mm (~8.5ft)
		# Fixture with L_mfg <= 2590 should be ASSEMBLED
		# Fixture with L_mfg > 2590 should be SHIP_PIECES

		# Test fixture just under the limit
		# L_req = 2590mm
		# L_internal = 2590 - 2*15 - 15 = 2545mm
		# L_tape_cut = floor(2545/50)*50 = 2500mm
		# L_mfg = 2500 + 45 = 2545mm (< 2590mm -> ASSEMBLED)
		result_under = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=2590,
			qty=1,
		)

		self.assertTrue(result_under["is_valid"])
		self.assertEqual(result_under["computed"]["assembled_max_len_mm"], 2590)
		self.assertLessEqual(result_under["computed"]["manufacturable_overall_length_mm"], 2590)
		self.assertEqual(result_under["computed"]["assembly_mode"], "ASSEMBLED")

		# Test fixture just over the limit
		# L_req = 2640mm
		# L_internal = 2640 - 2*15 - 15 = 2595mm
		# L_tape_cut = floor(2595/50)*50 = 2550mm
		# L_mfg = 2550 + 45 = 2595mm (> 2590mm -> SHIP_PIECES)
		result_over = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=2640,
			qty=1,
		)

		self.assertTrue(result_over["is_valid"])
		self.assertEqual(result_over["computed"]["assembled_max_len_mm"], 2590)
		self.assertGreater(result_over["computed"]["manufacturable_overall_length_mm"], 2590)
		self.assertEqual(result_over["computed"]["assembly_mode"], "SHIP_PIECES")

	def test_sh01_max_length_boundary_exact(self):
		"""Test SH01 exact boundary case where L_mfg equals assembled_max_len_mm"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# To get L_mfg = 2590mm exactly:
		# L_mfg = L_tape_cut + 2*E + A_leader = L_tape_cut + 2*15 + 15 = L_tape_cut + 45
		# So L_tape_cut = 2590 - 45 = 2545mm
		# L_tape_cut = floor(L_internal / 50) * 50 = 2545 -> L_internal must be in [2545, 2595)
		# L_internal = L_req - 2*E - A_leader = L_req - 45
		# So L_req = L_internal + 45, with L_internal in [2545, 2595)
		# L_req = 2545 + 45 = 2590 to 2595 + 45 = 2640 (exclusive)
		# Let's use L_req = 2590 + 45 = 2635 (just under the increment that bumps up)

		# Actually simpler: L_req = 2590 gives L_internal = 2545
		# L_tape_cut = floor(2545/50)*50 = 2500mm (not 2545)
		# Let me recalculate for exact boundary...
		# For L_tape_cut = 2545, need floor(L_internal/50)*50 = 2545
		# This requires L_internal in [2545, 2595), so L_internal = 2545 works
		# But floor(2545/50) = 50.9 -> floor = 50, so 50*50 = 2500, not 2545

		# Actually, cut increment of 50 means L_tape_cut is always multiple of 50
		# So L_mfg = multiple_of_50 + 45
		# For L_mfg = 2590, need L_tape_cut = 2545 (not a multiple of 50)
		# This is impossible! L_mfg can only be 2500+45=2545, 2550+45=2595, etc.

		# The closest L_mfg values to 2590 are:
		# L_tape_cut=2500 -> L_mfg = 2545 (ASSEMBLED)
		# L_tape_cut=2550 -> L_mfg = 2595 (SHIP_PIECES)

		# Test the exact boundary values
		# L_req chosen so L_tape_cut = 2550
		# L_internal needs to be >= 2550 and < 2600
		# L_internal = L_req - 45, so L_req >= 2595 and < 2645
		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=2595,  # L_internal = 2550, L_tape_cut = 2550
			qty=1,
		)

		self.assertTrue(result["is_valid"])
		computed = result["computed"]

		# L_mfg = 2550 + 45 = 2595 (just 5mm over 2590 limit)
		self.assertEqual(computed["tape_cut_length_mm"], 2550)
		self.assertEqual(computed["manufacturable_overall_length_mm"], 2595)
		self.assertEqual(computed["assembly_mode"], "SHIP_PIECES")

	def test_missing_endcap_map_returns_error(self):
		"""Test that missing endcap map returns proper error message"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Create a new endcap color that doesn't have a mapping
		unmapped_color = "UNMAPPED-COLOR"
		self._ensure(
			{"doctype": "ilL-Attribute-Endcap Color", "code": unmapped_color, "display_name": unmapped_color}
		)

		# Add the color to allowed options for the template
		self.template.append("allowed_options", {
			"doctype": "ilL-Child-Template-Allowed-Option",
			"option_type": "Endcap Style",
			"endcap_style": self.endcap_style_code,
			"is_active": 1,
		})
		self.template.save()

		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=unmapped_color,  # No mapping exists for this
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertFalse(result["is_valid"])
		error_texts = [msg["text"] for msg in result["messages"] if msg["severity"] == "error"]
		self.assertTrue(any("Endcap-Map" in text for text in error_texts))

	def test_missing_mounting_map_returns_error(self):
		"""Test that missing mounting accessory map returns proper error message"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Create a new mounting method that doesn't have a mapping
		unmapped_mount = "UNMAPPED-MOUNT"
		self._ensure(
			{"doctype": "ilL-Attribute-Mounting Method", "label": unmapped_mount, "code": unmapped_mount}
		)

		# Add the mounting method to allowed options for the template
		self.template.append("allowed_options", {
			"doctype": "ilL-Child-Template-Allowed-Option",
			"option_type": "Mounting Method",
			"mounting_method": unmapped_mount,
			"is_active": 1,
		})
		self.template.save()

		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=unmapped_mount,  # No mapping exists for this
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertFalse(result["is_valid"])
		error_texts = [msg["text"] for msg in result["messages"] if msg["severity"] == "error"]
		self.assertTrue(any("Mounting-Accessory-Map" in text for text in error_texts))

	def test_missing_lens_map_returns_error(self):
		"""Test that missing lens map returns proper error message"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Create a new lens appearance that doesn't have a mapping
		unmapped_lens = "UNMAPPED-LENS"
		self._ensure(
			{"doctype": "ilL-Attribute-Lens Appearance", "label": unmapped_lens, "code": unmapped_lens}
		)

		# Add the lens appearance to allowed options for the template
		self.template.append("allowed_options", {
			"doctype": "ilL-Child-Template-Allowed-Option",
			"option_type": "Lens Appearance",
			"lens_appearance": unmapped_lens,
			"is_active": 1,
		})
		self.template.save()

		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=unmapped_lens,  # No mapping exists for this
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=self.power_feed_type_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertFalse(result["is_valid"])
		error_texts = [msg["text"] for msg in result["messages"] if msg["severity"] == "error"]
		self.assertTrue(any("Lens" in text for text in error_texts))

	def test_missing_leader_cable_map_returns_error(self):
		"""Test that missing leader cable map returns proper error message (duplicate of existing test for coverage)"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote,
		)

		# Create a new power feed type that doesn't have a leader cable mapping
		unmapped_power = "UNMAPPED-POWER"
		self._ensure(
			{"doctype": "ilL-Attribute-Power Feed Type", "label": unmapped_power, "code": unmapped_power}
		)

		# Add to allowed options
		self.template.append("allowed_options", {
			"doctype": "ilL-Child-Template-Allowed-Option",
			"option_type": "Power Feed Type",
			"power_feed_type": unmapped_power,
			"is_active": 1,
		})
		self.template.save()

		result = validate_and_quote(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_style_code=self.endcap_style_code,
			endcap_color_code=self.endcap_color_code,
			power_feed_type_code=unmapped_power,  # No leader cable mapping exists for this
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			requested_overall_length_mm=1000,
			qty=1,
		)

		self.assertFalse(result["is_valid"])
		error_texts = [msg["text"] for msg in result["messages"] if msg["severity"] == "error"]
		self.assertTrue(any("Leader-Cable-Map" in text for text in error_texts))

	# =========================================================================
	# Multi-Segment Tape Run Optimization Tests
	# =========================================================================

	def test_multisegment_two_segments_under_max_run_equals_one_run(self):
		"""
		Test that two 6ft segments (12ft total) under max run of 16ft equals 1 tape run.

		This is the core fix for the issue: multiple segments connected by jumpers
		should be treated as a single continuous tape run when total length is under
		the max run limit.
		"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote_multisegment,
		)

		# Create 2 segments of ~6ft (1829mm) each
		# Total: 12ft < max run of 16ft, so should be 1 run
		segments = [
			{
				"segment_index": 1,
				"requested_length_mm": 1829,  # ~6ft
				"start_power_feed_type": "END",
				"start_leader_cable_length_mm": 300,
				"end_type": "Jumper",
				"end_power_feed_type": "END",
				"end_jumper_cable_length_mm": 150,
			},
			{
				"segment_index": 2,
				"requested_length_mm": 1829,  # ~6ft
				"start_power_feed_type": "END",
				"start_leader_cable_length_mm": 150,
				"end_type": "Endcap",
				"end_power_feed_type": None,
				"end_jumper_cable_length_mm": None,
			},
		]

		result = validate_and_quote_multisegment(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_color_code=self.endcap_color_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			segments_json=json.dumps(segments),
			qty=1,
		)

		self.assertTrue(result["is_valid"], f"Expected valid, got: {result.get('messages')}")
		computed = result["computed"]

		# Key assertion: 2 segments with total tape length < max run should = 1 run
		self.assertEqual(computed["user_segment_count"], 2)
		self.assertEqual(computed["runs_count"], 1, "Two 6ft segments (12ft) under 16ft max should be 1 run")
		self.assertEqual(computed["leader_qty"], 1, "1 run should require 1 leader cable")

	def test_multisegment_total_exceeds_max_run_creates_multiple_runs(self):
		"""
		Test that segments totaling > max run length create multiple runs.

		Example: 3 segments of 6ft each = 18ft total > 16ft max run = 2 runs
		"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote_multisegment,
		)

		# Create 3 segments of ~6ft (1829mm) each
		# Total: 18ft > max run of 16ft, so should be 2 runs
		segments = [
			{
				"segment_index": 1,
				"requested_length_mm": 1829,  # ~6ft
				"start_power_feed_type": "END",
				"start_leader_cable_length_mm": 300,
				"end_type": "Jumper",
				"end_power_feed_type": "END",
				"end_jumper_cable_length_mm": 150,
			},
			{
				"segment_index": 2,
				"requested_length_mm": 1829,  # ~6ft
				"start_power_feed_type": "END",
				"start_leader_cable_length_mm": 150,
				"end_type": "Jumper",
				"end_power_feed_type": "END",
				"end_jumper_cable_length_mm": 150,
			},
			{
				"segment_index": 3,
				"requested_length_mm": 1829,  # ~6ft
				"start_power_feed_type": "END",
				"start_leader_cable_length_mm": 150,
				"end_type": "Endcap",
				"end_power_feed_type": None,
				"end_jumper_cable_length_mm": None,
			},
		]

		result = validate_and_quote_multisegment(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_color_code=self.endcap_color_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			segments_json=json.dumps(segments),
			qty=1,
		)

		self.assertTrue(result["is_valid"], f"Expected valid, got: {result.get('messages')}")
		computed = result["computed"]

		# 3 segments of ~6ft = ~18ft total tape length
		# Max run = 16ft, so need ceil(18/16) = 2 runs
		self.assertEqual(computed["user_segment_count"], 3)
		self.assertGreaterEqual(computed["runs_count"], 2, "Three 6ft segments (18ft) over 16ft max should be >= 2 runs")

	def test_multisegment_driver_plan_included(self):
		"""Test that multi-segment configurations include driver plan in response."""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			validate_and_quote_multisegment,
		)

		# Create a driver spec for this test
		driver_item_code = "TEST-DRIVER-MS"
		self._ensure(
			{
				"doctype": "ilL-Spec-Driver",
				"item": driver_item_code,
				"voltage_output": self.output_voltage_code,
				"outputs_count": 4,
				"max_wattage": 100.0,
				"usable_load_factor": 0.8,
				"dimming_protocol": None,
				"cost": 50.0,
			},
			ignore_links=True,
		)

		# Create driver eligibility mapping
		self._ensure(
			{
				"doctype": "ilL-Rel-Driver-Eligibility",
				"fixture_template": self.template_code,
				"driver_spec": driver_item_code,
				"is_allowed": 1,
				"is_active": 1,
				"priority": 0,
			},
			ignore_links=True,
		)

		segments = [
			{
				"segment_index": 1,
				"requested_length_mm": 1829,
				"start_power_feed_type": "END",
				"start_leader_cable_length_mm": 300,
				"end_type": "Jumper",
				"end_power_feed_type": "END",
				"end_jumper_cable_length_mm": 150,
			},
			{
				"segment_index": 2,
				"requested_length_mm": 1829,
				"start_power_feed_type": "END",
				"start_leader_cable_length_mm": 150,
				"end_type": "Endcap",
				"end_power_feed_type": None,
				"end_jumper_cable_length_mm": None,
			},
		]

		result = validate_and_quote_multisegment(
			fixture_template_code=self.template_code,
			finish_code=self.finish_code,
			lens_appearance_code=self.lens_appearance_code,
			mounting_method_code=self.mounting_method_code,
			endcap_color_code=self.endcap_color_code,
			environment_rating_code=self.environment_rating_code,
			tape_offering_id=self.tape_offering_id,
			segments_json=json.dumps(segments),
			qty=1,
		)

		self.assertTrue(result["is_valid"], f"Expected valid, got: {result.get('messages')}")

		# Verify driver plan is included in response
		driver_plan = result["resolved_items"]["driver_plan"]
		self.assertIn(driver_plan["status"], ["selected", "no_eligible_drivers", "no_matching_drivers"])

		# If a driver was selected, verify it has the expected structure
		if driver_plan["status"] == "selected":
			self.assertGreaterEqual(len(driver_plan["drivers"]), 1)
			driver = driver_plan["drivers"][0]
			self.assertIn("item_code", driver)
			self.assertIn("qty", driver)

	def tearDown(self):
		"""Clean up test data"""
		# Clean up any test configured fixtures created during tests
		# Delete all fixtures associated with TEST-TEMPLATE
		test_fixtures = frappe.get_all(
			"ilL-Configured-Fixture", filters={"fixture_template": self.template_code}, pluck="name"
		)
		for fixture_name in test_fixtures:
			frappe.delete_doc("ilL-Configured-Fixture", fixture_name, force=True)
		# Note: frappe.db.commit() is not needed - test framework handles transactions automatically


class TestCascadingConfiguratorAPI(FrappeTestCase):
	"""Test cases for the cascading configurator API (auto-select tape based on output)"""

	def setUp(self):
		"""Set up test data for cascading configurator tests"""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
			get_led_packages_for_template,
			get_environment_ratings_for_template,
			get_ccts_for_template,
			get_delivered_outputs_for_template,
			auto_select_tape_for_configuration,
			get_cascading_options_for_template,
		)
		self.get_led_packages_for_template = get_led_packages_for_template
		self.get_environment_ratings_for_template = get_environment_ratings_for_template
		self.get_ccts_for_template = get_ccts_for_template
		self.get_delivered_outputs_for_template = get_delivered_outputs_for_template
		self.auto_select_tape_for_configuration = auto_select_tape_for_configuration
		self.get_cascading_options_for_template = get_cascading_options_for_template

		self.template_code = "CASCADE-TEST-TEMPLATE"
		self.finish_code = "CASCADE-FINISH"
		self.lens_appearance_white = "CASCADE-LENS-WHITE"
		self.lens_appearance_clear = "CASCADE-LENS-CLEAR"
		self.environment_rating = "CASCADE-ENV-INDOOR"
		self.led_package = "CASCADE-LED-PKG"
		self.cct_3000k = "CASCADE-CCT-3000K"
		self.cct_4000k = "CASCADE-CCT-4000K"
		self.output_100 = "CASCADE-OUT-100"
		self.output_200 = "CASCADE-OUT-200"
		self.output_300 = "CASCADE-OUT-300"

		# Create attributes
		self._ensure({"doctype": "ilL-Attribute-Finish", "finish_name": self.finish_code, "code": "FIN"})
		self._ensure({
			"doctype": "ilL-Attribute-Lens Appearance",
			"label": self.lens_appearance_white,
			"code": "W",
			"transmission": 56.0,  # 56% transmission
		})
		self._ensure({
			"doctype": "ilL-Attribute-Lens Appearance",
			"label": self.lens_appearance_clear,
			"code": "C",
			"transmission": 90.0,  # 90% transmission
		})
		self._ensure({
			"doctype": "ilL-Attribute-Environment Rating",
			"label": self.environment_rating,
			"code": "I",
		})
		self._ensure({
			"doctype": "ilL-Attribute-LED Package",
			"name": self.led_package,
			"code": "LP",
			"spectrum_type": "Static White",
		})
		self._ensure({
			"doctype": "ilL-Attribute-CCT",
			"cct_name": self.cct_3000k,
			"code": "30",
			"kelvin": 3000,
			"is_active": 1,
			"sort_order": 1,
		})
		self._ensure({
			"doctype": "ilL-Attribute-CCT",
			"cct_name": self.cct_4000k,
			"code": "40",
			"kelvin": 4000,
			"is_active": 1,
			"sort_order": 2,
		})
		self._ensure({"doctype": "ilL-Attribute-CRI", "cri_name": "CASCADE-CRI-90", "code": "90"})
		self._ensure({"doctype": "ilL-Attribute-SDCM", "sdcm_name": "CASCADE-SDCM-2", "code": "2", "value": 2})

		# Create output levels (lumen per foot values)
		self._ensure({
			"doctype": "ilL-Attribute-Output Level",
			"output_level_name": self.output_100,
			"value": 100,
			"sku_code": "100",
		})
		self._ensure({
			"doctype": "ilL-Attribute-Output Level",
			"output_level_name": self.output_200,
			"value": 200,
			"sku_code": "200",
		})
		self._ensure({
			"doctype": "ilL-Attribute-Output Level",
			"output_level_name": self.output_300,
			"value": 300,
			"sku_code": "300",
		})

		# Create tape spec
		self._ensure({
			"doctype": "ilL-Spec-LED Tape",
			"item": "CASCADE-TAPE-SPEC",
			"watts_per_foot": 5.0,
			"cut_increment_mm": 50,
		}, ignore_links=True)

		# Create tape offerings with different outputs
		self.tape_offering_100 = self._ensure({
			"doctype": "ilL-Rel-Tape Offering",
			"tape_spec": "CASCADE-TAPE-SPEC",
			"cct": self.cct_3000k,
			"cri": "CASCADE-CRI-90",
			"sdcm": "CASCADE-SDCM-2",
			"led_package": self.led_package,
			"output_level": self.output_100,
			"is_active": 1,
		}, ignore_links=True)

		self.tape_offering_200 = self._ensure({
			"doctype": "ilL-Rel-Tape Offering",
			"tape_spec": "CASCADE-TAPE-SPEC",
			"cct": self.cct_3000k,
			"cri": "CASCADE-CRI-90",
			"sdcm": "CASCADE-SDCM-2",
			"led_package": self.led_package,
			"output_level": self.output_200,
			"is_active": 1,
		}, ignore_links=True)

		self.tape_offering_300 = self._ensure({
			"doctype": "ilL-Rel-Tape Offering",
			"tape_spec": "CASCADE-TAPE-SPEC",
			"cct": self.cct_4000k,
			"cri": "CASCADE-CRI-90",
			"sdcm": "CASCADE-SDCM-2",
			"led_package": self.led_package,
			"output_level": self.output_300,
			"is_active": 1,
		}, ignore_links=True)

		# Create fixture template
		self._ensure({
			"doctype": "ilL-Fixture-Template",
			"template_code": self.template_code,
			"template_name": "Cascade Test Template",
			"is_active": 1,
			"default_profile_family": "CASCADE-PROFILE",
			"default_profile_stock_len_mm": 2000,
			"assembled_max_len_mm": 2590,
			"allowed_options": [
				{"option_type": "Finish", "finish": self.finish_code, "is_active": 1},
				{"option_type": "Lens Appearance", "lens_appearance": self.lens_appearance_white, "is_active": 1},
				{"option_type": "Lens Appearance", "lens_appearance": self.lens_appearance_clear, "is_active": 1},
				{"option_type": "Environment Rating", "environment_rating": self.environment_rating, "is_active": 1},
			],
			"allowed_tape_offerings": [
				{"tape_offering": self.tape_offering_100.name, "environment_rating": self.environment_rating},
				{"tape_offering": self.tape_offering_200.name, "environment_rating": self.environment_rating},
				{"tape_offering": self.tape_offering_300.name, "environment_rating": self.environment_rating},
			],
		}, ignore_links=True)

	def _ensure(self, doc_dict, ignore_links=False):
		"""Ensure a document exists, creating or updating as needed"""
		doctype = doc_dict.get("doctype")
		name = doc_dict.get("name")
		if not name:
			if doctype == "ilL-Fixture-Template":
				name = doc_dict.get("template_code")
			elif doctype == "ilL-Attribute-Finish":
				name = doc_dict.get("finish_name")
			elif doctype in ["ilL-Attribute-Lens Appearance", "ilL-Attribute-Mounting Method", "ilL-Attribute-Endcap Style", "ilL-Attribute-Power Feed Type", "ilL-Attribute-Environment Rating"]:
				name = doc_dict.get("label")
			elif doctype == "ilL-Attribute-CCT":
				name = doc_dict.get("cct_name")
			elif doctype == "ilL-Attribute-CRI":
				name = doc_dict.get("cri_name")
			elif doctype == "ilL-Attribute-SDCM":
				name = doc_dict.get("sdcm_name")
			elif doctype == "ilL-Attribute-Output Level":
				name = doc_dict.get("output_level_name")
			elif doctype == "ilL-Spec-LED Tape":
				name = doc_dict.get("item")
			elif doctype == "ilL-Rel-Tape Offering":
				# Let autoname handle it
				pass

		if name and frappe.db.exists(doctype, name):
			doc = frappe.get_doc(doctype, name)
			for key, value in doc_dict.items():
				if key != "doctype" and hasattr(doc, key):
					setattr(doc, key, value)
			doc.save(ignore_permissions=True)
			return doc
		else:
			doc = frappe.get_doc(doc_dict)
			doc.flags.ignore_links = ignore_links
			doc.insert(ignore_permissions=True)
			return doc

	def test_get_led_packages_for_template(self):
		"""Test that LED packages are derived from linked tape offerings"""
		result = self.get_led_packages_for_template(self.template_code)

		self.assertTrue(result["success"])
		self.assertGreaterEqual(len(result["led_packages"]), 1)

		led_pkg_values = [p["value"] for p in result["led_packages"]]
		self.assertIn(self.led_package, led_pkg_values)

	def test_get_led_packages_for_nonexistent_template(self):
		"""Test error handling for non-existent template"""
		result = self.get_led_packages_for_template("NONEXISTENT-TEMPLATE")

		self.assertFalse(result["success"])
		self.assertIsNotNone(result["error"])

	def test_get_environment_ratings_for_template(self):
		"""Test that environment ratings come from template allowed options"""
		result = self.get_environment_ratings_for_template(self.template_code)

		self.assertTrue(result["success"])
		self.assertGreaterEqual(len(result["environment_ratings"]), 1)

		env_values = [e["value"] for e in result["environment_ratings"]]
		self.assertIn(self.environment_rating, env_values)

	def test_get_ccts_filtered_by_led_package(self):
		"""Test that CCTs are filtered based on LED package selection"""
		result = self.get_ccts_for_template(
			fixture_template_code=self.template_code,
			led_package_code=self.led_package,
		)

		self.assertTrue(result["success"])
		self.assertGreaterEqual(len(result["ccts"]), 1)

		cct_values = [c["value"] for c in result["ccts"]]
		self.assertIn(self.cct_3000k, cct_values)

	def test_get_delivered_outputs_calculation(self):
		"""Test that delivered outputs are calculated correctly with lens transmission"""
		result = self.get_delivered_outputs_for_template(
			fixture_template_code=self.template_code,
			led_package_code=self.led_package,
			environment_rating_code=self.environment_rating,
			cct_code=self.cct_3000k,
			lens_appearance_code=self.lens_appearance_white,  # 56% transmission
		)

		self.assertTrue(result["success"])
		self.assertGreater(len(result["delivered_outputs"]), 0)

		# With 56% transmission:
		# 100 lm/ft tape * 0.56 = 56 lm/ft -> rounded to 50
		# 200 lm/ft tape * 0.56 = 112 lm/ft -> rounded to 100
		output_values = [o["value"] for o in result["delivered_outputs"]]
		# Check that outputs are rounded to nearest 50
		for val in output_values:
			self.assertEqual(val % 50, 0, f"Output {val} should be rounded to nearest 50")

	def test_auto_select_tape_for_configuration(self):
		"""Test that tape is auto-selected based on delivered output choice"""
		# First get the delivered outputs
		outputs_result = self.get_delivered_outputs_for_template(
			fixture_template_code=self.template_code,
			led_package_code=self.led_package,
			environment_rating_code=self.environment_rating,
			cct_code=self.cct_3000k,
			lens_appearance_code=self.lens_appearance_white,  # 56% transmission
		)

		self.assertTrue(outputs_result["success"])
		self.assertGreater(len(outputs_result["delivered_outputs"]), 0)

		# Select the first available output
		selected_output = outputs_result["delivered_outputs"][0]["value"]

		# Auto-select the tape
		tape_result = self.auto_select_tape_for_configuration(
			fixture_template_code=self.template_code,
			led_package_code=self.led_package,
			environment_rating_code=self.environment_rating,
			cct_code=self.cct_3000k,
			lens_appearance_code=self.lens_appearance_white,
			delivered_output_value=selected_output,
		)

		self.assertTrue(tape_result["success"])
		self.assertIsNotNone(tape_result["tape_offering_id"])
		self.assertIsNotNone(tape_result["tape_details"])

	def test_get_cascading_options_all_at_once(self):
		"""Test the convenience function that returns all cascading options"""
		result = self.get_cascading_options_for_template(
			fixture_template_code=self.template_code,
			led_package_code=self.led_package,
			environment_rating_code=self.environment_rating,
			cct_code=self.cct_3000k,
			lens_appearance_code=self.lens_appearance_white,
		)

		self.assertTrue(result["success"])
		self.assertIn("led_packages", result["options"])
		self.assertIn("environment_ratings", result["options"])
		self.assertIn("ccts", result["options"])
		self.assertIn("lens_appearances", result["options"])
		self.assertIn("delivered_outputs", result["options"])

		# With all selections made, delivered_outputs should be populated
		self.assertGreater(len(result["options"]["delivered_outputs"]), 0)

	def tearDown(self):
		"""Clean up test data"""
		# Clean up configured fixtures
		test_fixtures = frappe.get_all(
			"ilL-Configured-Fixture", filters={"fixture_template": self.template_code}, pluck="name"
		)
		for fixture_name in test_fixtures:
			frappe.delete_doc("ilL-Configured-Fixture", fixture_name, force=True)
