# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Installed-site checks for the System Designer role, capability and Settings (WP-0.5)."""

import frappe
from frappe.tests import IntegrationTestCase

from illumenate_lighting.illumenate_lighting.system_design import settings as designer_settings


class TestSystemDesignerSettings(IntegrationTestCase):
	def test_role_exists_and_holds_design_review(self):
		self.assertTrue(frappe.db.exists("Role", "ilL Applications Engineer"))
		from illumenate_lighting.illumenate_lighting.portal.staff import CAPABILITIES

		self.assertEqual(CAPABILITIES["design_review"], {"ilL Applications Engineer"})

	def test_defaults_match_the_decisions(self):
		meta = frappe.get_meta(designer_settings.DOCTYPE)
		for field, expected in designer_settings.DEFAULTS.items():
			with self.subTest(field=field):
				self.assertEqual(designer_settings._coerce(expected, meta.get_field(field).default), expected)
		values = designer_settings.settings()
		self.assertEqual(
			(
				values.vd_target_class2_pct,
				values.vd_target_line_pct,
				values.vd_target_landscape_pct,
				values.review_gate_watts,
				values.share_default_days,
				values.share_max_days,
			),
			(3.0, 3.0, 5.0, 1500.0, 90, 90),
		)

	def test_settings_validation_rejects_loose_values(self):
		doc = frappe.get_single(designer_settings.DOCTYPE)
		doc.share_default_days = 120
		self.assertRaises(frappe.ValidationError, doc.validate)
