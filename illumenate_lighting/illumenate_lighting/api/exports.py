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
import os
import shutil
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import now, nowdate
from frappe.utils.file_manager import save_file

from illumenate_lighting.illumenate_lighting.api.unit_conversion import convert_build_description_to_inches


def _save_file_ignore_permissions(fname, content, dt, dn, is_private=1):
	"""Wrap ``save_file()`` with ``ignore_permissions`` to avoid switching
	the session user to Administrator (which corrupts the Frappe session
	and causes 403 / forced sign-out for portal users).

	Always saves as private first to sidestep Frappe's
	``enforce_public_file_restrictions`` (a hard ``frappe.only_for("System Manager")``
	check that ``frappe.flags.ignore_permissions`` cannot bypass).
	If the caller requested ``is_private=0``, the file is moved to the
	public directory post-save via a direct DB update + filesystem move.
	"""
	requested_public = int(is_private) == 0

	_prev = frappe.flags.ignore_permissions
	try:
		frappe.flags.ignore_permissions = True
		file_doc = save_file(fname, content, dt, dn, is_private=1)
	finally:
		frappe.flags.ignore_permissions = _prev

	if requested_public:
		private_url = file_doc.file_url  # e.g. /private/files/xyz.pdf
		public_url = private_url.replace("/private/files/", "/files/", 1)

		site_path = frappe.get_site_path()
		private_path = os.path.join(site_path, private_url.lstrip("/"))
		public_path = os.path.join(site_path, "public", "files", os.path.basename(private_url))

		# copy first so a DB-update failure still leaves the private file intact
		shutil.copy2(private_path, public_path)
		try:
			frappe.db.set_value(
				"File", file_doc.name,
				{"is_private": 0, "file_url": public_url},
				update_modified=False,
			)
		except Exception:
			# DB update failed – remove the orphaned public copy and re-raise
			if os.path.exists(public_path):
				os.remove(public_path)
			raise

		# Private copy is no longer needed; failure here is benign (orphan)
		try:
			os.remove(private_path)
		except OSError:
			pass

		file_doc.reload()

	return file_doc


