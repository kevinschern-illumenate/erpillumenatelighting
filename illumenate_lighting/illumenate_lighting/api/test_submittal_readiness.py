# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Installed-site checks for spec submittal readiness: the queries and dry runs work on a real schema."""

import frappe
from frappe.tests import IntegrationTestCase

from illumenate_lighting.illumenate_lighting.api import submittal_readiness


class TestSubmittalReadiness(IntegrationTestCase):
	def test_report_runs_for_every_template_type(self):
		frappe.set_user("Administrator")
		data = submittal_readiness.get_report()
		self.assertEqual(data["summary"]["total"], len(data["rows"]))
		for row in data["rows"]:
			self.assertIn(row["kind"], submittal_readiness.KINDS)
			self.assertIn(
				row["status"], (submittal_readiness.STATUS_READY, submittal_readiness.STATUS_INCOMPLETE)
			)
			self.assertIsInstance(row["lines"], int)

	def test_mapping_doctypes_have_the_fields_the_dry_run_reads(self):
		for cfg in submittal_readiness.KINDS.values():
			meta = frappe.get_meta(cfg["mapping"])
			for field in (cfg["link"], "pdf_field_name", "source_doctype", "source_field", "required_value"):
				self.assertTrue(meta.has_field(field), f"{cfg['mapping']}.{field}")
			self.assertTrue(frappe.get_meta(cfg["doctype"]).has_field("spec_submittal_template"))
			if "build" in cfg:
				doctype, template_field, line_field = cfg["build"]
				self.assertTrue(frappe.get_meta(doctype).has_field(template_field))
				self.assertTrue(frappe.get_meta(submittal_readiness.LINE).has_field(line_field))

	def test_dry_run_of_every_template_saves_nothing(self):
		frappe.set_user("Administrator")
		files = frappe.db.count("File")
		result = submittal_readiness.audit()
		self.assertGreaterEqual(result["tested"], result["failed"])
		self.assertEqual(frappe.db.count("File"), files)
		self.assertIsNone(frappe.flags.get("ill_submittal_dry_run"))

	def test_page_is_installed(self):
		self.assertTrue(frappe.db.exists("Page", "submittal-readiness"))
