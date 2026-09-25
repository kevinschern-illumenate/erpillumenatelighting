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
		old = self.get_doc_before_save()
		if any(self.get(field) != (old.get(field) if old else None) for field in ("issued_on", "issued_by")):
			frappe.throw(_("Use the verified packet issue action; issuance metadata is immutable."))
		if old and old.get("manifest_json"):
			for field in ("manifest_json", "snapshot_json", "source_revision", "manifest_schema_version", "schedule", "requested_by", "export_type"):
				if self.get(field) != old.get(field):
					frappe.throw(_("Packet source snapshots are immutable. Generate a new packet."))
		if old and old.status in ("COMPLETE", "INCOMPLETE"):
			for field in ("status", "output_file", "output_sha256"):
				if self.get(field) != old.get(field):
					frappe.throw(_("Completed packet output is immutable."))
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


def get_permission_query_conditions(user=None):
	"""An export always follows current schedule and pricing access, including its owner."""
	from illumenate_lighting.illumenate_lighting.api.exports import _check_pricing_permission
	from illumenate_lighting.illumenate_lighting.portal.access import schedule_query_conditions

	user = user or frappe.session.user
	if user == "Guest":
		return "1=0"
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if allowed("engineering", user):
		return "`tabilL-Export-Job`.export_type NOT IN ('PDF_PRICED', 'CSV_PRICED')"
	predicate = schedule_query_conditions(user) or "1=1"
	conditions = [f"`tabilL-Export-Job`.schedule IN (SELECT name FROM `tabilL-Project-Fixture-Schedule` WHERE {predicate})"]
	if not _check_pricing_permission(user):
		conditions.append("`tabilL-Export-Job`.export_type NOT IN ('PDF_PRICED', 'CSV_PRICED')")
	return " AND ".join(f"({condition})" for condition in conditions)


def has_permission(doc, ptype="read", user=None):
	from illumenate_lighting.illumenate_lighting.api.exports import _check_pricing_permission
	from illumenate_lighting.illumenate_lighting.portal.access import can_read_schedule

	user = user or frappe.session.user
	if user == "Guest":
		return False
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return True
	if ptype not in ("read", "select", "print", "export"):
		return False
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if allowed("engineering", user) and doc.export_type not in ("PDF_PRICED", "CSV_PRICED"):
		return True
	if doc.export_type in ("PDF_PRICED", "CSV_PRICED") and not _check_pricing_permission(user):
		return False
	try:
		return can_read_schedule(frappe.get_doc("ilL-Project-Fixture-Schedule", doc.schedule), user)
	except frappe.DoesNotExistError:
		return False