# Conversion constant: millimeters per foot
MM_PER_FOOT = 304.8
MM_PER_INCH = 25.4


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

	# Load with ignore_permissions so portal users can reach the custom
	# permission check below (standard DocType role permissions may not
	# include the Website User role).
	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name, ignore_permissions=True)

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
	job = frappe.get_doc("ilL-Export-Job", job_name, ignore_permissions=True)
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
			driver_msrp_total = 0.0
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

					# Look up driver MSRP from Item Price
					driver_price = frappe.db.get_value(
						"Item Price",
						{"item_code": driver_alloc.driver_item, "selling": 1},
						"price_list_rate",
					)
					if driver_price:
						driver_msrp_total += float(driver_price) * driver_qty

			if driver_items:
				details["power_supply"] = ", ".join(driver_items)
			if driver_input_voltages:
				# Remove duplicates and join
				unique_voltages = list(dict.fromkeys(driver_input_voltages))
				details["driver_input_voltage"] = ", ".join(unique_voltages)
			if driver_msrp_total > 0:
				details["driver_msrp_unit"] = round(driver_msrp_total, 2)

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
				"runs_count", "tape_offering", "is_multi_segment", "build_description",
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

	# Pre-fetch all configured tape/neon records to avoid N+1 queries
	ctn_ids = [
		line.configured_tape_neon
		for line in (schedule.lines or [])
		if line.manufacturer_type == "ILLUMENATE"
		and getattr(line, "product_type", None) in ("LED Tape", "LED Neon")
		and line.configured_tape_neon
	]

	ctn_map = {}
	if ctn_ids:
		ctns = frappe.get_all(
			"ilL-Configured-Tape-Neon",
			filters={"name": ["in", ctn_ids]},
			fields=[
				"name", "part_number", "product_category", "tape_neon_template",
				"cct", "output_level", "environment_rating", "finish",
				"pcb_finish", "feed_type", "total_watts", "watts_per_foot",
				"manufacturable_length_mm", "total_segments", "build_description",
			],
		)
		for ctn in ctns:
			ctn_map[ctn.name] = ctn

		if include_pricing:
			for ctn_id in ctn_ids:
				if ctn_id in ctn_map:
					snaps = frappe.get_all(
						"ilL-Child-Pricing-Snapshot",
						filters={"parent": ctn_id, "parenttype": "ilL-Configured-Tape-Neon"},
						fields=["msrp_unit"],
						order_by="timestamp desc",
						limit=1,
					)
					if snaps:
						ctn_map[ctn_id]["latest_msrp_unit"] = float(snaps[0].msrp_unit or 0)

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
				line_data["is_multi_segment"] = fixture.get("is_multi_segment", 0)
				line_data["build_description"] = fixture.get("build_description", "")

				if include_pricing and fixture.get("latest_msrp_unit"):
					unit_price = fixture["latest_msrp_unit"]
					line_data["unit_price"] = unit_price
					line_data["line_total"] = unit_price * (line.qty or 1)
					schedule_total += line_data["line_total"]

					# Add driver MSRP as separate sub-line pricing
					driver_msrp = fixture.get("driver_msrp_unit")
					if driver_msrp:
						line_data["driver_unit_price"] = driver_msrp
						line_data["driver_line_total"] = driver_msrp * (line.qty or 1)
						schedule_total += line_data["driver_line_total"]
			else:
				line_data["template_code"] = ""
				line_data["config_summary"] = "Configured fixture not found"
				line_data["requested_length_mm"] = 0
				line_data["manufacturable_length_mm"] = line.manufacturable_length_mm or 0
				line_data["runs_count"] = 0

		elif (
			line.manufacturer_type == "ILLUMENATE"
			and getattr(line, "product_type", None) in ("LED Tape", "LED Neon")
		):
			# LED Tape / LED Neon — read from configured_tape_neon record or variant_selections
			import json as _json_tn

			line_data["is_tape_neon"] = True
			line_data["product_type"] = line.product_type or ""

			# --- Primary source: configured_tape_neon link field ---
			ctn = ctn_map.get(line.configured_tape_neon) if line.configured_tape_neon else None

			if ctn:
				line_data["part_number"] = ctn.get("part_number") or line.ill_item_code or ""
				line_data["product_category"] = ctn.get("product_category") or line.product_type or ""
				line_data["cct"] = ctn.get("cct") or ""
				line_data["output_level"] = ctn.get("output_level") or ""
				line_data["environment_rating"] = ctn.get("environment_rating") or ""
				line_data["finish"] = ctn.get("finish") or ""
				line_data["pcb_finish"] = ctn.get("pcb_finish") or ""
				line_data["feed_type"] = ctn.get("feed_type") or ""
				line_data["total_watts"] = ctn.get("total_watts") or ""
				line_data["manufacturable_length_mm"] = ctn.get("manufacturable_length_mm") or (line.manufacturable_length_mm or 0)
				line_data["total_segments"] = ctn.get("total_segments") or 1
				line_data["build_description"] = ctn.get("build_description") or ""
				line_data["tape_neon_template"] = ctn.get("tape_neon_template") or (getattr(line, "tape_neon_template", None) or "")

				# Resolve template name for display
				if line_data["tape_neon_template"]:
					tn_name = frappe.db.get_value(
						"ilL-Tape-Neon-Template",
						line_data["tape_neon_template"],
						"template_name",
					)
					line_data["tape_neon_template_name"] = tn_name or line_data["tape_neon_template"]
				else:
					line_data["tape_neon_template_name"] = ""

				if include_pricing and ctn.get("latest_msrp_unit"):
					unit_price = float(ctn["latest_msrp_unit"])
					line_data["unit_price"] = unit_price
					line_data["line_total"] = unit_price * (line.qty or 1)
					schedule_total += line_data["line_total"]

			else:
				# --- Fallback source: variant_selections JSON ---
				vs_raw = getattr(line, "variant_selections", None)
				vs = {}
				if vs_raw:
					try:
						vs = _json_tn.loads(vs_raw) if isinstance(vs_raw, str) else vs_raw
					except (ValueError, TypeError):
						vs = {}

				selections = vs.get("selections", {})
				computed = vs.get("computed", {})

				line_data["part_number"] = vs.get("part_number") or line.ill_item_code or ""
				line_data["product_category"] = vs.get("product_category") or line.product_type or ""
				line_data["cct"] = selections.get("cct") or ""
				line_data["output_level"] = selections.get("output_level") or ""
				line_data["environment_rating"] = selections.get("environment_rating") or ""
				line_data["finish"] = selections.get("finish") or ""
				line_data["pcb_finish"] = selections.get("pcb_finish") or ""
				line_data["feed_type"] = selections.get("feed_type") or ""
				line_data["total_watts"] = computed.get("total_watts") or ""
				line_data["manufacturable_length_mm"] = (
					computed.get("manufacturable_length_mm")
					or computed.get("total_manufacturable_length_mm")
					or (line.manufacturable_length_mm or 0)
				)
				line_data["total_segments"] = computed.get("segment_count") or 1
				line_data["build_description"] = vs.get("build_description") or ""
				line_data["tape_neon_template"] = getattr(line, "tape_neon_template", None) or ""

				if line_data["tape_neon_template"]:
					tn_name = frappe.db.get_value(
						"ilL-Tape-Neon-Template",
						line_data["tape_neon_template"],
						"template_name",
					)
					line_data["tape_neon_template_name"] = tn_name or line_data["tape_neon_template"]
				else:
					line_data["tape_neon_template_name"] = ""

				if include_pricing:
					total_msrp = computed.get("total_price_msrp")
					if total_msrp:
						unit_price = float(total_msrp)
						line_data["unit_price"] = unit_price
						line_data["line_total"] = unit_price * (line.qty or 1)
						schedule_total += line_data["line_total"]

			line_data["template_code"] = ""
			line_data["config_summary"] = ""
			line_data["requested_length_mm"] = 0
			line_data["runs_count"] = 0

		elif line.manufacturer_type == "ILLUMENATE" and not line.configured_fixture:
			# Unconfigured ILLUMENATE fixture - has template but not yet configured
			line_data["is_unconfigured"] = True
			line_data["fixture_template"] = line.fixture_template or ""
			line_data["product_type"] = line.product_type or ""
			# Try to get the fixture template name
			if line.fixture_template:
				template_name = frappe.db.get_value(
					"ilL-Fixture-Template",
					line.fixture_template,
					"template_name"
				)
				line_data["fixture_template_name"] = template_name or line.fixture_template
			else:
				line_data["fixture_template_name"] = ""
			line_data["template_code"] = ""
			line_data["config_summary"] = ""
			line_data["requested_length_mm"] = 0
			line_data["manufacturable_length_mm"] = 0
			line_data["runs_count"] = 0

		elif line.manufacturer_type == "ACCESSORY":
			# Accessory/Component line - ilLumenate products that aren't configurable fixtures
			line_data["accessory_product_type"] = line.accessory_product_type or ""
			line_data["accessory_item"] = line.accessory_item or ""
			line_data["accessory_item_name"] = line.accessory_item_name or ""
			# Fetch item description if we have an item
			if line.accessory_item:
				item_data = frappe.db.get_value(
					"Item",
					line.accessory_item,
					["item_name", "description"],
					as_dict=True
				)
				if item_data:
					line_data["accessory_item_name"] = line.accessory_item_name or item_data.item_name or ""
					line_data["accessory_item_description"] = item_data.description or ""
				# Try to get pricing if include_pricing
				if include_pricing:
					item_price = frappe.db.get_value(
						"Item Price",
						{"item_code": line.accessory_item, "selling": 1},
						"price_list_rate"
					)
					if item_price:
						line_data["unit_price"] = float(item_price)
						line_data["line_total"] = float(item_price) * (line.qty or 1)
						schedule_total += line_data["line_total"]
			line_data["template_code"] = ""
			line_data["config_summary"] = ""
			line_data["requested_length_mm"] = 0
			line_data["manufacturable_length_mm"] = 0
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

	Produces a professional construction lighting fixture schedule with a
	branded header, compact data table, and industry-standard aesthetics
	using the ilLumenate #1a365d navy palette.

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
	export_date = schedule_data["export_date"]

	# Build CSS
	css_rules = [
		"@page { size: landscape; margin: 12mm; }",
		"body { font-family: Arial, Helvetica, sans-serif; font-size: 8px; color: #333; margin: 0; padding: 0; }",
		# Header block
		"h1 { font-size: 14px; color: #1a365d; margin: 0 0 2px 0; }",
		".accent-bar { height: 2px; background: #1a365d; margin-bottom: 6px; }",
		"h2 { font-size: 11px; color: #4a5568; margin: 0 0 8px 0; font-weight: normal; }",
		".info-bar { background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 3px;"
		" padding: 5px 10px; margin-bottom: 10px; display: flex; gap: 18px; font-size: 7.5px; }",
		".info-bar .lbl { color: #4a5568; font-weight: bold; margin-right: 3px; }",
		# Table
		"table { width: 100%; border-collapse: collapse; margin-top: 4px; }",
		"th, td { border: 1px solid #e2e8f0; padding: 3px 5px; text-align: left;"
		" font-size: 7.5px; vertical-align: top; }",
		"th { background-color: #1a365d; color: #fff; font-weight: bold; font-size: 7.5px; }",
		"tbody tr:nth-child(even) { background-color: #f7fafc; }",
		".col-fixture-type { width: 40px; text-align: center; }",
		".text-right { text-align: right; }",
		".total-row { font-weight: bold; background-color: #edf2f7 !important; }",
		".other-manufacturer { background-color: #fffbe6 !important; }",
		".desc-detail { color: #4a5568; }",
		# Footer
		".footer { text-align: center; font-size: 7px; color: #a0aec0; margin-top: 12px;"
		" border-top: 1px solid #e2e8f0; padding-top: 4px; }",
	]
	if include_pricing:
		css_rules.append(".pricing-sub-line { font-size: 6.5px; color: #888; }")

	html_parts = [
		"<html><head><style>",
		"".join(css_rules),
		"</style></head><body>",
	]

	# ── Header section ──
	html_parts.append(f"<h1>{schedule.schedule_name}</h1>")
	html_parts.append("<div class='accent-bar'></div>")
	if project:
		html_parts.append(f"<h2>{project.project_name}</h2>")

	# Info bar — horizontal label/value pairs
	info_items = []
	if customer:
		customer_name = customer.customer_name or customer.name
		info_items.append(f"<span><span class='lbl'>Customer:</span> {customer_name}</span>")
	info_items.append(f"<span><span class='lbl'>Date:</span> {export_date}</span>")
	info_items.append(f"<span><span class='lbl'>Status:</span> {schedule.status}</span>")
	version = getattr(schedule, "version", None)
	if version:
		info_items.append(f"<span><span class='lbl'>Version:</span> {version}</span>")
	html_parts.append(f"<div class='info-bar'>{''.join(info_items)}</div>")

	# ── Table header ──
	html_parts.append("<table>")
	html_parts.append("<thead><tr>")
	html_parts.append("<th class='col-fixture-type'>Fixture<br>Type</th>")
	html_parts.append("<th>Type</th>")
	html_parts.append("<th>Qty</th>")
	html_parts.append("<th>Location</th>")
	html_parts.append("<th>Description</th>")
	if include_pricing:
		html_parts.append("<th class='text-right'>Unit Price</th>")
		html_parts.append("<th class='text-right'>Line Total</th>")
	html_parts.append("</tr></thead>")

	# ── Table body ──
	html_parts.append("<tbody>")
	for line in lines:
		row_class = "other-manufacturer" if line["manufacturer_type"] == "OTHER" else ""
		html_parts.append(f"<tr class='{row_class}'>")
		html_parts.append(f"<td class='col-fixture-type'>{line['line_id']}</td>")
		# Display manufacturer type
		if line["manufacturer_type"] in ["ILLUMENATE", "ACCESSORY"]:
			type_display = "ilLumenate Lighting"
		else:
			type_display = line.get("manufacturer_name") or "Other"
		html_parts.append(f"<td>{type_display}</td>")
		html_parts.append(f"<td>{line['qty']}</td>")
		html_parts.append(f"<td>{line['location']}</td>")

		# Description column — compact multi-line layout
		description = _build_pdf_description(line)

		html_parts.append(f"<td>{description}</td>")

		if include_pricing:
			unit_price = line.get("unit_price", 0)
			line_total = line.get("line_total", 0)
			unit_price_html = f"${unit_price:.2f}"
			line_total_html = f"${line_total:.2f}"
			if line.get("driver_unit_price"):
				unit_price_html += f"<div class='pricing-sub-line'>${line['driver_unit_price']:.2f}</div>"
			if line.get("driver_line_total"):
				line_total_html += f"<div class='pricing-sub-line'>${line['driver_line_total']:.2f}</div>"
			html_parts.append(f"<td class='text-right'>{unit_price_html}</td>")
			html_parts.append(f"<td class='text-right'>{line_total_html}</td>")

		html_parts.append("</tr>")

	# Total row for priced exports
	if include_pricing:
		schedule_total = schedule_data.get("schedule_total", 0)
		colspan = 6
		html_parts.append("<tr class='total-row'>")
		html_parts.append(f"<td colspan='{colspan}' class='text-right'>Schedule Total:</td>")
		html_parts.append(f"<td class='text-right'>${schedule_total:.2f}</td>")
		html_parts.append("</tr>")

	html_parts.append("</tbody></table>")

	# ── Footer ──
	html_parts.append(
		f"<div class='footer'>ilLumenate Lighting | Generated {export_date}</div>"
	)

	html_parts.append("</body></html>")

	return "".join(html_parts)


