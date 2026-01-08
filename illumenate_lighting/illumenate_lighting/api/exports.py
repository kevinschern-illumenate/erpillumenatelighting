# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Exports API

This module provides API endpoints for generating fixture schedule exports (PDF/CSV)
and Work Order travelers. All exports respect company visibility, private projects,
and pricing permission rules.

Export Types:
- PDF_NO_PRICE: PDF schedule without pricing
- PDF_PRICED: PDF schedule with pricing (requires pricing permission)
- CSV_NO_PRICE: CSV schedule without pricing
- CSV_PRICED: CSV schedule with pricing (requires pricing permission)
"""

import csv
import io
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import now, nowdate
from frappe.utils.file_manager import save_file


# Conversion constant: millimeters per foot
MM_PER_FOOT = 304.8


def _check_schedule_access(schedule_name: str, user: str = None) -> tuple[bool, str | None]:
	"""
	Check if user has access to the schedule based on company/private rules.

	Args:
		schedule_name: Name of the schedule
		user: User to check access for (defaults to current user)

	Returns:
		tuple: (has_access: bool, error_message: str or None)
	"""
	if not user:
		user = frappe.session.user

	if not frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
		return False, _("Schedule not found")

	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Import schedule permission check
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		has_permission,
	)

	if not has_permission(schedule, "read", user):
		return False, _("You don't have permission to access this schedule")

	return True, None


def _check_pricing_permission(user: str = None) -> bool:
	"""
	Check if user has pricing permission.

	Pricing permission is granted to:
	- System Manager role
	- Administrator user
	- Users with 'Can View Pricing' role (custom role)

	Args:
		user: User to check (defaults to current user)

	Returns:
		bool: True if user has pricing permission
	"""
	if not user:
		user = frappe.session.user

	# System Manager and Administrator always have pricing permission
	user_roles = frappe.get_roles(user)
	if "System Manager" in user_roles or user == "Administrator":
		return True

	# Check for custom pricing permission role
	if "Can View Pricing" in user_roles:
		return True

	# Default: portal users without special roles cannot see pricing
	return False


def _create_export_job(schedule_name: str, export_type: str, user: str = None) -> str:
	"""
	Create an ilL-Export-Job record for tracking export requests.

	Args:
		schedule_name: Name of the schedule being exported
		export_type: Type of export (PDF_PRICED, PDF_NO_PRICE, CSV_PRICED, CSV_NO_PRICE)
		user: User requesting the export (defaults to current user)

	Returns:
		str: Name of the created export job
	"""
	if not user:
		user = frappe.session.user

	job = frappe.new_doc("ilL-Export-Job")
	job.schedule = schedule_name
	job.export_type = export_type
	job.status = "QUEUED"
	job.requested_by = user
	job.created_on = now()
	job.insert(ignore_permissions=True)

	return job.name


def _update_export_job_status(
	job_name: str, status: str, output_file: str | None = None, error_log: str | None = None
):
	"""
	Update an export job's status and optionally attach output or error.

	Args:
		job_name: Name of the export job
		status: New status (RUNNING, COMPLETE, FAILED)
		output_file: URL of the output file (for COMPLETE status)
		error_log: Error message (for FAILED status)
	"""
	job = frappe.get_doc("ilL-Export-Job", job_name)
	job.status = status
	if output_file:
		job.output_file = output_file
	if error_log:
		job.error_log = error_log
	job.save(ignore_permissions=True)


def _get_schedule_data(schedule_name: str, include_pricing: bool = False) -> dict:
	"""
	Gather all data needed for schedule exports.

	Args:
		schedule_name: Name of the schedule
		include_pricing: Whether to include pricing data

	Returns:
		dict: Schedule data including project, customer, lines, and optionally pricing
	"""
	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

	# Get project info
	project = None
	if schedule.ill_project:
		project = frappe.get_doc("ilL-Project", schedule.ill_project)

	# Get customer info
	customer = None
	if schedule.customer:
		customer = frappe.get_doc("Customer", schedule.customer)

	# Pre-fetch all configured fixtures to avoid N+1 queries
	fixture_ids = [
		line.configured_fixture
		for line in (schedule.lines or [])
		if line.manufacturer_type == "ILLUMENATE" and line.configured_fixture
	]

	fixtures_map = {}
	if fixture_ids:
		fixtures = frappe.get_all(
			"ilL-Configured-Fixture",
			filters={"name": ["in", fixture_ids]},
			fields=[
				"name", "fixture_template", "finish", "lens_appearance",
				"mounting_method", "power_feed_type", "environment_rating",
				"requested_overall_length_mm", "manufacturable_overall_length_mm",
				"runs_count",
			],
		)
		for f in fixtures:
			fixtures_map[f.name] = f

		# If we need pricing, fetch pricing snapshots separately
		if include_pricing:
			for fixture_id in fixture_ids:
				if fixture_id in fixtures_map:
					# Get the latest pricing snapshot
					snapshots = frappe.get_all(
						"ilL-Child-Pricing-Snapshot",
						filters={"parent": fixture_id, "parenttype": "ilL-Configured-Fixture"},
						fields=["msrp_unit"],
						order_by="timestamp desc",
						limit=1,
					)
					if snapshots:
						fixtures_map[fixture_id]["latest_msrp_unit"] = float(snapshots[0].msrp_unit or 0)

	# Build lines data
	lines_data = []
	schedule_total = 0.0

	for line in schedule.lines or []:
		line_data = {
			"line_id": line.line_id or str(line.idx),
			"qty": line.qty or 1,
			"location": line.location or "",
			"manufacturer_type": line.manufacturer_type or "ILLUMENATE",
			"notes": line.notes or "",
		}

		if line.manufacturer_type == "ILLUMENATE" and line.configured_fixture:
			# Get configured fixture details from pre-fetched map
			fixture = fixtures_map.get(line.configured_fixture)
			if fixture:
				line_data["template_code"] = fixture.fixture_template or ""
				line_data["config_summary"] = _build_config_summary_from_dict(fixture)
				line_data["requested_length_mm"] = fixture.requested_overall_length_mm or 0
				line_data["manufacturable_length_mm"] = fixture.manufacturable_overall_length_mm or 0
				line_data["runs_count"] = fixture.runs_count or 0

				if include_pricing and fixture.get("latest_msrp_unit"):
					unit_price = fixture["latest_msrp_unit"]
					line_data["unit_price"] = unit_price
					line_data["line_total"] = unit_price * (line.qty or 1)
					schedule_total += line_data["line_total"]
			else:
				line_data["template_code"] = ""
				line_data["config_summary"] = "Configured fixture not found"
				line_data["requested_length_mm"] = 0
				line_data["manufacturable_length_mm"] = line.manufacturable_length_mm or 0
				line_data["runs_count"] = 0
		else:
			# Other manufacturer line
			line_data["template_code"] = ""
			line_data["config_summary"] = ""
			line_data["requested_length_mm"] = 0
			line_data["manufacturable_length_mm"] = 0
			line_data["runs_count"] = 0
			line_data["manufacturer_name"] = line.manufacturer_name or ""
			line_data["model_number"] = line.model_number or ""
			line_data["attachments"] = line.attachments or ""

		lines_data.append(line_data)

	return {
		"schedule": schedule,
		"project": project,
		"customer": customer,
		"lines": lines_data,
		"schedule_total": schedule_total if include_pricing else None,
		"export_date": nowdate(),
	}


def _build_config_summary(fixture) -> str:
	"""Build a summary string of fixture configuration options from a document."""
	parts = []

	if fixture.finish:
		parts.append(f"Finish: {fixture.finish}")
	if fixture.lens_appearance:
		parts.append(f"Lens: {fixture.lens_appearance}")
	if fixture.mounting_method:
		parts.append(f"Mount: {fixture.mounting_method}")
	if fixture.power_feed_type:
		parts.append(f"Feed: {fixture.power_feed_type}")
	if fixture.environment_rating:
		parts.append(f"Env: {fixture.environment_rating}")

	return " | ".join(parts) if parts else ""


def _build_config_summary_from_dict(fixture: dict) -> str:
	"""Build a summary string of fixture configuration options from a dict."""
	parts = []

	if fixture.get("finish"):
		parts.append(f"Finish: {fixture['finish']}")
	if fixture.get("lens_appearance"):
		parts.append(f"Lens: {fixture['lens_appearance']}")
	if fixture.get("mounting_method"):
		parts.append(f"Mount: {fixture['mounting_method']}")
	if fixture.get("power_feed_type"):
		parts.append(f"Feed: {fixture['power_feed_type']}")
	if fixture.get("environment_rating"):
		parts.append(f"Env: {fixture['environment_rating']}")

	return " | ".join(parts) if parts else ""


def _generate_pdf_content(schedule_data: dict, include_pricing: bool = False) -> str:
	"""
	Generate HTML content for PDF export.

	Args:
		schedule_data: Data from _get_schedule_data
		include_pricing: Whether to include pricing columns

	Returns:
		str: HTML content for PDF rendering
	"""
	schedule = schedule_data["schedule"]
	project = schedule_data["project"]
	customer = schedule_data["customer"]
	lines = schedule_data["lines"]

	# Build header
	html_parts = [
		"<html><head><style>",
		"body { font-family: Arial, sans-serif; font-size: 11px; }",
		"h1 { font-size: 18px; margin-bottom: 5px; }",
		"h2 { font-size: 14px; color: #555; margin-top: 0; }",
		".header-info { margin-bottom: 20px; }",
		".header-info p { margin: 2px 0; }",
		"table { width: 100%; border-collapse: collapse; margin-top: 10px; }",
		"th, td { border: 1px solid #ccc; padding: 6px; text-align: left; }",
		"th { background-color: #f5f5f5; font-weight: bold; }",
		".text-right { text-align: right; }",
		".total-row { font-weight: bold; background-color: #f0f0f0; }",
		".other-manufacturer { background-color: #fffbe6; }",
		"</style></head><body>",
	]

	# Header section
	html_parts.append("<div class='header-info'>")
	html_parts.append(f"<h1>{schedule.schedule_name}</h1>")
	if project:
		html_parts.append(f"<h2>Project: {project.project_name}</h2>")
	if customer:
		customer_name = customer.customer_name or customer.name
		html_parts.append(f"<p><strong>Customer:</strong> {customer_name}</p>")
	html_parts.append(f"<p><strong>Date:</strong> {schedule_data['export_date']}</p>")
	html_parts.append(f"<p><strong>Status:</strong> {schedule.status}</p>")
	html_parts.append("</div>")

	# Table header
	html_parts.append("<table>")
	html_parts.append("<thead><tr>")
	html_parts.append("<th>Line ID</th>")
	html_parts.append("<th>Type</th>")
	html_parts.append("<th>Qty</th>")
	html_parts.append("<th>Location</th>")
	html_parts.append("<th>Description</th>")
	html_parts.append("<th>Req. Length (mm)</th>")
	html_parts.append("<th>Mfg. Length (mm)</th>")
	html_parts.append("<th>Notes</th>")
	if include_pricing:
		html_parts.append("<th class='text-right'>Unit Price</th>")
		html_parts.append("<th class='text-right'>Line Total</th>")
	html_parts.append("</tr></thead>")

	# Table body
	html_parts.append("<tbody>")
	for line in lines:
		row_class = "other-manufacturer" if line["manufacturer_type"] == "OTHER" else ""
		html_parts.append(f"<tr class='{row_class}'>")
		html_parts.append(f"<td>{line['line_id']}</td>")
		html_parts.append(f"<td>{line['manufacturer_type']}</td>")
		html_parts.append(f"<td>{line['qty']}</td>")
		html_parts.append(f"<td>{line['location']}</td>")

		# Description column
		if line["manufacturer_type"] == "ILLUMENATE":
			description = f"{line['template_code']}"
			if line["config_summary"]:
				description += f"<br><small>{line['config_summary']}</small>"
		else:
			description = f"{line.get('manufacturer_name', '')} {line.get('model_number', '')}"
			if line.get("attachments"):
				description += f"<br><small>Attachments: {line['attachments']}</small>"

		html_parts.append(f"<td>{description}</td>")
		html_parts.append(f"<td>{line['requested_length_mm']}</td>")
		html_parts.append(f"<td>{line['manufacturable_length_mm']}</td>")
		html_parts.append(f"<td>{line['notes']}</td>")

		if include_pricing:
			unit_price = line.get("unit_price", 0)
			line_total = line.get("line_total", 0)
			html_parts.append(f"<td class='text-right'>${unit_price:.2f}</td>")
			html_parts.append(f"<td class='text-right'>${line_total:.2f}</td>")

		html_parts.append("</tr>")

	# Total row for priced exports
	if include_pricing:
		schedule_total = schedule_data.get("schedule_total", 0)
		colspan = 9
		html_parts.append(f"<tr class='total-row'>")
		html_parts.append(f"<td colspan='{colspan}' class='text-right'>Schedule Total:</td>")
		html_parts.append(f"<td class='text-right'>${schedule_total:.2f}</td>")
		html_parts.append("</tr>")

	html_parts.append("</tbody></table>")
	html_parts.append("</body></html>")

	return "".join(html_parts)


def _generate_csv_content(schedule_data: dict, include_pricing: bool = False) -> str:
	"""
	Generate CSV content for schedule export.

	Args:
		schedule_data: Data from _get_schedule_data
		include_pricing: Whether to include pricing columns

	Returns:
		str: CSV content
	"""
	schedule = schedule_data["schedule"]
	project = schedule_data["project"]
	lines = schedule_data["lines"]

	output = io.StringIO()
	writer = csv.writer(output)

	# Header row
	headers = [
		"Project",
		"Schedule",
		"Line ID",
		"Manufacturer Type",
		"Qty",
		"Location",
		"Template Code / Config Summary",
		"Requested Length (mm)",
		"Manufacturable Length (mm)",
		"Runs Count",
		"Notes",
		"Manufacturer Name",
		"Model Number",
	]
	if include_pricing:
		headers.extend(["Unit Price", "Line Total"])

	writer.writerow(headers)

	# Data rows
	project_name = project.project_name if project else ""
	schedule_name = schedule.schedule_name

	for line in lines:
		row = [
			project_name,
			schedule_name,
			line["line_id"],
			line["manufacturer_type"],
			line["qty"],
			line["location"],
			f"{line['template_code']} {line['config_summary']}".strip(),
			line["requested_length_mm"],
			line["manufacturable_length_mm"],
			line.get("runs_count", ""),
			line["notes"],
			line.get("manufacturer_name", ""),
			line.get("model_number", ""),
		]
		if include_pricing:
			row.extend([
				f"{line.get('unit_price', 0):.2f}",
				f"{line.get('line_total', 0):.2f}",
			])
		writer.writerow(row)

	# Summary row for priced exports
	if include_pricing:
		schedule_total = schedule_data.get("schedule_total", 0)
		summary_row = [""] * (len(headers) - 1) + [f"{schedule_total:.2f}"]
		summary_row[0] = "SCHEDULE TOTAL"
		writer.writerow(summary_row)

	return output.getvalue()


@frappe.whitelist()
def generate_schedule_pdf(schedule_id: str, priced: bool = False) -> dict:
	"""
	Generate a PDF export of a fixture schedule.

	Args:
		schedule_id: Name of the ilL-Project-Fixture-Schedule
		priced: Whether to include pricing (requires pricing permission)

	Returns:
		dict: {
			"success": bool,
			"export_job": str (job name),
			"download_url": str (file URL),
			"error": str (if failed)
		}
	"""
	priced = frappe.parse_json(priced) if isinstance(priced, str) else priced

	# Check schedule access
	has_access, error = _check_schedule_access(schedule_id)
	if not has_access:
		return {"success": False, "error": error}

	# Check pricing permission if requesting priced export
	if priced and not _check_pricing_permission():
		return {"success": False, "error": _("You don't have permission to view pricing")}

	export_type = "PDF_PRICED" if priced else "PDF_NO_PRICE"

	# Create export job
	job_name = _create_export_job(schedule_id, export_type)

	try:
		# Update status to RUNNING
		_update_export_job_status(job_name, "RUNNING")

		# Gather schedule data
		schedule_data = _get_schedule_data(schedule_id, include_pricing=priced)

		# Generate PDF content
		html_content = _generate_pdf_content(schedule_data, include_pricing=priced)

		# Generate PDF using frappe's PDF generator
		from frappe.utils.pdf import get_pdf

		pdf_content = get_pdf(html_content)

		# Generate filename
		schedule = schedule_data["schedule"]
		timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
		price_suffix = "_priced" if priced else "_no_price"
		filename = f"{schedule.schedule_name}{price_suffix}_{timestamp}.pdf"

		# Save file
		file_doc = save_file(
			filename,
			pdf_content,
			"ilL-Export-Job",
			job_name,
			is_private=0,
		)

		# Update job with output file
		_update_export_job_status(job_name, "COMPLETE", output_file=file_doc.file_url)

		return {
			"success": True,
			"export_job": job_name,
			"download_url": file_doc.file_url,
		}

	except Exception as e:
		# Log error and update job status
		error_msg = str(e)
		frappe.log_error(f"PDF Export Error for {schedule_id}: {error_msg}")
		_update_export_job_status(job_name, "FAILED", error_log=error_msg)
		return {"success": False, "export_job": job_name, "error": error_msg}


@frappe.whitelist()
def generate_schedule_csv(schedule_id: str, priced: bool = False) -> dict:
	"""
	Generate a CSV export of a fixture schedule.

	Args:
		schedule_id: Name of the ilL-Project-Fixture-Schedule
		priced: Whether to include pricing (requires pricing permission)

	Returns:
		dict: {
			"success": bool,
			"export_job": str (job name),
			"download_url": str (file URL),
			"error": str (if failed)
		}
	"""
	priced = frappe.parse_json(priced) if isinstance(priced, str) else priced

	# Check schedule access
	has_access, error = _check_schedule_access(schedule_id)
	if not has_access:
		return {"success": False, "error": error}

	# Check pricing permission if requesting priced export
	if priced and not _check_pricing_permission():
		return {"success": False, "error": _("You don't have permission to view pricing")}

	export_type = "CSV_PRICED" if priced else "CSV_NO_PRICE"

	# Create export job
	job_name = _create_export_job(schedule_id, export_type)

	try:
		# Update status to RUNNING
		_update_export_job_status(job_name, "RUNNING")

		# Gather schedule data
		schedule_data = _get_schedule_data(schedule_id, include_pricing=priced)

		# Generate CSV content
		csv_content = _generate_csv_content(schedule_data, include_pricing=priced)

		# Generate filename
		schedule = schedule_data["schedule"]
		timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
		price_suffix = "_priced" if priced else "_no_price"
		filename = f"{schedule.schedule_name}{price_suffix}_{timestamp}.csv"

		# Save file
		file_doc = save_file(
			filename,
			csv_content.encode("utf-8"),
			"ilL-Export-Job",
			job_name,
			is_private=0,
		)

		# Update job with output file
		_update_export_job_status(job_name, "COMPLETE", output_file=file_doc.file_url)

		return {
			"success": True,
			"export_job": job_name,
			"download_url": file_doc.file_url,
		}

	except Exception as e:
		# Log error and update job status
		error_msg = str(e)
		frappe.log_error(f"CSV Export Error for {schedule_id}: {error_msg}")
		_update_export_job_status(job_name, "FAILED", error_log=error_msg)
		return {"success": False, "export_job": job_name, "error": error_msg}


@frappe.whitelist()
def get_export_history(schedule_id: str) -> dict:
	"""
	Get export history for a schedule.

	Args:
		schedule_id: Name of the ilL-Project-Fixture-Schedule

	Returns:
		dict: {
			"success": bool,
			"exports": list of export job dicts,
			"error": str (if failed)
		}
	"""
	# Check schedule access
	has_access, error = _check_schedule_access(schedule_id)
	if not has_access:
		return {"success": False, "error": error}

	# Get user pricing permission
	can_view_pricing = _check_pricing_permission()

	# Query export jobs for this schedule
	filters = {"schedule": schedule_id}
	if not can_view_pricing:
		# Filter out priced exports for users without pricing permission
		filters["export_type"] = ["in", ["PDF_NO_PRICE", "CSV_NO_PRICE"]]

	exports = frappe.get_all(
		"ilL-Export-Job",
		filters=filters,
		fields=["name", "export_type", "status", "requested_by", "created_on", "output_file"],
		order_by="created_on desc",
		limit=50,
	)

	# Batch fetch user names to avoid N+1 queries
	user_ids = list({exp.requested_by for exp in exports if exp.requested_by})
	user_names_map = {}
	if user_ids:
		users = frappe.get_all(
			"User",
			filters={"name": ["in", user_ids]},
			fields=["name", "full_name"],
		)
		user_names_map = {u.name: u.full_name for u in users}

	# Enrich with user display name
	for export in exports:
		if export.requested_by:
			export["requested_by_name"] = user_names_map.get(export.requested_by) or export.requested_by
		else:
			export["requested_by_name"] = ""

	return {
		"success": True,
		"exports": exports,
		"can_view_pricing": can_view_pricing,
	}


@frappe.whitelist()
def check_pricing_permission() -> dict:
	"""
	Check if current user has pricing permission.

	Returns:
		dict: {"has_permission": bool}
	"""
	return {"has_permission": _check_pricing_permission()}
