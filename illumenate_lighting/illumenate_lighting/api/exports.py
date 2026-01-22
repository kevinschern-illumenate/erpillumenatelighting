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
	- Users with 'Dealer' role

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

	# Dealers have pricing permission
	if "Dealer" in user_roles:
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


def _get_fixture_export_details(configured_fixture_id: str) -> dict:
	"""
	Get fixture details for export.

	Args:
		configured_fixture_id: Name of the ilL-Configured-Fixture

	Returns:
		dict: Fixture details including cct, cri, estimated_delivered_output, power_supply,
		       fixture_input_voltage, driver_input_voltage, total_watts
	"""
	try:
		cf = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_id)
		details = {
			"total_watts": cf.total_watts if hasattr(cf, "total_watts") else None,
			"estimated_delivered_output": cf.estimated_delivered_output if hasattr(cf, "estimated_delivered_output") else None,
		}

		# Get lens transmission as decimal for output calculation (0.56 = 56%)
		lens_transmission = 1.0
		if cf.lens_appearance:
			lens_doc = frappe.db.get_value(
				"ilL-Attribute-Lens Appearance",
				cf.lens_appearance,
				["transmission"],
				as_dict=True,
			)
			if lens_doc and lens_doc.transmission:
				lens_transmission = lens_doc.transmission

		# Get tape offering details (CCT, CRI, Output Level, Input Voltage)
		if cf.tape_offering:
			tape_offering = frappe.db.get_value(
				"ilL-Rel-Tape Offering",
				cf.tape_offering,
				["cct", "output_level", "tape_spec", "cri"],
				as_dict=True,
			)
			if tape_offering:
				details["cct"] = tape_offering.cct or ""

				# Get CRI display value
				if tape_offering.cri:
					cri_doc = frappe.db.get_value(
						"ilL-Attribute-CRI",
						tape_offering.cri,
						["cri_name"],
						as_dict=True,
					)
					if cri_doc:
						details["cri"] = cri_doc.cri_name or tape_offering.cri
					else:
						details["cri"] = tape_offering.cri

				# Get lumens per foot and input voltage from tape spec
				if tape_offering.tape_spec:
					tape_spec_data = frappe.db.get_value(
						"ilL-Spec-LED Tape",
						tape_offering.tape_spec,
						["lumens_per_foot", "input_voltage"],
						as_dict=True,
					)
					if tape_spec_data:
						# Calculate delivered output if not already stored on fixture
						if not details.get("estimated_delivered_output") and tape_spec_data.lumens_per_foot:
							delivered = tape_spec_data.lumens_per_foot * lens_transmission
							details["estimated_delivered_output"] = round(delivered, 1)
						# Get fixture input voltage (tape voltage)
						if tape_spec_data.input_voltage:
							details["fixture_input_voltage"] = tape_spec_data.input_voltage

				# Get output level display name (for reference only)
				if tape_offering.output_level:
					output_level_doc = frappe.db.get_value(
						"ilL-Attribute-Output Level",
						tape_offering.output_level,
						["output_level_name"],
						as_dict=True,
					)
					if output_level_doc:
						details["output_level"] = output_level_doc.output_level_name

		# Get power supply info from drivers child table
		if cf.drivers:
			driver_items = []
			driver_input_voltages = []
			for driver_alloc in cf.drivers:
				if driver_alloc.driver_item:
					# Get driver spec for input voltage
					driver_spec = frappe.db.get_value(
						"ilL-Spec-Driver",
						{"item": driver_alloc.driver_item},
						["input_voltage"],
						as_dict=True,
					)

					driver_qty = driver_alloc.driver_qty or 1
					if driver_qty > 1:
						driver_items.append(f"{driver_alloc.driver_item} ({driver_qty})")
					else:
						driver_items.append(driver_alloc.driver_item)

					# Collect driver input voltage
					if driver_spec and driver_spec.input_voltage:
						driver_input_voltages.append(driver_spec.input_voltage)

			if driver_items:
				details["power_supply"] = ", ".join(driver_items)
			if driver_input_voltages:
				# Remove duplicates and join
				unique_voltages = list(dict.fromkeys(driver_input_voltages))
				details["driver_input_voltage"] = ", ".join(unique_voltages)

		return details
	except Exception:
		return {}


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
				"runs_count", "tape_offering",
			],
		)
		for f in fixtures:
			fixtures_map[f.name] = f

		# Fetch additional fixture details (CCT, CRI, Output, Power Supply)
		for fixture_id in fixture_ids:
			if fixture_id in fixtures_map:
				fixture_details = _get_fixture_export_details(fixture_id)
				fixtures_map[fixture_id].update(fixture_details)

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
				line_data["configured_fixture_name"] = line.configured_fixture
				line_data["config_summary"] = _build_config_summary_from_dict(fixture)
				line_data["requested_length_mm"] = fixture.requested_overall_length_mm or 0
				line_data["manufacturable_length_mm"] = fixture.manufacturable_overall_length_mm or 0
				line_data["runs_count"] = fixture.runs_count or 0

				# Add fixture details
				# Add fixture configuration options
				line_data["environment_rating"] = fixture.get("environment_rating", "")
				line_data["finish"] = fixture.get("finish", "")
				line_data["lens_appearance"] = fixture.get("lens_appearance", "")
				line_data["mounting_method"] = fixture.get("mounting_method", "")
				line_data["power_feed_type"] = fixture.get("power_feed_type", "")

				# Add fixture details
				line_data["cct"] = fixture.get("cct", "")
				line_data["cri"] = fixture.get("cri", "")
				line_data["output_level"] = fixture.get("output_level", "")
				line_data["estimated_delivered_output"] = fixture.get("estimated_delivered_output", "")
				line_data["power_supply"] = fixture.get("power_supply", "")
				line_data["fixture_input_voltage"] = fixture.get("fixture_input_voltage", "")
				line_data["driver_input_voltage"] = fixture.get("driver_input_voltage", "")
				line_data["total_watts"] = fixture.get("total_watts", "")

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
			# Other manufacturer fields
			line_data["manufacturer_name"] = line.manufacturer_name or ""
			line_data["fixture_model_number"] = line.fixture_model_number or ""
			line_data["trim_info"] = line.trim_info or ""
			line_data["housing_model_number"] = line.housing_model_number or ""
			line_data["driver_model_number"] = line.driver_model_number or ""
			line_data["lamp_info"] = line.lamp_info or ""
			line_data["dimming_protocol"] = line.dimming_protocol or ""
			line_data["input_voltage"] = line.input_voltage or ""
			line_data["other_finish"] = line.other_finish or ""
			line_data["spec_sheet"] = line.spec_sheet or ""

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

	return "<br>".join(parts) if parts else ""


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

	return "<br>".join(parts) if parts else ""


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
		".col-fixture-type { width: 50px; text-align: center; }",
		".col-notes { width: 20%; }",
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
	html_parts.append("<th class='col-fixture-type'>Fixture<br>Type</th>")
	html_parts.append("<th>Type</th>")
	html_parts.append("<th>Qty</th>")
	html_parts.append("<th>Location</th>")
	html_parts.append("<th>Description</th>")
	html_parts.append("<th class='col-notes'>Notes</th>")
	if include_pricing:
		html_parts.append("<th class='text-right'>Unit Price</th>")
		html_parts.append("<th class='text-right'>Line Total</th>")
	html_parts.append("</tr></thead>")

	# Table body
	html_parts.append("<tbody>")
	for line in lines:
		row_class = "other-manufacturer" if line["manufacturer_type"] == "OTHER" else ""
		html_parts.append(f"<tr class='{row_class}'>")
		html_parts.append(f"<td class='col-fixture-type'>{line['line_id']}</td>")
		# Display manufacturer type with proper styling
		type_display = "ilLumenate Lighting" if line["manufacturer_type"] == "ILLUMENATE" else line["manufacturer_type"]
		html_parts.append(f"<td>{type_display}</td>")
		html_parts.append(f"<td>{line['qty']}</td>")
		html_parts.append(f"<td>{line['location']}</td>")

		# Description column
		if line["manufacturer_type"] == "ILLUMENATE":
			# Build description in specified order:
			# Part number, Environment, CCT, CRI, Output, Lens, Mounting, Finish, Length,
			# Feed, Input Voltage, PS Input Voltage, Wattage, Driver
			part_number = line.get("configured_fixture_name") or line["template_code"]
			description = f"<strong>{part_number}</strong>"

			# Environment / Dry/Wet
			if line.get("environment_rating"):
				description += f"<br><small>Environment: {line['environment_rating']}</small>"

			# CCT
			if line.get("cct"):
				description += f"<br><small>CCT: {line['cct']}</small>"

			# CRI
			if line.get("cri"):
				description += f"<br><small>CRI: {line['cri']}</small>"

			# Output
			if line.get("estimated_delivered_output"):
				description += f"<br><small>Output: {line['estimated_delivered_output']} lm/ft</small>"

			# Lens
			if line.get("lens_appearance"):
				description += f"<br><small>Lens: {line['lens_appearance']}</small>"

			# Mounting
			if line.get("mounting_method"):
				description += f"<br><small>Mounting: {line['mounting_method']}</small>"

			# Finish
			if line.get("finish"):
				description += f"<br><small>Finish: {line['finish']}</small>"

			# Length
			mfg_length_mm = line.get("manufacturable_length_mm", 0)
			if mfg_length_mm:
				length_inches = mfg_length_mm / 25.4
				description += f"<br><small>Length: {length_inches:.1f}\"</small>"

			# Feed
			if line.get("power_feed_type"):
				description += f"<br><small>Feed: {line['power_feed_type']}</small>"

			# Input Voltage (fixture/tape voltage)
			if line.get("fixture_input_voltage"):
				description += f"<br><small>Input Voltage: {line['fixture_input_voltage']}</small>"

			# PS Input Voltage (power supply/driver input voltage)
			if line.get("driver_input_voltage"):
				description += f"<br><small>PS Input Voltage: {line['driver_input_voltage']}</small>"

			# Wattage / Power
			if line.get("total_watts"):
				description += f"<br><small>Wattage: {line['total_watts']}W</small>"

			# Driver
			if line.get("power_supply"):
				description += f"<br><small>Driver: {line['power_supply']}</small>"
		else:
			# Other manufacturer - each field on its own line
			description = f"<strong>{line.get('manufacturer_name', '')}</strong>"
			if line.get("fixture_model_number"):
				description += f"<br><small>Fixture: {line['fixture_model_number']}</small>"
			if line.get("trim_info"):
				description += f"<br><small>Trim: {line['trim_info']}</small>"
			if line.get("housing_model_number"):
				description += f"<br><small>Housing: {line['housing_model_number']}</small>"
			if line.get("driver_model_number"):
				description += f"<br><small>Driver: {line['driver_model_number']}</small>"
			if line.get("lamp_info"):
				description += f"<br><small>Lamp: {line['lamp_info']}</small>"
			if line.get("dimming_protocol"):
				description += f"<br><small>Dimming: {line['dimming_protocol']}</small>"
			if line.get("input_voltage"):
				description += f"<br><small>Voltage: {line['input_voltage']}</small>"
			if line.get("other_finish"):
				description += f"<br><small>Finish: {line['other_finish']}</small>"
			if line.get("spec_sheet"):
				description += f"<br><small>Spec Sheet: {line['spec_sheet']}</small>"

		html_parts.append(f"<td>{description}</td>")
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
		colspan = 7
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
		"CCT",
		"CRI",
		"Output (lm/ft)",
		"Driver",
		"Requested Length (mm)",
		"Manufacturable Length (mm)",
		"Runs Count",
		"Notes",
		# Other manufacturer fields
		"Manufacturer Name",
		"Fixture Model",
		"Trim",
		"Housing Model",
		"Driver Model",
		"Lamp",
		"Dimming",
		"Voltage",
		"Finish",
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
			line.get("cct", ""),
			line.get("cri", ""),
			line.get("estimated_delivered_output", ""),
			line.get("power_supply", ""),
			line["requested_length_mm"],
			line["manufacturable_length_mm"],
			line.get("runs_count", ""),
			line["notes"],
			# Other manufacturer fields
			line.get("manufacturer_name", ""),
			line.get("fixture_model_number", ""),
			line.get("trim_info", ""),
			line.get("housing_model_number", ""),
			line.get("driver_model_number", ""),
			line.get("lamp_info", ""),
			line.get("dimming_protocol", ""),
			line.get("input_voltage", ""),
			line.get("other_finish", ""),
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

		# Save file - priced exports are saved as private files to require authentication for access.
		# Non-priced exports remain public as they don't contain sensitive pricing data.
		# Epic 3 Task 3.2: Direct-download leakage prevention for priced exports
		file_doc = save_file(
			filename,
			pdf_content,
			"ilL-Export-Job",
			job_name,
			is_private=1 if priced else 0,
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

		# Save file - priced exports are saved as private files to require authentication for access.
		# Non-priced exports remain public as they don't contain sensitive pricing data.
		# Epic 3 Task 3.2: Direct-download leakage prevention for priced exports
		file_doc = save_file(
			filename,
			csv_content.encode("utf-8"),
			"ilL-Export-Job",
			job_name,
			is_private=1 if priced else 0,
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


@frappe.whitelist()
def download_export_file(export_job_id: str) -> dict:
	"""
	Secure download endpoint for export files.

	Validates permissions before providing access to the file.
	Epic 3 Task 3.2: Direct-download leakage prevention.

	Args:
		export_job_id: Name of the ilL-Export-Job

	Returns:
		dict: {
			"success": bool,
			"download_url": str (if authorized),
			"error": str (if not authorized)
		}
	"""
	if not frappe.db.exists("ilL-Export-Job", export_job_id):
		return {"success": False, "error": _("Export job not found")}

	export_job = frappe.get_doc("ilL-Export-Job", export_job_id)

	# Check schedule access
	has_access, error = _check_schedule_access(export_job.schedule)
	if not has_access:
		return {"success": False, "error": error}

	# Check if this is a priced export and user has pricing permission
	if export_job.export_type in ["PDF_PRICED", "CSV_PRICED"]:
		if not _check_pricing_permission():
			return {"success": False, "error": _("You don't have permission to download priced exports")}

	# Check if export is complete
	if export_job.status != "COMPLETE":
		return {"success": False, "error": _("Export is not ready for download")}

	if not export_job.output_file:
		return {"success": False, "error": _("No output file available")}

	return {
		"success": True,
		"download_url": export_job.output_file,
		"export_type": export_job.export_type,
		"created_on": export_job.created_on,
	}


@frappe.whitelist()
def validate_file_access(file_url: str) -> dict:
	"""
	Validate if current user can access a specific file.

	This is used to check file access before serving private files.
	Epic 3 Task 3.2: Direct-download leakage prevention.

	Args:
		file_url: The file URL to validate

	Returns:
		dict: {"has_access": bool, "reason": str}
	"""
	# Extract file doc from URL
	file_doc = frappe.db.get_value(
		"File",
		{"file_url": file_url},
		["name", "is_private", "attached_to_doctype", "attached_to_name"],
		as_dict=True,
	)

	if not file_doc:
		return {"has_access": False, "reason": "File not found"}

	# Public files are always accessible
	if not file_doc.is_private:
		return {"has_access": True, "reason": "Public file"}

	# For private files attached to export jobs, validate export access
	if file_doc.attached_to_doctype == "ilL-Export-Job":
		export_job = frappe.get_doc("ilL-Export-Job", file_doc.attached_to_name)

		# Check schedule access
		has_access, error = _check_schedule_access(export_job.schedule)
		if not has_access:
			return {"has_access": False, "reason": error}

		# Check pricing permission for priced exports
		if export_job.export_type in ["PDF_PRICED", "CSV_PRICED"]:
			if not _check_pricing_permission():
				return {"has_access": False, "reason": "Pricing permission required"}

		return {"has_access": True, "reason": "Authorized via export job access"}

	# For other private files, use default Frappe permission check
	try:
		frappe.get_doc("File", file_doc.name).check_permission("read")
		return {"has_access": True, "reason": "Standard file permission"}
	except frappe.PermissionError:
		return {"has_access": False, "reason": "No file permission"}

