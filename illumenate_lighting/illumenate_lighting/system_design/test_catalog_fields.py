# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Installed-site checks for the System Designer catalog fields and their pre-fill patch (WP-1.1)."""

import frappe
from frappe.tests import IntegrationTestCase

from illumenate_lighting.patches import system_designer_tape_fields


class TestSystemDesignerCatalogFields(IntegrationTestCase):
	def test_fields_exist(self):
		for doctype, field in (
			("ilL-Attribute-Output Voltage", "nominal_voltage_v"),
			("ilL-Attribute-Dimming Protocol", "engine_protocol"),
			("ilL-Spec-LED Tape", "max_run_single_feed_ft"),
			("ilL-Spec-LED Tape", "channel_limits"),
			("ilL-Spec-Profile", "cross_section_json"),
			("ilL-Spec-Accessory", "clip_spacing_max_in"),
			("ilL-Spec-Lens", "diffusion_class"),
			("ilL-Fixture-Template", "diagram_icon"),
			("ilL-Tape-Neon-Template", "scene_archetypes"),
			("ilL-LED-Sheet-Template", "diagram_icon"),
		):
			with self.subTest(doctype=doctype, field=field):
				self.assertIsNotNone(frappe.get_meta(doctype).get_field(field))

	def test_patch_is_idempotent(self):
		name = "ZZTEST " + frappe.generate_hash(length=6)
		frappe.get_doc(
			{
				"doctype": "ilL-Attribute-Output Voltage",
				"voltage_name": name + " 24V",
				"voltage_code": name[-6:],
				"dc_voltage": "24V",
			}
		).insert(ignore_permissions=True)
		voltage = name + " 24V"
		system_designer_tape_fields.execute()
		self.assertEqual(
			frappe.db.get_value("ilL-Attribute-Output Voltage", voltage, "nominal_voltage_v"), 24
		)
		frappe.db.set_value("ilL-Attribute-Output Voltage", voltage, "nominal_voltage_v", 23.5)
		system_designer_tape_fields.execute()
		self.assertEqual(
			frappe.db.get_value("ilL-Attribute-Output Voltage", voltage, "nominal_voltage_v"), 23.5
		)
