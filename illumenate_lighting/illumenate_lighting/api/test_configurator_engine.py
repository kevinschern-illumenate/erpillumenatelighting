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
			"allowance_mm_per_side": 15,  # Epic 3 Task 3.1: E = endcap_style.mm_per_side
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

		if frappe.db.exists("ilL-Fixture-Template", self.template_code):
			self.template = frappe.get_doc("ilL-Fixture-Template", self.template_code)
			self.template.template_name = "Test Template"
			self.template.is_active = 1
			self.template.default_profile_family = self.profile_family
			# Epic 3 Task 3.1, 3.2, 3.4 fields
			self.template.default_profile_stock_len_mm = 2000
			self.template.leader_allowance_mm_per_fixture = 15
			self.template.assembled_max_len_mm = 2590  # ~8.5ft
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