def _build_pdf_description(line: dict) -> str:
	"""
	Build a compact HTML description cell for a single schedule line.

	Consolidates secondary details into semicolon / dot-delimited rows
	to minimize vertical space in the PDF table.

	Args:
		line: A single line dict from schedule_data["lines"]

	Returns:
		str: HTML fragment for the description ``<td>``
	"""
	if line.get("is_tape_neon"):
		return _build_tape_neon_pdf_description(line)

	if line["manufacturer_type"] == "ILLUMENATE" and not line.get("is_unconfigured"):
		return _build_illumenate_description(line)

	if line["manufacturer_type"] == "ILLUMENATE" and line.get("is_unconfigured"):
		template_name = (
			line.get("fixture_template_name")
			or line.get("fixture_template")
			or "Unknown Template"
		)
		return (
			f"<strong>{template_name}</strong>"
			"<br><span class='desc-detail' style='color:#856404;'>"
			"⚠ Not configured - configuration required</span>"
		)

	if line["manufacturer_type"] == "ACCESSORY":
		return _build_accessory_description(line)

	# OTHER manufacturer
	return _build_other_description(line)


def _detail_row(items: list) -> str:
	"""Join non-empty items with middle-dot separators and wrap in a desc-detail span."""
	if not items:
		return ""
	return f"<br><span class='desc-detail'>{' · '.join(items)}</span>"


