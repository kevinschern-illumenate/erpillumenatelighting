# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Tests for the Driver / Controller configurator API.

Covers the phases added alongside the driver & controller configurator:
- ilL-Driver-Template / ilL-Controller-Template validation rules
- the six guest configurator endpoints (init / cascading / validate)
- ilL-Webflow-Product wiring (backlinks + configurator option population)
- download_spec_sheet routing into the driver/controller spec sheet pipeline
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase


class TestDriverControllerConfigurator(FrappeTestCase):
	"""Test cases for the driver/controller configurator."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.voltage_24v = cls._ensure_doc({
			"doctype": "ilL-Attribute-Output Voltage",
			"voltage_name": "DCC-24V",
			"voltage_code": "24",
			"dc_voltage": 24,
		})
		cls.voltage_48v = cls._ensure_doc({
			"doctype": "ilL-Attribute-Output Voltage",
			"voltage_name": "DCC-48V",
			"voltage_code": "48",
			"dc_voltage": 48,
		})
		cls.proto_0_10v = cls._ensure_doc({
			"doctype": "ilL-Attribute-Dimming Protocol",
			"label": "DCC-0-10V",
			"code": "010",
		})
		cls.proto_dali = cls._ensure_doc({
			"doctype": "ilL-Attribute-Dimming Protocol",
			"label": "DCC-DALI",
			"code": "DAL",
		})
		cls.controller_type_dmx = cls._ensure_doc({
			"doctype": "ilL-Attribute-Controller Type",
			"label": "DCC-DMX Controller",
			"code": "DMX",
		})
		cls.mounting_din = cls._ensure_doc({
			"doctype": "ilL-Attribute-Mounting Type",
			"label": "DCC-DIN Rail",
			"code": "DIN",
		})

		# Two driver specs: 60W/24V and 100W/48V.
		cls.driver_spec_60 = cls._ensure_doc({
			"doctype": "ilL-Spec-Driver",
			"item": "DCC-DRV-60",
			"voltage_output": cls.voltage_24v,
			"outputs_count": 1,
			"max_wattage": 60.0,
			"output_protocol": cls.proto_0_10v,
		}, ignore_links=True)
		cls.driver_spec_100 = cls._ensure_doc({
			"doctype": "ilL-Spec-Driver",
			"item": "DCC-DRV-100",
			"voltage_output": cls.voltage_48v,
			"outputs_count": 1,
			"max_wattage": 100.0,
			"output_protocol": cls.proto_dali,
		}, ignore_links=True)

		cls.controller_spec = cls._ensure_doc({
			"doctype": "ilL-Spec-Controller",
			"item": "DCC-CTL-4CH",
			"controller_name": "Test 4ch DMX Controller",
			"controller_type": "DMX Controller",
			"channels": 4,
			"zones": 1,
		}, ignore_links=True)

	@classmethod
	def _ensure_doc(cls, data: dict, ignore_links: bool = False) -> str:
		"""Insert a document if it does not exist yet and return its name."""
		doc = frappe.get_doc(data)
		doc.flags.ignore_links = ignore_links
		doc.insert(ignore_if_duplicate=True, ignore_links=ignore_links)
		return doc.name

	def _cleanup(self, doctype: str, name: str) -> None:
		"""Register a delete that tolerates the doc already being gone."""
		def _delete():
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

		self.addCleanup(_delete)

	# ── fixtures ──────────────────────────────────────────────────────

	def _make_driver_template(self, suffix: str = "", with_options: bool = True):
		"""Two-variant driver template: 60W/24V/0-10V and 100W/48V/DALI."""
		code = "DCC-DRV-TPL-" + (suffix or frappe.generate_hash(length=6))
		template = frappe.get_doc({
			"doctype": "ilL-Driver-Template",
			"template_code": code,
			"template_name": "Driver Configurator Test",
			"is_active": 1,
			"sku_series_code": "PSU",
			"base_price_msrp": 100.0,
			"variants": [
				{
					"driver_spec": self.driver_spec_60,
					"is_default": 1,
					"is_active": 1,
					"variant_code": "60-24",
					"wattage": 60,
					"voltage_output": self.voltage_24v,
					"input_protocol": self.proto_0_10v,
				},
				{
					"driver_spec": self.driver_spec_100,
					"is_active": 1,
					"variant_code": "100-48",
					"wattage": 100,
					"voltage_output": self.voltage_48v,
					"input_protocol": self.proto_dali,
				},
			],
		})
		if with_options:
			template.extend("allowed_options", [
				{"option_type": "Wattage", "option_value": "60", "option_label": "60W",
				 "option_code": "060", "is_default": 1, "is_active": 1},
				{"option_type": "Wattage", "option_value": "100", "option_label": "100W",
				 "option_code": "100", "is_active": 1},
				{"option_type": "Voltage Output", "attribute_doctype": "ilL-Attribute-Output Voltage",
				 "attribute_link": self.voltage_24v, "option_label": "24V", "option_code": "24",
				 "is_default": 1, "is_active": 1},
				{"option_type": "Voltage Output", "attribute_doctype": "ilL-Attribute-Output Voltage",
				 "attribute_link": self.voltage_48v, "option_label": "48V", "option_code": "48",
				 "is_active": 1},
				{"option_type": "Input Protocol", "attribute_doctype": "ilL-Attribute-Dimming Protocol",
				 "attribute_link": self.proto_0_10v, "option_label": "0-10V", "option_code": "010",
				 "is_default": 1, "is_active": 1},
				{"option_type": "Input Protocol", "attribute_doctype": "ilL-Attribute-Dimming Protocol",
				 "attribute_link": self.proto_dali, "option_label": "DALI", "option_code": "DAL",
				 "is_active": 1},
			])
		template.flags.ignore_links = True
		template.insert(ignore_links=True)
		self._cleanup("ilL-Driver-Template", template.name)
		return template

	def _make_webflow_product(self, template_name: str, kind: str = "Driver", configurable: int = 1):
		field = "driver_template" if kind == "Driver" else "controller_template"
		product = frappe.get_doc({
			"doctype": "ilL-Webflow-Product",
			"product_name": f"{kind} Configurator Test",
			"product_slug": f"dcc-{kind.lower()}-" + frappe.generate_hash(length=6),
			"product_type": kind,
			"is_active": 1,
			"is_configurable": configurable,
			field: template_name,
		})
		product.insert()
		self._cleanup("ilL-Webflow-Product", product.name)
		return product

	# ── template validation ───────────────────────────────────────────

	def test_duplicate_variant_axes_rejected(self):
		"""Two active variants may not share the same axis tuple."""
		template = self._make_driver_template()
		template.append("variants", {
			"driver_spec": self.driver_spec_100,
			"is_active": 1,
			"variant_code": "60-24-DUPE",
			"wattage": 60,
			"voltage_output": self.voltage_24v,
			"input_protocol": self.proto_0_10v,
		})
		with self.assertRaises(frappe.ValidationError):
			template.save(ignore_permissions=True)

	def test_numeric_axis_values_compare_numerically(self):
		"""60 and 60.0 are the same wattage, so the duplicate check must fire."""
		template = self._make_driver_template()
		template.append("variants", {
			"driver_spec": self.driver_spec_100,
			"is_active": 1,
			"variant_code": "60-24-FLOAT",
			"wattage": 60.0,
			"voltage_output": self.voltage_24v,
			"input_protocol": self.proto_0_10v,
		})
		with self.assertRaises(frappe.ValidationError):
			template.save(ignore_permissions=True)

	def test_multiple_default_variants_rejected(self):
		"""Only one variant may be flagged as the default."""
		template = self._make_driver_template()
		template.variants[1].is_default = 1
		with self.assertRaises(frappe.ValidationError):
			template.save(ignore_permissions=True)

	def test_wattage_option_requires_option_value(self):
		"""A scalar option type must carry option_value, not an attribute link."""
		template = self._make_driver_template()
		template.append("allowed_options", {
			"option_type": "Wattage",
			"option_label": "150W",
			"is_active": 1,
		})
		with self.assertRaises(frappe.ValidationError):
			template.save(ignore_permissions=True)

	# ── configurator endpoints ────────────────────────────────────────

	def test_init_returns_only_steps_with_options(self):
		from illumenate_lighting.illumenate_lighting.api.driver_controller_configurator import (
			get_driver_configurator_init,
		)

		template = self._make_driver_template()
		product = self._make_webflow_product(template.name)

		result = get_driver_configurator_init(product.product_slug)

		self.assertTrue(result["success"])
		step_names = [s["name"] for s in result["steps"]]
		# Output Protocol has no allowed options on this template.
		self.assertEqual(step_names, ["wattage", "voltage_output", "input_protocol"])
		self.assertEqual(result["variant_count"], 2)
		self.assertEqual(result["part_number_prefix"], "ILL-PSU")
		self.assertEqual(len(result["options"]["wattage"]), 2)

	def test_init_rejects_non_configurable_product(self):
		from illumenate_lighting.illumenate_lighting.api.driver_controller_configurator import (
			get_driver_configurator_init,
		)

		template = self._make_driver_template()
		product = self._make_webflow_product(template.name, configurable=0)

		result = get_driver_configurator_init(product.product_slug)
		self.assertFalse(result["success"])

	def test_cascading_options_narrow_downstream_steps(self):
		from illumenate_lighting.illumenate_lighting.api.driver_controller_configurator import (
			get_driver_cascading_options,
		)

		template = self._make_driver_template()
		product = self._make_webflow_product(template.name)

		result = get_driver_cascading_options(
			product.product_slug, "wattage", json.dumps({"wattage": "60"})
		)

		self.assertTrue(result["success"])
		self.assertEqual(result["matching_variant_count"], 1)
		voltages = [o["value"] for o in result["updated_options"]["voltage_output"]]
		self.assertEqual(voltages, [self.voltage_24v])
		self.assertNotIn("wattage", result["updated_options"])

	def test_cascading_clears_impossible_downstream_selection(self):
		from illumenate_lighting.illumenate_lighting.api.driver_controller_configurator import (
			get_driver_cascading_options,
		)

		template = self._make_driver_template()
		product = self._make_webflow_product(template.name)

		result = get_driver_cascading_options(
			product.product_slug,
			"wattage",
			json.dumps({"wattage": "60", "voltage_output": self.voltage_48v}),
		)

		self.assertTrue(result["success"])
		self.assertIn("voltage_output", result["clear_selections"])

	def test_validate_returns_matched_variant_and_part_number(self):
		from illumenate_lighting.illumenate_lighting.api.driver_controller_configurator import (
			validate_driver_configuration,
		)

		template = self._make_driver_template()
		product = self._make_webflow_product(template.name)

		result = validate_driver_configuration(product.product_slug, json.dumps({
			"wattage": "60",
			"voltage_output": self.voltage_24v,
			"input_protocol": self.proto_0_10v,
		}))

		self.assertTrue(result["success"])
		self.assertEqual(result["part_number"], "ILL-PSU-60-24")
		self.assertEqual(result["variant"]["spec_name"], self.driver_spec_60)
		self.assertTrue(result["variant"]["variant_name"])
		self.assertEqual(result["pricing"]["total_msrp"], 100.0)

	def test_validate_reports_missing_steps(self):
		from illumenate_lighting.illumenate_lighting.api.driver_controller_configurator import (
			validate_driver_configuration,
		)

		template = self._make_driver_template()
		product = self._make_webflow_product(template.name)

		result = validate_driver_configuration(
			product.product_slug, json.dumps({"wattage": "60"})
		)

		self.assertFalse(result["success"])
		self.assertIn("Output Voltage", result["missing_steps"])

	def test_validate_rejects_unmatched_combination(self):
		from illumenate_lighting.illumenate_lighting.api.driver_controller_configurator import (
			validate_driver_configuration,
		)

		template = self._make_driver_template()
		product = self._make_webflow_product(template.name)

		result = validate_driver_configuration(product.product_slug, json.dumps({
			"wattage": "60",
			"voltage_output": self.voltage_48v,
			"input_protocol": self.proto_0_10v,
		}))

		self.assertFalse(result["success"])
		self.assertNotIn("missing_steps", result)

	# ── Webflow product wiring ────────────────────────────────────────

	def test_driver_template_backlink_set_and_cleared(self):
		template = self._make_driver_template()
		product = self._make_webflow_product(template.name)

		template.reload()
		self.assertEqual(template.webflow_product, product.name)

		frappe.delete_doc("ilL-Webflow-Product", product.name, force=True, ignore_permissions=True)
		template.reload()
		self.assertFalse(template.webflow_product)

	def test_configurator_options_populated_from_driver_template(self):
		template = self._make_driver_template()
		product = self._make_webflow_product(template.name)

		option_types = [o.option_type for o in product.configurator_options]
		self.assertEqual(option_types, ["Wattage", "Voltage Output", "Input Protocol"])

		wattage_row = product.configurator_options[0]
		self.assertEqual(wattage_row.option_step, 1)
		values = json.loads(wattage_row.allowed_values_json)
		self.assertEqual([v["value"] for v in values], ["60", "100"])

	def test_controller_template_populates_dependent_steps(self):
		template = frappe.get_doc({
			"doctype": "ilL-Controller-Template",
			"template_code": "DCC-CTL-TPL-" + frappe.generate_hash(length=6),
			"template_name": "Controller Configurator Test",
			"is_active": 1,
			"sku_series_code": "CTL",
			"variants": [{
				"controller_spec": self.controller_spec,
				"is_default": 1,
				"is_active": 1,
				"variant_code": "DMX-4",
				"controller_type": self.controller_type_dmx,
				"channels": 4,
				"mounting_type": self.mounting_din,
			}],
			"allowed_options": [
				{"option_type": "Controller Type",
				 "attribute_doctype": "ilL-Attribute-Controller Type",
				 "attribute_link": self.controller_type_dmx, "option_label": "DMX",
				 "option_code": "DMX", "is_default": 1, "is_active": 1},
				{"option_type": "Channels", "option_value": "4", "option_label": "4 Channel",
				 "option_code": "04", "is_default": 1, "is_active": 1},
				{"option_type": "Mounting Type",
				 "attribute_doctype": "ilL-Attribute-Mounting Type",
				 "attribute_link": self.mounting_din, "option_label": "DIN Rail",
				 "option_code": "DIN", "is_default": 1, "is_active": 1},
			],
		})
		template.flags.ignore_links = True
		template.insert(ignore_links=True)
		self._cleanup("ilL-Controller-Template", template.name)

		product = self._make_webflow_product(template.name, kind="Controller")

		rows = {o.option_type: o for o in product.configurator_options}
		self.assertEqual(
			list(rows), ["Controller Type", "Channels", "Mounting Type"]
		)
		# Channels depends on Controller Type; Mounting Type is independent.
		self.assertEqual(rows["Channels"].depends_on_step, 1)
		self.assertFalse(rows["Mounting Type"].depends_on_step)

	# ── spec sheet download routing ───────────────────────────────────

	def test_download_spec_sheet_routes_driver_to_variant_pipeline(self):
		"""A Driver slug must not fall through to the fixture pipeline."""
		from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
			download_spec_sheet,
		)

		template = self._make_driver_template()
		product = self._make_webflow_product(template.name)

		result = download_spec_sheet(
			product_slug=product.product_slug,
			selections=json.dumps({
				"wattage": "60",
				"voltage_output": self.voltage_24v,
				"input_protocol": self.proto_0_10v,
			}),
		)

		# No submittal template and no spec sheet are attached to the template,
		# so the pipeline reports that specific condition rather than a
		# fixture-template error.
		self.assertFalse(result["success"])
		self.assertIn("spec sheet", result["error"].lower())

	def test_download_spec_sheet_returns_static_sheet_fallback(self):
		from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
			download_spec_sheet,
		)

		template = self._make_driver_template()
		template.db_set("spec_sheet", "/files/dcc-static-spec-sheet.pdf")
		product = self._make_webflow_product(template.name)

		result = download_spec_sheet(
			product_slug=product.product_slug,
			selections=json.dumps({
				"wattage": "60",
				"voltage_output": self.voltage_24v,
				"input_protocol": self.proto_0_10v,
			}),
		)

		self.assertTrue(result["success"])
		self.assertEqual(result["file_url"], "/files/dcc-static-spec-sheet.pdf")
		self.assertEqual(result["part_number"], "ILL-PSU-60-24")
