# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Installed-site checks for the design readiness report (WP-1.7): the queries run on a real schema."""

import frappe
from frappe.tests import IntegrationTestCase

from illumenate_lighting.illumenate_lighting.system_design import readiness


class TestDesignReadiness(IntegrationTestCase):
	def test_report_runs_for_every_product_type(self):
		frappe.set_user("Administrator")
		data = readiness.get_report()
		self.assertEqual(data["volume_days"], readiness.VOLUME_DAYS)
		for row in data["rows"]:
			self.assertIn(row["product_type"], readiness.PRODUCT_TYPES)
			self.assertIn(
				row["status"], (readiness.STATUS_READY, readiness.STATUS_INCOMPLETE, "not modelled")
			)
			self.assertIsInstance(row["volume"], int)
			self.assertNotIn("cost", row)
		counts = readiness.volumes()
		self.assertEqual(set(counts), {"tape", "item"})

	def test_page_is_installed(self):
		self.assertTrue(frappe.db.exists("Page", "design-readiness"))