def _build_illumenate_description(line: dict) -> str:
	"""Build compact description for a configured ILLUMENATE fixture line."""
	part_number = line.get("configured_fixture_name") or line.get("template_code", "")
	parts = [f"<strong>{part_number}</strong>"]

	# Row 1 — optical: CCT · CRI · Output · Environment
	optical = []
	if line.get("cct"):
		optical.append(line["cct"])
	if line.get("cri"):
		optical.append(f"{line['cri']} CRI")
	if line.get("estimated_delivered_output"):
		optical.append(f"{line['estimated_delivered_output']} lm/ft")
	if line.get("environment_rating"):
		optical.append(line["environment_rating"])
	parts.append(_detail_row(optical))

	# Row 2 — physical: Mounting · Finish · Lens
	physical = []
	if line.get("mounting_method"):
		physical.append(line["mounting_method"])
	if line.get("finish"):
		physical.append(line["finish"])
	if line.get("lens_appearance"):
		physical.append(line["lens_appearance"])
	parts.append(_detail_row(physical))

	# Row 3 — electrical + dimensions: Length · Feed/Build · Voltages · Wattage · Driver
	elec = []
	mfg_length_mm = line.get("manufacturable_length_mm", 0)
	if mfg_length_mm:
		length_inches = mfg_length_mm / 25.4
		elec.append(f"{length_inches:.1f}\"")
	if line.get("is_multi_segment") and line.get("build_description"):
		build_desc = convert_build_description_to_inches(
			line.get("build_description", "")
		).replace("\n", "; ")
		elec.append(f"Build: {build_desc}")
	elif line.get("power_feed_type"):
		elec.append(line["power_feed_type"])
	if line.get("fixture_input_voltage"):
		elec.append(line["fixture_input_voltage"])
	if line.get("driver_input_voltage"):
		elec.append(f"PS {line['driver_input_voltage']}")
	if line.get("total_watts"):
		elec.append(f"{line['total_watts']}W")
	if line.get("power_supply"):
		elec.append(line["power_supply"])
	parts.append(_detail_row(elec))

	return "".join(parts)


