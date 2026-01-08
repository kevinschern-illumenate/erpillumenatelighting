# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestilLExportJob(FrappeTestCase):
	"""Test cases for ilL-Export-Job doctype and export functionality."""

	def setUp(self):
		"""Set up test data."""
		# Create test customer
		if not frappe.db.exists("Customer", "Test Export Customer"):
			customer = frappe.new_doc("Customer")
			customer.customer_name = "Test Export Customer"
			customer.customer_type = "Company"
			customer.insert(ignore_permissions=True)

		# Create test project
		if not frappe.db.exists("ilL-Project", {"project_name": "Test Export Project"}):
			project = frappe.new_doc("ilL-Project")
			project.project_name = "Test Export Project"
			project.customer = "Test Export Customer"
			project.is_private = 0
			project.insert(ignore_permissions=True)
			self.project_name = project.name
		else:
			self.project_name = frappe.db.get_value(
				"ilL-Project", {"project_name": "Test Export Project"}, "name"
			)

		# Create test schedule
		if not frappe.db.exists("ilL-Project-Fixture-Schedule", {"schedule_name": "Test Export Schedule"}):
			schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
			schedule.schedule_name = "Test Export Schedule"
			schedule.ill_project = self.project_name
			schedule.customer = "Test Export Customer"
			schedule.insert(ignore_permissions=True)
			self.schedule_name = schedule.name
		else:
			self.schedule_name = frappe.db.get_value(
				"ilL-Project-Fixture-Schedule", {"schedule_name": "Test Export Schedule"}, "name"
			)

	def test_create_export_job(self):
		"""Test creating an export job."""
		job = frappe.new_doc("ilL-Export-Job")
		job.schedule = self.schedule_name
		job.export_type = "PDF_NO_PRICE"
		job.insert(ignore_permissions=True)

		self.assertIsNotNone(job.name)
		self.assertEqual(job.status, "QUEUED")
		self.assertIsNotNone(job.created_on)
		self.assertIsNotNone(job.requested_by)

	def test_export_job_status_lifecycle(self):
		"""Test export job status lifecycle."""
		job = frappe.new_doc("ilL-Export-Job")
		job.schedule = self.schedule_name
		job.export_type = "CSV_NO_PRICE"
		job.insert(ignore_permissions=True)

		# Initial status should be QUEUED
		self.assertEqual(job.status, "QUEUED")

		# Update to RUNNING
		job.set_status("RUNNING")
		job.reload()
		self.assertEqual(job.status, "RUNNING")

		# Update to COMPLETE with output file
		job.set_status("COMPLETE", output_file="/files/test.csv")
		job.reload()
		self.assertEqual(job.status, "COMPLETE")
		self.assertEqual(job.output_file, "/files/test.csv")

	def test_export_job_failed_status(self):
		"""Test export job failure status."""
		job = frappe.new_doc("ilL-Export-Job")
		job.schedule = self.schedule_name
		job.export_type = "PDF_NO_PRICE"
		job.insert(ignore_permissions=True)

		job.set_status("FAILED", error_log="Test error message")
		job.reload()
		self.assertEqual(job.status, "FAILED")
		self.assertEqual(job.error_log, "Test error message")

	def test_export_types(self):
		"""Test all export types can be created."""
		export_types = ["PDF_PRICED", "PDF_NO_PRICE", "CSV_PRICED", "CSV_NO_PRICE"]

		for export_type in export_types:
			job = frappe.new_doc("ilL-Export-Job")
			job.schedule = self.schedule_name
			job.export_type = export_type
			job.insert(ignore_permissions=True)

			self.assertIsNotNone(job.name)
			self.assertEqual(job.export_type, export_type)

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

