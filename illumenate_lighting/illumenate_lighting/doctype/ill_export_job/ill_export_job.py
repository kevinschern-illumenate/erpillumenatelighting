# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now


class ilLExportJob(Document):
	def before_insert(self):
		"""Set defaults before insert."""
		if not self.created_on:
			self.created_on = now()
		if not self.requested_by:
			self.requested_by = frappe.session.user
		if not self.status:
			self.status = "QUEUED"

	def validate(self):
		"""Validate export job data."""
		self._validate_schedule_access()
		self._validate_pricing_permission()

	def _validate_schedule_access(self):
		"""Validate that the requesting user has access to the schedule."""
		if not self.schedule:
			frappe.throw(_("Schedule is required"))

		# Import schedule permission check
		from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
			has_permission,
		)

		schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", self.schedule)
		if not has_permission(schedule, "read", self.requested_by):
			frappe.throw(_("You don't have permission to export this schedule"))

	def _validate_pricing_permission(self):
		"""Validate pricing permission for priced exports."""
		if self.export_type in ["PDF_PRICED", "CSV_PRICED"]:
			from illumenate_lighting.illumenate_lighting.api.exports import (
				_check_pricing_permission,
			)

			if not _check_pricing_permission(self.requested_by):
				frappe.throw(_("You don't have permission to generate priced exports"))

	def set_status(self, status: str, output_file: str | None = None, error_log: str | None = None):
		"""
		Update the export job status.

		Args:
			status: New status (RUNNING, COMPLETE, FAILED)
			output_file: URL of the output file (for COMPLETE status)
			error_log: Error message (for FAILED status)
		"""
		self.status = status
		if output_file:
			self.output_file = output_file
		if error_log:
			self.error_log = error_log
		self.save(ignore_permissions=True)