def _build_accessory_description(line: dict) -> str:
	"""Build compact description for an ACCESSORY line."""
	item_name = line.get("accessory_item_name") or line.get("accessory_item") or ""
	parts = [f"<strong>{item_name}</strong>"]
	details = []
	if line.get("accessory_item"):
		details.append(line["accessory_item"])
	if line.get("accessory_product_type"):
		details.append(line["accessory_product_type"])
	parts.append(_detail_row(details))
	if line.get("accessory_item_description"):
		item_desc = line["accessory_item_description"]
		if len(item_desc) > 150:
			item_desc = item_desc[:150] + "..."
		parts.append(f"<br><span class='desc-detail'>{item_desc}</span>")
	return "".join(parts)


def _build_other_description(line: dict) -> str:
	"""Build compact description for an OTHER manufacturer line."""
	parts = [f"<strong>{line.get('manufacturer_name', '')}</strong>"]
	# Row 1 — model info
	models = []
	if line.get("fixture_model_number"):
		models.append(line["fixture_model_number"])
	if line.get("trim_info"):
		models.append(f"Trim: {line['trim_info']}")
	if line.get("housing_model_number"):
		models.append(f"Housing: {line['housing_model_number']}")
	parts.append(_detail_row(models))
	# Row 2 — electrical / finish
	elec = []
	if line.get("driver_model_number"):
		elec.append(f"Driver: {line['driver_model_number']}")
	if line.get("lamp_info"):
		elec.append(line["lamp_info"])
	if line.get("dimming_protocol"):
		elec.append(line["dimming_protocol"])
	if line.get("input_voltage"):
		elec.append(line["input_voltage"])
	if line.get("other_finish"):
		elec.append(line["other_finish"])
	parts.append(_detail_row(elec))
	if line.get("spec_sheet"):
		parts.append(f"<br><span class='desc-detail'>Spec: {line['spec_sheet']}</span>")
	return "".join(parts)


