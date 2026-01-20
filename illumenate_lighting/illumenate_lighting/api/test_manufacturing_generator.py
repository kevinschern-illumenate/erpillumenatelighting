# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Tests for Manufacturing Artifacts Generator API
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestManufacturingGenerator(FrappeTestCase):
	"""Test cases for the manufacturing artifacts generator API"""

	def setUp(self):
		"""Set up test data"""
		self.template_code = "TEST-MFG-TEMPLATE"
		self.finish_code = "FINISH-MFG"
		self.lens_appearance_code = "LENS-MFG"
		self.mounting_method_code = "MOUNT-MFG"
		self.endcap_style_code = "ENDCAP-MFG-FLAT"
		self.endcap_color_code = "ENDCAP-MFG-WHITE"
		self.power_feed_type_code = "POWER-MFG-WIRE"
		self.environment_rating_code = "ENV-MFG-DRY"
		self.profile_family = "PFAM-MFG-TEST"
		self.lens_interface_code = "LENS-MFG-IFACE"
		self.output_voltage_code = "24V-MFG"
		self.cct_code = "CCT-MFG-3000K"
		self.cri_code = "CRI-MFG-90"
		self.sdcm_code = "SDCM-MFG-2"
		self.led_package_code = "LP-MFG-1"
		self.output_level_code = "OP-MFG-1"

		# Create attribute docs
		self._ensure({"doctype": "ilL-Attribute-Finish", "finish_name": self.finish_code, "code": self.finish_code})
		self._ensure({"doctype": "ilL-Attribute-Lens Appearance", "label": self.lens_appearance_code, "code": self.lens_appearance_code})
		self._ensure({"doctype": "ilL-Attribute-Mounting Method", "label": self.mounting_method_code, "code": self.mounting_method_code})
		self._ensure({
			"doctype": "ilL-Attribute-Endcap Style",
			"label": self.endcap_style_code,
			"code": self.endcap_style_code,
			"allowance_mm_per_side": 15,
		})
		self._ensure({"doctype": "ilL-Attribute-Endcap Color", "code": self.endcap_color_code, "display_name": self.endcap_color_code})
		self._ensure({"doctype": "ilL-Attribute-Power Feed Type", "label": self.power_feed_type_code, "code": self.power_feed_type_code})
		self._ensure({"doctype": "ilL-Attribute-Environment Rating", "label": self.environment_rating_code, "code": self.environment_rating_code})
		self._ensure({"doctype": "ilL-Attribute-Lens Interface Type", "label": self.lens_interface_code, "code": self.lens_interface_code, "is_active": 1})
		self._ensure({"doctype": "ilL-Attribute-Output Voltage", "output_voltage_name": self.output_voltage_code, "code": self.output_voltage_code})
		self._ensure({"doctype": "ilL-Attribute-CCT", "cct_name": self.cct_code, "code": self.cct_code, "kelvin": 3000})
		self._ensure({"doctype": "ilL-Attribute-CRI", "cri_name": self.cri_code, "code": self.cri_code})
		self._ensure({"doctype": "ilL-Attribute-SDCM", "sdcm_name": self.sdcm_code, "code": self.sdcm_code, "value": 2})
		self._ensure({"doctype": "ilL-Attribute-LED Package", "package_name": self.led_package_code, "code": self.led_package_code})
		self._ensure({"doctype": "ilL-Attribute-Output Level", "output_level_name": self.output_level_code, "value": 1, "sku_code": self.output_level_code})

		# Create Item Group if needed
		if not frappe.db.exists("Item Group", "Configured Fixtures"):
			frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": "Configured Fixtures",
				"parent_item_group": "All Item Groups",
			}).insert(ignore_permissions=True)

		# Create test Items for components
		self._ensure_item("PROFILE-MFG-ITEM", "Test Profile Item", "Products")
		self._ensure_item("LENS-MFG-ITEM", "Test Lens Item", "Products")
		self._ensure_item("ENDCAP-MFG-ITEM", "Test Endcap Item", "Products")
		self._ensure_item("MOUNT-MFG-ITEM", "Test Mounting Item", "Products")
		self._ensure_item("LEADER-MFG-ITEM", "Test Leader Item", "Products")
		self._ensure_item("TAPE-MFG-ITEM", "Test Tape Item", "Products")
		self._ensure_item("DRIVER-MFG-ITEM", "Test Driver Item", "Products")

		# Create specs
		self.profile_spec = self._ensure({
			"doctype": "ilL-Spec-Profile",
			"item": "PROFILE-MFG-ITEM",
			"family": self.profile_family,
			"variant_code": self.finish_code,
			"is_active": 1,
			"lens_interface": self.lens_interface_code,
			"stock_length_mm": 2000,
		}, ignore_links=True)

		self.lens_spec = self._ensure({
			"doctype": "ilL-Spec-Lens",
			"item": "LENS-MFG-ITEM",
			"family": "LENS-MFG-FAMILY",
			"lens_appearance": self.lens_appearance_code,
			"supported_environment_ratings": [{"environment_rating": self.environment_rating_code}],
		}, ignore_links=True)

		self.tape_spec = self._ensure({
			"doctype": "ilL-Spec-LED Tape",
			"item": "TAPE-MFG-ITEM",
			"input_voltage": self.output_voltage_code,
			"watts_per_foot": 5,
			"cut_increment_mm": 50,
			"voltage_drop_max_run_length_ft": 16,
		}, ignore_links=True)

		self.tape_offering_id = f"{self.tape_spec.name}-{self.cct_code}-{self.cri_code}-{self.sdcm_code}-{self.led_package_code}-{self.output_level_code}"
		self.tape_offering = self._ensure({
			"doctype": "ilL-Rel-Tape Offering",
			"name": self.tape_offering_id,
			"tape_spec": self.tape_spec.name,
			"cct": self.cct_code,
			"cri": self.cri_code,
			"sdcm": self.sdcm_code,
			"led_package": self.led_package_code,
			"output_level": self.output_level_code,
			"is_active": 1,
		}, ignore_links=True)

		# Create template with allowed options
		template_allowed_options = [
			{"doctype": "ilL-Child-Template-Allowed-Option", "option_type": "Finish", "finish": self.finish_code, "is_active": 1, "is_default": 1},
			{"doctype": "ilL-Child-Template-Allowed-Option", "option_type": "Lens Appearance", "lens_appearance": self.lens_appearance_code, "is_active": 1},
			{"doctype": "ilL-Child-Template-Allowed-Option", "option_type": "Mounting Method", "mounting_method": self.mounting_method_code, "is_active": 1},
			{"doctype": "ilL-Child-Template-Allowed-Option", "option_type": "Endcap Style", "endcap_style": self.endcap_style_code, "is_active": 1},
			{"doctype": "ilL-Child-Template-Allowed-Option", "option_type": "Power Feed Type", "power_feed_type": self.power_feed_type_code, "is_active": 1},
			{"doctype": "ilL-Child-Template-Allowed-Option", "option_type": "Environment Rating", "environment_rating": self.environment_rating_code, "is_active": 1},
		]

		template_allowed_tapes = [{"doctype": "ilL-Child-Template-Allowed-TapeOffering", "tape_offering": self.tape_offering.name, "environment_rating": self.environment_rating_code}]

		if frappe.db.exists("ilL-Fixture-Template", self.template_code):
			self.template = frappe.get_doc("ilL-Fixture-Template", self.template_code)
			self.template.template_name = "Test MFG Template"
			self.template.is_active = 1
			self.template.default_profile_family = self.profile_family
			self.template.default_profile_stock_len_mm = 2000
			self.template.leader_allowance_mm_per_fixture = 15
			self.template.assembled_max_len_mm = 2590
			self.template.base_price_msrp = 100.0
			self.template.price_per_ft_msrp = 10.0
			self.template.pricing_length_basis = "L_tape_cut"
			self.template.allowed_options = template_allowed_options
			self.template.allowed_tape_offerings = template_allowed_tapes
			self.template.save()
		else:
			self.template = self._ensure({
				"doctype": "ilL-Fixture-Template",
				"template_code": self.template_code,
				"template_name": "Test MFG Template",
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
			})

		# Create mapping tables
		self._ensure({
			"doctype": "ilL-Rel-Endcap-Map",
			"fixture_template": self.template_code,
			"endcap_style": self.endcap_style_code,
			"endcap_color": self.endcap_color_code,
			"power_feed_type": self.power_feed_type_code,
			"environment_rating": self.environment_rating_code,
			"endcap_item": "ENDCAP-MFG-ITEM",
			"is_active": 1,
		}, ignore_links=True)

		self._ensure({
			"doctype": "ilL-Rel-Mounting-Accessory-Map",
			"fixture_template": self.template_code,
			"mounting_method": self.mounting_method_code,
			"environment_rating": self.environment_rating_code,
			"accessory_item": "MOUNT-MFG-ITEM",
			"qty_rule_type": "PER_FIXTURE",
			"qty_rule_value": 2,
			"min_qty": 1,
			"is_active": 1,
		}, ignore_links=True)

		self._ensure({
			"doctype": "ilL-Rel-Leader-Cable-Map",
			"tape_spec": self.tape_spec.name,
			"power_feed_type": self.power_feed_type_code,
			"environment_rating": self.environment_rating_code,
			"leader_item": "LEADER-MFG-ITEM",
			"default_length_mm": 150,
			"is_active": 1,
		}, ignore_links=True)

		# Create a driver spec and eligibility for complete test
		self._ensure({
			"doctype": "ilL-Spec-Driver",
			"item": "DRIVER-MFG-ITEM",
			"voltage_output": self.output_voltage_code,
			"outputs_count": 4,
			"max_wattage": 100.0,
			"usable_load_factor": 0.8,
			"cost": 50.0,
		}, ignore_links=True)

		self._ensure({
			"doctype": "ilL-Rel-Driver-Eligibility",
			"fixture_template": self.template_code,
			"driver_spec": "DRIVER-MFG-ITEM",
			"is_allowed": 1,
			"is_active": 1,
			"priority": 0,
		}, ignore_links=True)

	def _ensure(self, data: dict, ignore_links: bool = False):
		"""Insert a document if it does not already exist and return it."""
		doc = frappe.get_doc(data)
		doc.flags.ignore_links = ignore_links
		doc.insert(ignore_if_duplicate=True, ignore_links=ignore_links)
		doc = frappe.get_doc(data["doctype"], doc.name)
		return doc

	def _ensure_item(self, item_code: str, item_name: str, item_group: str):
		"""Ensure an Item exists."""
		if not frappe.db.exists("Item", item_code):
			frappe.get_doc({
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_name,
				"item_group": item_group,
				"stock_uom": "Nos",
			}).insert(ignore_permissions=True)

	def _create_configured_fixture(self):
		"""Create a configured fixture for testing."""
		from illumenate_lighting.illumenate_lighting.api.configurator_engine import validate_and_quote

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

		if not result["is_valid"]:
			raise ValueError(f"Failed to create fixture: {result['messages']}")

		return result["configured_fixture_id"]

	def test_generate_manufacturing_artifacts_basic(self):
		"""Test basic manufacturing artifact generation"""
		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import generate_manufacturing_artifacts

		fixture_id = self._create_configured_fixture()

		result = generate_manufacturing_artifacts(
			configured_fixture_id=fixture_id,
			qty=1,
			skip_if_exists=False,
		)

		# Verify response structure
		self.assertIn("success", result)
		self.assertIn("item_code", result)
		self.assertIn("bom_name", result)
		self.assertIn("work_order_name", result)
		self.assertIn("messages", result)

		# Verify success
		self.assertTrue(result["success"], f"Generation failed: {result['messages']}")

		# Verify artifacts were created
		self.assertIsNotNone(result["item_code"])
		self.assertTrue(result["item_code"].startswith("ILL-"))

	def test_item_code_naming_convention(self):
		"""Test that item code follows ILL-{hash} convention"""
		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import generate_manufacturing_artifacts

		fixture_id = self._create_configured_fixture()
		fixture = frappe.get_doc("ilL-Configured-Fixture", fixture_id)

		result = generate_manufacturing_artifacts(
			configured_fixture_id=fixture_id,
			qty=1,
			skip_if_exists=False,
		)

		self.assertTrue(result["success"])

		# Item code should be ILL-{first 8 chars of config_hash}
		expected_item_code = f"ILL-{fixture.config_hash[:8].upper()}"
		self.assertEqual(result["item_code"], expected_item_code)

	def test_configured_item_reuse(self):
		"""Test that identical configurations reuse the same Item (Epic 2 reuse policy)"""
		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import generate_manufacturing_artifacts

		fixture_id = self._create_configured_fixture()

		# Generate artifacts first time
		result1 = generate_manufacturing_artifacts(
			configured_fixture_id=fixture_id,
			qty=1,
			skip_if_exists=True,
		)

		self.assertTrue(result1["success"])
		self.assertTrue(result1["created"]["item"])

		# Generate artifacts second time
		result2 = generate_manufacturing_artifacts(
			configured_fixture_id=fixture_id,
			qty=1,
			skip_if_exists=True,
		)

		self.assertTrue(result2["success"])
		self.assertTrue(result2["skipped"]["item"])  # Should be skipped, not created

		# Should use the same item
		self.assertEqual(result1["item_code"], result2["item_code"])

	def test_bom_endcap_extra_pair_rule(self):
		"""Test Epic 3 Task 3.3: Endcap extra pair rule (4 total endcaps)"""
		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import generate_manufacturing_artifacts

		fixture_id = self._create_configured_fixture()

		result = generate_manufacturing_artifacts(
			configured_fixture_id=fixture_id,
			qty=1,
			skip_if_exists=False,
		)

		self.assertTrue(result["success"])
		self.assertIsNotNone(result["bom_name"])

		# Check BOM for endcap quantity
		bom = frappe.get_doc("BOM", result["bom_name"])
		endcap_items = [item for item in bom.items if item.item_code == "ENDCAP-MFG-ITEM"]

		self.assertEqual(len(endcap_items), 1)
		self.assertEqual(endcap_items[0].qty, 4)  # 2 for use + 2 extra pair

	def test_work_order_has_traveler_notes(self):
		"""Test Epic 5 Task 5.2: Work Order includes traveler notes"""
		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import generate_manufacturing_artifacts

		fixture_id = self._create_configured_fixture()

		result = generate_manufacturing_artifacts(
			configured_fixture_id=fixture_id,
			qty=1,
			skip_if_exists=False,
		)

		self.assertTrue(result["success"])
		self.assertIsNotNone(result["work_order_name"])

		# Check Work Order has traveler notes in remarks
		wo = frappe.get_doc("Work Order", result["work_order_name"])
		self.assertIsNotNone(wo.remarks)
		self.assertIn("MANUFACTURING TRAVELER", wo.remarks)
		self.assertIn("LENGTH SPECIFICATIONS", wo.remarks)
		self.assertIn("SEGMENT CUT LIST", wo.remarks)
		self.assertIn("RUN BREAKDOWN", wo.remarks)
		self.assertIn("DRIVER SELECTION", wo.remarks)
		self.assertIn("ENDCAPS", wo.remarks)
		self.assertIn("QC / TESTING SECTION", wo.remarks)

	def test_fixture_links_updated(self):
		"""Test Epic 6: Configured fixture links are updated after generation"""
		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import generate_manufacturing_artifacts

		fixture_id = self._create_configured_fixture()

		result = generate_manufacturing_artifacts(
			configured_fixture_id=fixture_id,
			qty=1,
			skip_if_exists=False,
		)

		self.assertTrue(result["success"])

		# Reload fixture and check links
		fixture = frappe.get_doc("ilL-Configured-Fixture", fixture_id)
		self.assertEqual(fixture.configured_item, result["item_code"])
		self.assertEqual(fixture.bom, result["bom_name"])
		self.assertEqual(fixture.work_order, result["work_order_name"])

	def test_idempotency(self):
		"""Test Epic 6 Task 6.2: Idempotency - safe to re-run without duplicating"""
		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import generate_manufacturing_artifacts

		fixture_id = self._create_configured_fixture()

		# Run first time
		result1 = generate_manufacturing_artifacts(
			configured_fixture_id=fixture_id,
			qty=1,
			skip_if_exists=True,
		)

		self.assertTrue(result1["success"])

		# Run second time with same parameters
		result2 = generate_manufacturing_artifacts(
			configured_fixture_id=fixture_id,
			qty=1,
			skip_if_exists=True,
		)

		self.assertTrue(result2["success"])

		# Same artifacts should be returned
		self.assertEqual(result1["item_code"], result2["item_code"])
		self.assertEqual(result1["bom_name"], result2["bom_name"])
		self.assertEqual(result1["work_order_name"], result2["work_order_name"])

		# Second run should have skipped flags
		self.assertTrue(result2["skipped"]["item"])
		self.assertTrue(result2["skipped"]["bom"])
		self.assertTrue(result2["skipped"]["work_order"])

	def test_missing_configured_fixture(self):
		"""Test error handling for non-existent configured fixture"""
		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import generate_manufacturing_artifacts

		result = generate_manufacturing_artifacts(
			configured_fixture_id="NON-EXISTENT-FIXTURE",
			qty=1,
			skip_if_exists=True,
		)

		self.assertFalse(result["success"])
		error_messages = [m for m in result["messages"] if m["severity"] == "error"]
		self.assertTrue(len(error_messages) > 0)
		self.assertIn("not found", error_messages[0]["text"])

	def tearDown(self):
		"""Clean up test data"""
		# Delete Work Orders first (they reference BOMs)
		for wo in frappe.get_all("Work Order", filters={"production_item": ["like", "ILL-%"]}, pluck="name"):
			try:
				wo_doc = frappe.get_doc("Work Order", wo)
				if wo_doc.docstatus == 1:
					wo_doc.cancel()
				frappe.delete_doc("Work Order", wo, force=True)
			except Exception:
				pass

		# Delete BOMs (they need to be cancelled first if submitted)
		for bom in frappe.get_all("BOM", filters={"item": ["like", "ILL-%"]}, pluck="name"):
			try:
				bom_doc = frappe.get_doc("BOM", bom)
				if bom_doc.docstatus == 1:
					bom_doc.cancel()
				frappe.delete_doc("BOM", bom, force=True)
			except Exception:
				pass

		# Delete Items
		for item in frappe.get_all("Item", filters={"item_code": ["like", "ILL-%"]}, pluck="name"):
			try:
				frappe.delete_doc("Item", item, force=True)
			except Exception:
				pass

		# Delete configured fixtures
		for fixture in frappe.get_all("ilL-Configured-Fixture", filters={"fixture_template": self.template_code}, pluck="name"):
			try:
				frappe.delete_doc("ilL-Configured-Fixture", fixture, force=True)
			except Exception:
				pass
