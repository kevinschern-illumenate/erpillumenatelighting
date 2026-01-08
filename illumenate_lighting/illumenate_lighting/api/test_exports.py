# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Tests for Exports API
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestExportsAPI(FrappeTestCase):
	"""Test cases for the exports API."""

	def setUp(self):
		"""Set up test data."""
		# Create test customer
		if not frappe.db.exists("Customer", "Test Exports API Customer"):
			customer = frappe.new_doc("Customer")
			customer.customer_name = "Test Exports API Customer"
			customer.customer_type = "Company"
			customer.insert(ignore_permissions=True)

		# Create test project
		if not frappe.db.exists("ilL-Project", {"project_name": "Test Exports API Project"}):
			project = frappe.new_doc("ilL-Project")
			project.project_name = "Test Exports API Project"
			project.customer = "Test Exports API Customer"
			project.is_private = 0
			project.insert(ignore_permissions=True)
			self.project_name = project.name
		else:
			self.project_name = frappe.db.get_value(
				"ilL-Project", {"project_name": "Test Exports API Project"}, "name"
			)

		# Create test schedule with lines
		if not frappe.db.exists(
			"ilL-Project-Fixture-Schedule", {"schedule_name": "Test Exports API Schedule"}
		):
			schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
			schedule.schedule_name = "Test Exports API Schedule"
			schedule.ill_project = self.project_name
			schedule.customer = "Test Exports API Customer"
			schedule.append(
				"lines",
				{
					"line_id": "A",
					"qty": 2,
					"location": "Test Location",
					"manufacturer_type": "OTHER",
					"manufacturer_name": "Test Manufacturer",
					"model_number": "TM-100",
					"notes": "Test notes",
				},
			)
			schedule.insert(ignore_permissions=True)
			self.schedule_name = schedule.name
		else:
			self.schedule_name = frappe.db.get_value(
				"ilL-Project-Fixture-Schedule",
				{"schedule_name": "Test Exports API Schedule"},
				"name",
			)

	def test_check_schedule_access(self):
		"""Test schedule access check."""
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_check_schedule_access,
		)

		# Valid schedule with admin user should have access
		has_access, error = _check_schedule_access(self.schedule_name, "Administrator")
		self.assertTrue(has_access)
		self.assertIsNone(error)

		# Non-existent schedule should fail
		has_access, error = _check_schedule_access("NON-EXISTENT-SCHEDULE", "Administrator")
		self.assertFalse(has_access)
		self.assertIsNotNone(error)

	def test_check_pricing_permission_admin(self):
		"""Test pricing permission for admin user."""
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_check_pricing_permission,
		)

		# Administrator should have pricing permission
		has_permission = _check_pricing_permission("Administrator")
		self.assertTrue(has_permission)

	def test_create_export_job_function(self):
		"""Test _create_export_job function."""
		from illumenate_lighting.illumenate_lighting.api.exports import _create_export_job

		job_name = _create_export_job(
			self.schedule_name, "PDF_NO_PRICE", "Administrator"
		)

		self.assertIsNotNone(job_name)

		# Verify job was created
		job = frappe.get_doc("ilL-Export-Job", job_name)
		self.assertEqual(job.schedule, self.schedule_name)
		self.assertEqual(job.export_type, "PDF_NO_PRICE")
		self.assertEqual(job.status, "QUEUED")

	def test_get_schedule_data(self):
		"""Test _get_schedule_data function."""
		from illumenate_lighting.illumenate_lighting.api.exports import _get_schedule_data

		data = _get_schedule_data(self.schedule_name, include_pricing=False)

		self.assertIsNotNone(data)
		self.assertIn("schedule", data)
		self.assertIn("project", data)
		self.assertIn("customer", data)
		self.assertIn("lines", data)
		self.assertIn("export_date", data)

		# Verify lines data
		self.assertEqual(len(data["lines"]), 1)
		line = data["lines"][0]
		self.assertEqual(line["line_id"], "A")
		self.assertEqual(line["qty"], 2)
		self.assertEqual(line["manufacturer_type"], "OTHER")

	def test_generate_csv_content(self):
		"""Test _generate_csv_content function."""
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_generate_csv_content,
			_get_schedule_data,
		)

		schedule_data = _get_schedule_data(self.schedule_name, include_pricing=False)
		csv_content = _generate_csv_content(schedule_data, include_pricing=False)

		self.assertIsNotNone(csv_content)
		self.assertIn("Project", csv_content)
		self.assertIn("Schedule", csv_content)
		self.assertIn("Line ID", csv_content)
		self.assertIn("Test Manufacturer", csv_content)
		self.assertIn("TM-100", csv_content)

	def test_generate_pdf_content(self):
		"""Test _generate_pdf_content function."""
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_generate_pdf_content,
			_get_schedule_data,
		)

		schedule_data = _get_schedule_data(self.schedule_name, include_pricing=False)
		html_content = _generate_pdf_content(schedule_data, include_pricing=False)

		self.assertIsNotNone(html_content)
		self.assertIn("<html>", html_content)
		self.assertIn("Test Exports API Schedule", html_content)
		self.assertIn("Test Manufacturer", html_content)

	def test_get_export_history(self):
		"""Test get_export_history function."""
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_create_export_job,
			get_export_history,
		)

		# Create some export jobs
		_create_export_job(self.schedule_name, "PDF_NO_PRICE", "Administrator")
		_create_export_job(self.schedule_name, "CSV_NO_PRICE", "Administrator")

		# Get export history
		result = get_export_history(self.schedule_name)

		self.assertTrue(result["success"])
		self.assertIn("exports", result)
		self.assertGreaterEqual(len(result["exports"]), 2)

	def test_check_pricing_permission_endpoint(self):
		"""Test check_pricing_permission endpoint."""
		from illumenate_lighting.illumenate_lighting.api.exports import (
			check_pricing_permission,
		)

		result = check_pricing_permission()

		self.assertIn("has_permission", result)
		# Admin should have permission
		self.assertTrue(result["has_permission"])

	def tearDown(self):
		"""Clean up test data."""
		# Delete test export jobs
		test_jobs = frappe.get_all(
			"ilL-Export-Job",
			filters={"schedule": self.schedule_name},
			pluck="name",
		)
		for job_name in test_jobs:
			frappe.delete_doc("ilL-Export-Job", job_name, force=True)