def _build_tape_neon_pdf_description(line: dict) -> str:
	"""Build compact description for a configured LED Tape / LED Neon line."""
	part_number = line.get("part_number") or "Configured"
	product_category = line.get("product_category") or line.get("product_type") or "LED Tape"
	parts = [f"<strong>{part_number}</strong> <span style='font-size:6.5px;'>({product_category})</span>"]

	# Template/series reference
	tpl_name = line.get("tape_neon_template_name") or line.get("tape_neon_template")
	if tpl_name:
		parts.append(f"<br><span class='desc-detail'>Series: {tpl_name}</span>")

	# Optical: CCT · Output · Environment
	optical = []
	if line.get("cct"):
		optical.append(line["cct"])
	if line.get("output_level"):
		optical.append(f"{line['output_level']} lm/ft")
	if line.get("environment_rating"):
		optical.append(line["environment_rating"])
	if optical:
		parts.append(_detail_row(optical))

	# Physical: Finish / PCB Finish
	physical = []
	if line.get("finish"):
		physical.append(f"Finish: {line['finish']}")
	if line.get("pcb_finish"):
		physical.append(f"PCB: {line['pcb_finish']}")
	if physical:
		parts.append(_detail_row(physical))

	# Dimensions & electrical
	elec = []
	mfg_length_mm = line.get("manufacturable_length_mm") or 0
	if mfg_length_mm:
		length_in = mfg_length_mm / 25.4
		elec.append(f'{length_in:.1f}"')
	if line.get("total_watts"):
		elec.append(f"{line['total_watts']}W")
	if line.get("total_segments") and line["total_segments"] > 1:
		elec.append(f"{line['total_segments']} segments")
	if elec:
		parts.append(_detail_row(elec))

	# Build description (neon multi-segment)
	if line.get("build_description"):
		bd = convert_build_description_to_inches(line["build_description"]).replace("\n", "; ")
		if len(bd) > 200:
			bd = bd[:200] + "..."
		parts.append(f"<br><span class='desc-detail'>{bd}</span>")

	return "".join(parts)


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
		"Description",
		"CCT",
		"CRI",
		"Output (lm/ft)",
		"Driver",
		"Requested Length (in)",
		"Manufacturable Length (in)",
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
		# Accessory fields
		"Accessory Item Code",
		"Accessory Item Name",
		"Accessory Category",
	]
	if include_pricing:
		headers.extend(["Unit Price", "Line Total", "PS Unit Price", "PS Line Total"])

	writer.writerow(headers)

	# Data rows
	project_name = project.project_name if project else ""
	schedule_name = schedule.schedule_name

	for line in lines:
		# Convert lengths from mm to inches for display
		requested_length_in = round(line["requested_length_mm"] / MM_PER_INCH, 1) if line.get("requested_length_mm") else ""
		manufacturable_length_in = round(line["manufacturable_length_mm"] / MM_PER_INCH, 1) if line.get("manufacturable_length_mm") else ""
		
		# Build description based on manufacturer type
		if line["manufacturer_type"] == "ILLUMENATE" and not line.get("is_unconfigured"):
			description = f"{line['template_code']} {line['config_summary']}".strip()
		elif line["manufacturer_type"] == "ILLUMENATE" and line.get("is_unconfigured"):
			template_name = line.get("fixture_template_name") or line.get("fixture_template") or ""
			description = f"{template_name} (Not configured)"
		elif line["manufacturer_type"] == "ACCESSORY":
			description = line.get("accessory_item_name") or line.get("accessory_item") or ""
		else:
			description = line.get("manufacturer_name") or ""
		
		row = [
			project_name,
			schedule_name,
			line["line_id"],
			line["manufacturer_type"],
			line["qty"],
			line["location"],
			description,
			line.get("cct", ""),
			line.get("cri", ""),
			line.get("estimated_delivered_output", ""),
			line.get("power_supply", ""),
			requested_length_in,
			manufacturable_length_in,
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
			# Accessory fields
			line.get("accessory_item", ""),
			line.get("accessory_item_name", ""),
			line.get("accessory_product_type", ""),
		]
		if include_pricing:
			row.extend([
				f"{line.get('unit_price', 0):.2f}",
				f"{line.get('line_total', 0):.2f}",
				f"{line['driver_unit_price']:.2f}" if line.get("driver_unit_price") else "",
				f"{line['driver_line_total']:.2f}" if line.get("driver_line_total") else "",
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
def debug_schedule_lines(schedule_id: str) -> dict:
	"""
	Debug helper: dump raw field values for every line in a schedule.
	Use from the browser console:
	  frappe.call({method:'illumenate_lighting.illumenate_lighting.api.exports.debug_schedule_lines',
	              args:{schedule_id:'SCHED-0001'}, callback: r => console.table(r.message.lines)})
	"""
	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_id)
	lines = []
	for line in schedule.lines or []:
		lines.append({
			"idx": line.idx,
			"line_id": line.line_id,
			"manufacturer_type": line.manufacturer_type,
			"product_type": line.product_type,
			"configuration_status": line.configuration_status,
			"configured_fixture": line.configured_fixture,
			"configured_tape_neon": getattr(line, "configured_tape_neon", None),
			"tape_neon_template": getattr(line, "tape_neon_template", None),
			"ill_item_code": getattr(line, "ill_item_code", None),
			"manufacturable_length_mm": getattr(line, "manufacturable_length_mm", None),
			"variant_selections_present": bool(getattr(line, "variant_selections", None)),
			"notes_snippet": (line.notes or "")[:80],
			# Which branch will exports.py take?
			"_branch": (
				"linear_fixture" if (line.manufacturer_type == "ILLUMENATE" and line.configured_fixture)
				else "tape_neon" if (line.manufacturer_type == "ILLUMENATE" and getattr(line, "product_type", None) in ("LED Tape", "LED Neon"))
				else "unconfigured" if (line.manufacturer_type == "ILLUMENATE" and not line.configured_fixture)
				else "accessory" if line.manufacturer_type == "ACCESSORY"
				else "other"
			),
		})
	return {"schedule": schedule_id, "line_count": len(lines), "lines": lines}


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

		# Save file as private – use ignore_permissions to avoid switching
		# the session user (which corrupts the Frappe session for portal users).
		file_doc = _save_file_ignore_permissions(
			filename, pdf_content, "ilL-Export-Job", job_name, is_private=1,
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
		try:
			_update_export_job_status(job_name, "FAILED", error_log=error_msg)
		except Exception:
			frappe.log_error("Failed to update export job status during PDF error handling")
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

		# Save file as private – use ignore_permissions to avoid switching
		# the session user (which corrupts the Frappe session for portal users).
		file_doc = _save_file_ignore_permissions(
			filename, csv_content.encode("utf-8"), "ilL-Export-Job", job_name, is_private=1,
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
		try:
			_update_export_job_status(job_name, "FAILED", error_log=error_msg)
		except Exception:
			frappe.log_error("Failed to update export job status during CSV error handling")
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
		# Spec submittals don't contain pricing, so always include them
		filters["export_type"] = ["in", [
			"PDF_NO_PRICE", "CSV_NO_PRICE",
			"SPEC_SUBMITTAL", "SPEC_SUBMITTAL_FULL",
		]]

	# Portal users may not have standard DocType read permission on
	# ilL-Export-Job, so use ignore_permissions here.  Access is already
	# validated above via _check_schedule_access.
	exports = frappe.get_all(
		"ilL-Export-Job",
		filters=filters,
		fields=["name", "export_type", "status", "requested_by", "created_on", "output_file"],
		order_by="created_on desc",
		limit=50,
		ignore_permissions=True,
	)

	# Batch fetch user names to avoid N+1 queries
	user_ids = list({exp.requested_by for exp in exports if exp.requested_by})
	user_names_map = {}
	if user_ids:
		users = frappe.get_all(
			"User",
			filters={"name": ["in", user_ids]},
			fields=["name", "full_name"],
			ignore_permissions=True,
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
def get_project_export_files(project_name: str) -> dict:
	"""
	Get all exported documents across all fixture schedules for a project.

	Aggregates completed export jobs from every schedule belonging to the
	given project so they can be listed in the project-level Files tab.

	Args:
		project_name: Name of the ilL-Project

	Returns:
		dict: {
			"success": bool,
			"files": list of export file dicts,
			"error": str (if failed)
		}
	"""
	if frappe.session.user == "Guest":
		return {"success": False, "error": _("Please login to view project files")}

	if not frappe.db.exists("ilL-Project", project_name):
		return {"success": False, "error": _("Project not found")}

	# Check project permission
	project = frappe.get_doc("ilL-Project", project_name)
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		has_permission,
	)

	if not has_permission(project, "read", frappe.session.user):
		return {"success": False, "error": _("You don't have permission to view this project")}

	# Get all schedules for this project
	schedule_names = frappe.get_all(
		"ilL-Project-Fixture-Schedule",
		filters={"ill_project": project_name},
		pluck="name",
	)

	if not schedule_names:
		return {"success": True, "files": []}

	# Get user pricing permission
	can_view_pricing = _check_pricing_permission()

	# Build filters for export jobs
	filters = {
		"schedule": ["in", schedule_names],
		"status": "COMPLETE",
	}
	if not can_view_pricing:
		filters["export_type"] = ["in", [
			"PDF_NO_PRICE", "CSV_NO_PRICE",
			"SPEC_SUBMITTAL", "SPEC_SUBMITTAL_FULL",
		]]

	exports = frappe.get_all(
		"ilL-Export-Job",
		filters=filters,
		fields=[
			"name", "schedule", "export_type", "status",
			"requested_by", "created_on", "output_file",
		],
		order_by="created_on desc",
		limit=100,
	)

	# Batch fetch schedule names for display
	schedule_name_map = {}
	if schedule_names:
		schedules = frappe.get_all(
			"ilL-Project-Fixture-Schedule",
			filters={"name": ["in", schedule_names]},
			fields=["name", "schedule_name"],
		)
		schedule_name_map = {s.name: s.schedule_name for s in schedules}

	# Batch fetch user names
	user_ids = list({exp.requested_by for exp in exports if exp.requested_by})
	user_names_map = {}
	if user_ids:
		users = frappe.get_all(
			"User",
			filters={"name": ["in", user_ids]},
			fields=["name", "full_name"],
		)
		user_names_map = {u.name: u.full_name for u in users}

	# Enrich exports with display data
	for export in exports:
		export["schedule_display_name"] = schedule_name_map.get(export.schedule, export.schedule)
		if export.requested_by:
			export["requested_by_name"] = user_names_map.get(export.requested_by) or export.requested_by
		else:
			export["requested_by_name"] = ""

	return {
		"success": True,
		"files": exports,
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

	# Use ignore_permissions because portal users (dealers, customers) may
	# not have standard DocType read permission on ilL-Export-Job.  Access
	# is validated below via _check_schedule_access.
	export_job = frappe.get_doc("ilL-Export-Job", export_job_id, ignore_permissions=True)

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
		export_job = frappe.get_doc("ilL-Export-Job", file_doc.attached_to_name, ignore_permissions=True)

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


@frappe.whitelist(methods=["GET"])
def serve_export_file(export_job_id: str):
	"""
	Serve an export file for download after validating custom permissions.

	Portal users cannot download private files via direct URL because Frappe's
	built-in file handler only checks standard DocType role permissions, not
	custom ``has_permission`` functions.  This endpoint bridges that gap: it
	validates access via ``_check_schedule_access`` (which calls the custom
	permission logic) and then streams the file content to the browser.

	Args:
		export_job_id: Name of the ilL-Export-Job whose output file to serve.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please login to download files"), frappe.PermissionError)

	if not frappe.db.exists("ilL-Export-Job", export_job_id):
		frappe.throw(_("Export job not found"), frappe.DoesNotExistError)

	# Load the export job with ignore_permissions – portal users (dealers,
	# customers) may not have standard DocType read permission on
	# ilL-Export-Job.  The custom access check below validates authorization.
	export_job = frappe.get_doc("ilL-Export-Job", export_job_id, ignore_permissions=True)

	# Validate schedule-level access using the custom permission check
	has_access, error = _check_schedule_access(export_job.schedule)
	if not has_access:
		frappe.throw(error or _("Access denied"), frappe.PermissionError)

	# Pricing permission gate for priced exports
	if export_job.export_type in ["PDF_PRICED", "CSV_PRICED"]:
		if not _check_pricing_permission():
			frappe.throw(_("You don't have permission to download priced exports"), frappe.PermissionError)

	if export_job.status != "COMPLETE" or not export_job.output_file:
		frappe.throw(_("Export is not ready for download"))

	# Look up the File record and read content.  Use ignore_permissions
	# on the query and load to bypass Frappe's standard file-permission
	# checks on private files (the custom access check above already
	# validated the user's right to this export).  Avoid
	# frappe.set_user() here because it can corrupt the session.
	file_records = frappe.get_all(
		"File",
		filters={"file_url": export_job.output_file},
		fields=["name", "file_name"],
		order_by="creation desc",
		limit=1,
		ignore_permissions=True,
	)
	if not file_records:
		frappe.throw(_("Output file record not found"))

	# Read the file content from disk using the file_url.  This avoids
	# frappe.get_doc("File", …) permission checks that may block portal
	# users from accessing private files.
	file_path = os.path.realpath(frappe.get_site_path(export_job.output_file.lstrip("/")))
	site_path = os.path.realpath(frappe.get_site_path())
	if not file_path.startswith(site_path + os.sep):
		frappe.throw(_("Invalid file path"), frappe.PermissionError)
	if not os.path.isfile(file_path):
		frappe.throw(_("Output file not found on disk"))

	with open(file_path, "rb") as f:
		content = f.read()

	if not content:
		frappe.throw(_("Output file is empty"))

	filename = file_records[0].file_name or f"export_{export_job_id}.pdf"

	# Stream the file to the browser as a download
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"

