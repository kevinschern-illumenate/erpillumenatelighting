# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Spec Submittal API

This module provides API endpoints for generating spec submittal packets that aggregate
spec sheets and fillable spec submittals from fixture schedule lines.

Supports:
- ilLumenate configured fixtures (filled submittal PDFs)
- ilLumenate unconfigured templates (static spec sheets)
- ilLumenate items/accessories
- Other manufacturer fixtures (attached spec sheets)

Export Types:
- SPEC_SUBMITTAL: Cover page + spec submittals only (filled PDFs for configured fixtures)
- SPEC_SUBMITTAL_FULL: Cover page + all spec sheets + spec submittals
"""

import io
from datetime import datetime
from typing import Any

import frappe
from frappe import _
from frappe.utils import now, nowdate
from frappe.utils.file_manager import save_file

# Conversion constants
MM_PER_INCH = 25.4
MM_PER_FOOT = 304.8


def _apply_transformation(value: Any, transformation: str | None) -> str:
	"""
	Apply a transformation to a value before filling into PDF form field.

	Args:
		value: The source value to transform
		transformation: The transformation type to apply

	Returns:
		str: The transformed value as a string
	"""
	if value is None:
		return ""

	if not transformation or transformation == "None":
		return str(value)

	if transformation == "MM_TO_INCHES":
		try:
			return f"{float(value) / MM_PER_INCH:.2f}"
		except (ValueError, TypeError):
			return str(value)

	if transformation == "MM_TO_FEET":
		try:
			return f"{float(value) / MM_PER_FOOT:.2f}"
		except (ValueError, TypeError):
			return str(value)

	if transformation == "UPPERCASE":
		return str(value).upper()

	if transformation == "LOWERCASE":
		return str(value).lower()

	if transformation == "ROUND_2_DECIMALS":
		try:
			return f"{float(value):.2f}"
		except (ValueError, TypeError):
			return str(value)

	if transformation == "DATE_FORMAT":
		try:
			if isinstance(value, datetime):
				return value.strftime("%Y-%m-%d")
			return str(value)
		except (ValueError, TypeError):
			return str(value)

	return str(value)


def _get_source_value(
	source_doctype: str,
	source_field: str,
	configured_fixture: Any = None,
	fixture_template: Any = None,
	schedule: Any = None,
	project: Any = None,
) -> Any:
	"""
	Get a value from the specified source doctype and field.

	Args:
		source_doctype: The DocType to pull the value from
		source_field: The field name to get
		configured_fixture: The configured fixture document (if applicable)
		fixture_template: The fixture template document (if applicable)
		schedule: The schedule document
		project: The project document

	Returns:
		The value from the source field, or None if not found
	"""
	try:
		if source_doctype == "ilL-Configured-Fixture" and configured_fixture:
			return getattr(configured_fixture, source_field, None)

		if source_doctype == "ilL-Fixture-Template" and fixture_template:
			return getattr(fixture_template, source_field, None)

		if source_doctype == "ilL-Project-Fixture-Schedule" and schedule:
			return getattr(schedule, source_field, None)

		if source_doctype == "ilL-Project" and project:
			return getattr(project, source_field, None)

		if source_doctype == "ilL-Rel-Tape Offering" and configured_fixture:
			tape_offering = configured_fixture.tape_offering
			if tape_offering:
				return frappe.db.get_value(
					"ilL-Rel-Tape Offering", tape_offering, source_field
				)

		if source_doctype == "ilL-Spec-Profile" and fixture_template:
			profile_spec = fixture_template.default_profile_spec
			if profile_spec:
				return frappe.db.get_value("ilL-Spec-Profile", profile_spec, source_field)

		if source_doctype == "ilL-Spec-Lens" and configured_fixture:
			lens_appearance = configured_fixture.lens_appearance
			if lens_appearance:
				# Get the lens spec linked to this appearance
				lens_spec = frappe.db.get_value(
					"ilL-Attribute-Lens Appearance", lens_appearance, "lens_spec"
				)
				if lens_spec:
					return frappe.db.get_value("ilL-Spec-Lens", lens_spec, source_field)

		if source_doctype == "ilL-Spec-Driver" and configured_fixture:
			# Get driver from the first driver allocation if available
			if configured_fixture.drivers and len(configured_fixture.drivers) > 0:
				driver_spec = configured_fixture.drivers[0].driver_spec
				if driver_spec:
					return frappe.db.get_value("ilL-Spec-Driver", driver_spec, source_field)

	except Exception:
		pass

	return None


def _gather_field_mappings(fixture_template_name: str) -> list[dict]:
	"""
	Get all field mappings for a fixture template.

	Args:
		fixture_template_name: Name of the fixture template

	Returns:
		list: List of mapping dictionaries with pdf_field_name, source_doctype,
			  source_field, and transformation
	"""
	return frappe.get_all(
		"ilL-Spec-Submittal-Mapping",
		filters={"fixture_template": fixture_template_name},
		fields=["pdf_field_name", "source_doctype", "source_field", "transformation"],
	)


def _fill_pdf_form_fields(
	pdf_template_path: str,
	field_values: dict[str, str],
) -> bytes | None:
	"""
	Fill form fields in a PDF template with the provided values.

	Uses pypdf to fill AcroForm fields in the PDF.

	Args:
		pdf_template_path: Path or URL to the PDF template
		field_values: Dictionary mapping field names to values

	Returns:
		bytes: The filled PDF as bytes, or None if filling failed
	"""
	try:
		from pypdf import PdfReader, PdfWriter

		# Get the PDF content
		if pdf_template_path.startswith("/files/") or pdf_template_path.startswith(
			"/private/files/"
		):
			# It's a Frappe file path
			file_doc = frappe.get_doc(
				"File", {"file_url": pdf_template_path}
			)
			pdf_content = file_doc.get_content()
		else:
			# Try to read as a file path
			with open(pdf_template_path, "rb") as f:
				pdf_content = f.read()

		# Read the PDF
		reader = PdfReader(io.BytesIO(pdf_content))
		writer = PdfWriter()

		# Copy pages and fill form fields
		for page in reader.pages:
			writer.add_page(page)

		# Update form fields
		if reader.get_form_text_fields():
			writer.update_page_form_field_values(writer.pages[0], field_values)

		# Write the filled PDF to bytes
		output = io.BytesIO()
		writer.write(output)
		return output.getvalue()

	except ImportError:
		frappe.log_error("pypdf not installed", "Spec Submittal Generation Error")
		return None
	except Exception as e:
		frappe.log_error(
			f"Error filling PDF form fields: {str(e)}", "Spec Submittal Generation Error"
		)
		return None


def _merge_pdfs(pdf_list: list[bytes]) -> bytes | None:
	"""
	Merge multiple PDFs into a single PDF.

	Args:
		pdf_list: List of PDF contents as bytes

	Returns:
		bytes: The merged PDF as bytes, or None if merging failed
	"""
	if not pdf_list:
		return None

	try:
		from pypdf import PdfReader, PdfWriter

		writer = PdfWriter()

		for pdf_bytes in pdf_list:
			if pdf_bytes:
				reader = PdfReader(io.BytesIO(pdf_bytes))
				for page in reader.pages:
					writer.add_page(page)

		output = io.BytesIO()
		writer.write(output)
		return output.getvalue()

	except ImportError:
		frappe.log_error("pypdf not installed", "Spec Submittal Generation Error")
		return None
	except Exception as e:
		frappe.log_error(f"Error merging PDFs: {str(e)}", "Spec Submittal Generation Error")
		return None


def _get_pdf_bytes_from_url(file_url: str) -> bytes | None:
	"""
	Get PDF content as bytes from a Frappe file URL.

	Args:
		file_url: The file URL (e.g., /files/spec.pdf or /private/files/spec.pdf)

	Returns:
		bytes: The PDF content, or None if not found
	"""
	try:
		file_doc = frappe.get_doc("File", {"file_url": file_url})
		return file_doc.get_content()
	except Exception as e:
		frappe.log_error(
			f"Error getting PDF from URL {file_url}: {str(e)}",
			"Spec Submittal Generation Error",
		)
		return None


def _generate_cover_page(
	schedule_name: str,
	project_name: str | None,
	fixture_lines: list[dict],
	include_date: bool = True,
) -> bytes | None:
	"""
	Generate a cover page PDF for the spec submittal packet.

	Args:
		schedule_name: Name of the schedule
		project_name: Name of the project (optional)
		fixture_lines: List of fixture line summaries for the TOC
		include_date: Whether to include generation date

	Returns:
		bytes: The cover page PDF as bytes, or None if generation failed
	"""
	try:
		# Get schedule and project details
		schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

		project = None
		if project_name or schedule.ill_project:
			project_id = project_name or schedule.ill_project
			project = frappe.get_doc("ilL-Project", project_id)

		# Prepare context for template
		context = {
			"schedule": schedule,
			"project": project,
			"fixture_lines": fixture_lines,
			"generation_date": nowdate() if include_date else None,
			"generation_datetime": now() if include_date else None,
			"company_name": "ilLumenate Lighting",
		}

		# Render the cover page template
		html_content = frappe.render_template(
			"illumenate_lighting/templates/pages/spec_submittal_cover.html",
			context,
		)

		# Convert HTML to PDF using frappe's PDF generation
		from frappe.utils.pdf import get_pdf

		pdf_bytes = get_pdf(html_content)
		return pdf_bytes

	except Exception as e:
		frappe.log_error(
			f"Error generating cover page: {str(e)}", "Spec Submittal Generation Error"
		)
		return None


def _gather_line_documents(schedule_name: str, include_all_specs: bool = False) -> list[dict]:
	"""
	Gather spec documents from all lines in a schedule.

	Args:
		schedule_name: Name of the schedule to gather documents from
		include_all_specs: If True, include static spec sheets; if False, only filled submittals

	Returns:
		list: List of document info dicts with keys:
			- line_id: The line identifier
			- qty: Quantity
			- location: Location description
			- manufacturer_type: ILLUMENATE, ACCESSORY, or OTHER
			- spec_document_url: URL of the spec document (if any)
			- has_submittal: Whether a filled submittal is available
			- configured_fixture: Name of configured fixture (if any)
	"""
	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)
	documents = []

	for line in schedule.lines:
		doc_info = {
			"line_id": line.line_id,
			"qty": line.qty,
			"location": line.location,
			"manufacturer_type": line.manufacturer_type,
			"notes": line.notes,
			"spec_document_url": None,
			"has_submittal": False,
			"configured_fixture": None,
			"fixture_template": None,
		}

		if line.manufacturer_type == "ILLUMENATE":
			if line.configured_fixture:
				doc_info["configured_fixture"] = line.configured_fixture

				# Get configured fixture details
				cf = frappe.get_doc("ilL-Configured-Fixture", line.configured_fixture)
				doc_info["fixture_template"] = cf.fixture_template

				# Check for filled submittal
				if cf.spec_submittal:
					doc_info["spec_document_url"] = cf.spec_submittal
					doc_info["has_submittal"] = True
				elif include_all_specs:
					# Fall back to template spec sheet
					if cf.spec_sheet_link:
						doc_info["spec_document_url"] = cf.spec_sheet_link
					elif cf.fixture_template:
						template_spec = frappe.db.get_value(
							"ilL-Fixture-Template", cf.fixture_template, "spec_sheet"
						)
						if template_spec:
							doc_info["spec_document_url"] = template_spec

			elif include_all_specs:
				# Unconfigured line - use template override or fixture template
				template_name = line.fixture_template_override or line.fixture_template
				if template_name:
					doc_info["fixture_template"] = template_name
					template_spec = frappe.db.get_value(
						"ilL-Fixture-Template", template_name, "spec_sheet"
					)
					if template_spec:
						doc_info["spec_document_url"] = template_spec

		elif line.manufacturer_type == "OTHER" and include_all_specs:
			# Other manufacturer - use attached spec sheet
			if line.spec_sheet:
				doc_info["spec_document_url"] = line.spec_sheet

		documents.append(doc_info)

	return documents


@frappe.whitelist()
def generate_spec_submittal_packet(
	schedule_name: str,
	export_type: str = "SPEC_SUBMITTAL",
	include_cover: bool = True,
) -> dict:
	"""
	Generate a spec submittal packet for a fixture schedule.

	This aggregates spec sheets and filled spec submittals from all lines
	in the schedule into a single PDF packet.

	Args:
		schedule_name: Name of the ilL-Project-Fixture-Schedule
		export_type: SPEC_SUBMITTAL (submittals only) or SPEC_SUBMITTAL_FULL (all specs)
		include_cover: Whether to include a cover page with TOC

	Returns:
		dict: Result with keys:
			- success: bool
			- file_url: URL of the generated packet (if successful)
			- message: Status message
			- warnings: List of warning messages
	"""
	warnings = []
	pdf_parts = []

	try:
		# Validate schedule access
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_check_schedule_access,
		)

		has_access, error = _check_schedule_access(schedule_name)
		if not has_access:
			return {
				"success": False,
				"message": error or _("Access denied"),
				"warnings": [],
			}

		# Determine if we should include all spec sheets
		include_all_specs = export_type == "SPEC_SUBMITTAL_FULL"

		# Gather documents from all lines
		line_documents = _gather_line_documents(schedule_name, include_all_specs)

		# Get schedule for project info
		schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

		# Generate cover page if requested
		if include_cover:
			cover_pdf = _generate_cover_page(
				schedule_name,
				schedule.ill_project,
				line_documents,
			)
			if cover_pdf:
				pdf_parts.append(cover_pdf)
			else:
				warnings.append(_("Failed to generate cover page"))

		# Collect PDFs from each line
		for doc_info in line_documents:
			if doc_info["spec_document_url"]:
				pdf_bytes = _get_pdf_bytes_from_url(doc_info["spec_document_url"])
				if pdf_bytes:
					pdf_parts.append(pdf_bytes)
				else:
					warnings.append(
						_("Could not retrieve spec document for line {0}").format(
							doc_info["line_id"]
						)
					)
			elif doc_info["manufacturer_type"] != "ACCESSORY":
				# Missing spec document (not an accessory)
				warnings.append(
					_("No spec document available for line {0}").format(doc_info["line_id"])
				)

		if not pdf_parts:
			return {
				"success": False,
				"message": _("No spec documents found to include in packet"),
				"warnings": warnings,
			}

		# Merge all PDFs
		merged_pdf = _merge_pdfs(pdf_parts)
		if not merged_pdf:
			return {
				"success": False,
				"message": _("Failed to merge PDF documents"),
				"warnings": warnings,
			}

		# Save the merged PDF
		filename = f"Spec_Submittal_Packet_{schedule_name}_{nowdate()}.pdf"
		file_doc = save_file(
			filename,
			merged_pdf,
			"ilL-Project-Fixture-Schedule",
			schedule_name,
			is_private=1,
		)

		return {
			"success": True,
			"file_url": file_doc.file_url,
			"message": _("Spec submittal packet generated successfully"),
			"warnings": warnings,
		}

	except Exception as e:
		frappe.log_error(
			f"Error generating spec submittal packet: {str(e)}",
			"Spec Submittal Generation Error",
		)
		return {
			"success": False,
			"message": _("Error generating spec submittal packet: {0}").format(str(e)),
			"warnings": warnings,
		}


@frappe.whitelist()
def generate_filled_submittal(configured_fixture_name: str) -> dict:
	"""
	Generate a filled spec submittal PDF for a configured fixture.

	Uses the fixture template's spec_submittal_template and field mappings
	to create a filled PDF.

	Args:
		configured_fixture_name: Name of the ilL-Configured-Fixture

	Returns:
		dict: Result with keys:
			- success: bool
			- file_url: URL of the generated submittal (if successful)
			- message: Status message
	"""
	try:
		# Get the configured fixture
		cf = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_name)

		if not cf.fixture_template:
			return {
				"success": False,
				"message": _("Configured fixture has no fixture template"),
			}

		# Get the fixture template
		template = frappe.get_doc("ilL-Fixture-Template", cf.fixture_template)

		if not template.spec_submittal_template:
			return {
				"success": False,
				"message": _("Fixture template has no spec submittal template"),
			}

		# Get field mappings
		mappings = _gather_field_mappings(cf.fixture_template)

		if not mappings:
			return {
				"success": False,
				"message": _("No field mappings defined for this fixture template"),
			}

		# Get project and schedule context (if available)
		schedule = None
		project = None

		# Build field values
		field_values = {}
		for mapping in mappings:
			value = _get_source_value(
				mapping["source_doctype"],
				mapping["source_field"],
				configured_fixture=cf,
				fixture_template=template,
				schedule=schedule,
				project=project,
			)
			transformed_value = _apply_transformation(value, mapping.get("transformation"))
			field_values[mapping["pdf_field_name"]] = transformed_value

		# Fill the PDF
		filled_pdf = _fill_pdf_form_fields(template.spec_submittal_template, field_values)

		if not filled_pdf:
			return {
				"success": False,
				"message": _("Failed to fill PDF form fields"),
			}

		# Save the filled PDF
		filename = f"Spec_Submittal_{configured_fixture_name}_{nowdate()}.pdf"
		file_doc = save_file(
			filename,
			filled_pdf,
			"ilL-Configured-Fixture",
			configured_fixture_name,
			is_private=1,
		)

		# Update the configured fixture with the submittal link
		cf.spec_submittal = file_doc.file_url
		cf.save(ignore_permissions=True)

		return {
			"success": True,
			"file_url": file_doc.file_url,
			"message": _("Spec submittal generated successfully"),
		}

	except Exception as e:
		frappe.log_error(
			f"Error generating filled submittal: {str(e)}",
			"Spec Submittal Generation Error",
		)
		return {
			"success": False,
			"message": _("Error generating spec submittal: {0}").format(str(e)),
		}
