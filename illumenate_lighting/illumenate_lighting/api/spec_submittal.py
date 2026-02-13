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

# ── DEBUG FLAG  ─────────────────────────────────────────────────────
# Set to True to emit detailed spec-submittal diagnostic messages.
# These show up in the browser warnings list *and* in the Error Log.
# TODO: remove or set False once spec-submittal flow is stable.
SPEC_DEBUG = True
# ────────────────────────────────────────────────────────────────────


def _debug(msg: str, warnings: list | None = None) -> None:
	"""Emit a debug message to the Error Log and optionally to the warnings list."""
	if not SPEC_DEBUG:
		return
	frappe.log_error(title="Spec Submittal DEBUG", message=msg)
	if warnings is not None:
		warnings.append(f"[DEBUG] {msg}")


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
	schedule_line: Any = None,
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
		schedule_line: The fixture schedule line (child table row, if applicable)

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

		if source_doctype == "ilL-Child-Fixture-Schedule-Line" and schedule_line:
			return getattr(schedule_line, source_field, None)

		if source_doctype == "ilL-Rel-Tape Offering" and configured_fixture:
			tape_offering = configured_fixture.tape_offering
			if tape_offering:
				return frappe.db.get_value(
					"ilL-Rel-Tape Offering", tape_offering, source_field
				)

		if source_doctype == "ilL-Spec-Profile":
			# Priority 1: Configured fixture's resolved profile_item
			# ilL-Spec-Profile is autonamed by field:item, so profile_item IS the doc name
			if configured_fixture:
				profile_item = getattr(configured_fixture, "profile_item", None)
				if profile_item and frappe.db.exists("ilL-Spec-Profile", profile_item):
					return frappe.db.get_value("ilL-Spec-Profile", profile_item, source_field)
			# Priority 2: Fixture template's default_profile_spec
			if fixture_template:
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
			# ilL-Child-Driver-Allocation has driver_item (Link→Item), not driver_spec
			# ilL-Spec-Driver is autonamed by field:item, so driver_item IS the doc name
			if configured_fixture.drivers and len(configured_fixture.drivers) > 0:
				driver_item = configured_fixture.drivers[0].driver_item
				if driver_item and frappe.db.exists("ilL-Spec-Driver", driver_item):
					return frappe.db.get_value("ilL-Spec-Driver", driver_item, source_field)

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
	warnings: list | None = None,
) -> bytes | None:
	"""
	Fill form fields in a PDF template with the provided values and flatten the result.

	Uses pypdf to fill AcroForm fields in the PDF, then flattens the PDF by removing
	form field annotations to make the fields non-editable.

	Args:
		pdf_template_path: Path or URL to the PDF template (must be a Frappe file URL)
		field_values: Dictionary mapping field names to values
		warnings: Optional list that debug messages are appended to

	Returns:
		bytes: The filled and flattened PDF as bytes, or None if filling failed
	"""
	try:
		from pypdf import PdfReader, PdfWriter

		_debug(f"_fill_pdf_form_fields: pdf_template_path={pdf_template_path!r}, {len(field_values)} field values", warnings)

		# Only allow Frappe file URLs to prevent path traversal attacks
		if not (
			pdf_template_path.startswith("/files/")
			or pdf_template_path.startswith("/private/files/")
		):
			msg = (
				f"Invalid PDF template path: {pdf_template_path}. "
				"Only Frappe file URLs are allowed."
			)
			_debug(f"_fill_pdf_form_fields: FAIL – {msg}", warnings)
			frappe.log_error(msg, "Spec Submittal Generation Error")
			return None

		# Get the PDF content from Frappe file system
		_debug(f"_fill_pdf_form_fields: looking up File doc for {pdf_template_path!r}", warnings)
		try:
			file_doc = frappe.get_doc("File", {"file_url": pdf_template_path})
		except frappe.DoesNotExistError:
			msg = f"File doc not found for URL: {pdf_template_path}"
			_debug(f"_fill_pdf_form_fields: FAIL – {msg}", warnings)
			frappe.log_error(msg, "Spec Submittal Generation Error")
			return None

		pdf_content = file_doc.get_content()
		_debug(f"_fill_pdf_form_fields: got PDF content ({len(pdf_content)} bytes)", warnings)

		# Read the PDF
		reader = PdfReader(io.BytesIO(pdf_content))

		# Use clone_from to properly copy the entire document structure
		# including the AcroForm root dictionary that defines form fields.
		# writer.add_page() only copies page objects without the AcroForm,
		# which causes update_page_form_field_values to silently fail.
		writer = PdfWriter(clone_from=reader)

		# Detect ALL form fields (not just text – also checkboxes, dropdowns, etc.)
		all_fields = reader.get_fields()
		text_fields = reader.get_form_text_fields()
		_debug(
			f"_fill_pdf_form_fields: PDF has {len(reader.pages)} pages, "
			f"all form fields: {list(all_fields.keys()) if all_fields else 'NONE'}, "
			f"text fields: {list(text_fields.keys()) if text_fields else 'NONE'}",
			warnings,
		)

		if all_fields:
			for page in writer.pages:
				writer.update_page_form_field_values(page, field_values)
		else:
			_debug(
				"_fill_pdf_form_fields: WARNING – PDF has no AcroForm fields; "
				"the template may not be a fillable PDF",
				warnings,
			)

		# Make form fields read-only instead of removing them.
		# Removing Widget annotations strips the appearance streams that
		# contain the visible filled text.  Setting the ReadOnly bit (bit 1
		# of /Ff) preserves the rendered values while preventing editing.
		from pypdf.generic import NameObject, NumberObject

		_debug("_fill_pdf_form_fields: Setting form fields to read-only", warnings)
		for page in writer.pages:
			if "/Annots" in page:
				for annot_ref in page["/Annots"]:
					annot = annot_ref.get_object()
					if annot.get("/Subtype") == "/Widget":
						ff = int(annot.get("/Ff", 0))
						annot[NameObject("/Ff")] = NumberObject(ff | 1)  # ReadOnly bit

		# Write the filled PDF to bytes
		output = io.BytesIO()
		writer.write(output)
		result_bytes = output.getvalue()
		_debug(f"_fill_pdf_form_fields: SUCCESS – output PDF = {len(result_bytes)} bytes", warnings)
		return result_bytes

	except ImportError:
		_debug("_fill_pdf_form_fields: FAIL – pypdf not installed", warnings)
		frappe.log_error("pypdf not installed", "Spec Submittal Generation Error")
		return None
	except Exception as e:
		_debug(f"_fill_pdf_form_fields: EXCEPTION – {type(e).__name__}: {e}", warnings)
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
		_debug(f"_get_pdf_bytes_from_url: looking up File doc with file_url={file_url!r}")
		file_doc = frappe.get_doc("File", {"file_url": file_url})
		content = file_doc.get_content()
		_debug(f"_get_pdf_bytes_from_url: got {len(content) if content else 0} bytes")
		return content
	except Exception as e:
		_debug(f"_get_pdf_bytes_from_url: EXCEPTION for {file_url!r}: {e}")
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


def _gather_line_documents(
	schedule_name: str, include_all_specs: bool = False, warnings: list | None = None,
) -> list[dict]:
	"""
	Gather spec documents from all lines in a schedule.

	Args:
		schedule_name: Name of the schedule to gather documents from
		include_all_specs: If True, include static spec sheets; if False, only filled submittals
		warnings: Optional list that debug messages are appended to

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

	_debug(f"_gather_line_documents: schedule={schedule_name}, lines count={len(schedule.lines)}, include_all_specs={include_all_specs}", warnings)

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

		_debug(
			f"Line {line.line_id}: mfr_type={line.manufacturer_type}, "
			f"configured_fixture={line.configured_fixture}, "
			f"fixture_template={line.fixture_template}, "
			f"fixture_template_override={getattr(line, 'fixture_template_override', None)}",
			warnings,
		)

		if line.manufacturer_type == "ILLUMENATE":
			if line.configured_fixture:
				doc_info["configured_fixture"] = line.configured_fixture

				# Get configured fixture details
				cf = frappe.get_doc("ilL-Configured-Fixture", line.configured_fixture)
				doc_info["fixture_template"] = cf.fixture_template

				_debug(
					f"Line {line.line_id}: CF={line.configured_fixture}, "
					f"cf.fixture_template={cf.fixture_template}, "
					f"cf.spec_submittal={cf.spec_submittal!r}, "
					f"cf.spec_sheet_link={cf.spec_sheet_link!r}",
					warnings,
				)

				if include_all_specs:
					# SPEC_SUBMITTAL_FULL mode: use the static spec sheet (full documentation)
					# instead of the filled submittal (which focuses on one configured fixture)
					_debug(
						f"Line {line.line_id}: FULL mode – looking for spec sheet instead of submittal",
						warnings,
					)

					# 1) cf.spec_sheet_link (fetch_from field – may be stale/empty)
					spec_url = cf.spec_sheet_link
					_debug(f"Line {line.line_id}: Check 1 – cf.spec_sheet_link = {spec_url!r}", warnings)

					# 2) Direct lookup on the Fixture Template (always authoritative)
					if not spec_url and cf.fixture_template:
						template_data = frappe.db.get_value(
							"ilL-Fixture-Template",
							cf.fixture_template,
							["spec_sheet", "spec_submittal_template"],
							as_dict=True,
						)
						_debug(
							f"Line {line.line_id}: Check 2 – template {cf.fixture_template} → "
							f"spec_sheet={template_data.spec_sheet if template_data else None!r}, "
							f"spec_submittal_template={template_data.spec_submittal_template if template_data else None!r}",
							warnings,
						)
						if template_data:
							# Prefer spec_sheet over spec_submittal_template for FULL mode
							spec_url = template_data.spec_sheet or template_data.spec_submittal_template

					# 3) Look for ANY PDF file attached to the Fixture Template
					if not spec_url and cf.fixture_template:
						attached = frappe.get_all(
							"File",
							filters={
								"attached_to_doctype": "ilL-Fixture-Template",
								"attached_to_name": cf.fixture_template,
								"file_url": ["like", "%.pdf"],
							},
							fields=["file_url", "file_name"],
							order_by="creation desc",
						)
						_debug(
							f"Line {line.line_id}: Check 3 – attached PDFs on template: {attached}",
							warnings,
						)
						if attached:
							spec_url = attached[0].file_url

					if spec_url:
						doc_info["spec_document_url"] = spec_url
						_debug(f"Line {line.line_id}: ✓ Spec sheet resolved to {spec_url}", warnings)
					else:
						_debug(f"Line {line.line_id}: ✗ ALL spec sheet lookups exhausted – no document found", warnings)

				else:
					# SPEC_SUBMITTAL mode: use filled submittal PDF
					# Check for existing filled submittal
					if cf.spec_submittal:
						doc_info["spec_document_url"] = cf.spec_submittal
						doc_info["has_submittal"] = True
						_debug(f"Line {line.line_id}: ✓ Using existing spec_submittal: {cf.spec_submittal}", warnings)
					else:
						# Try to generate filled submittal on-the-fly
						_debug(f"Line {line.line_id}: No spec_submittal on CF, trying generate_filled_submittal...", warnings)
						result = generate_filled_submittal(line.configured_fixture, warnings=warnings)
						_debug(
							f"Line {line.line_id}: generate_filled_submittal result: "
							f"success={result.get('success')}, file_url={result.get('file_url')!r}, "
							f"message={result.get('message')!r}",
							warnings,
						)

						if result.get("success") and result.get("file_url"):
							doc_info["spec_document_url"] = result["file_url"]
							doc_info["has_submittal"] = True
						else:
							# No spec submittal available - fall back to spec sheet
							_debug(
								f"Line {line.line_id}: Filled submittal failed, trying spec sheet fallbacks...",
								warnings,
							)

							# 1) cf.spec_sheet_link (fetch_from field – may be stale/empty)
							spec_url = cf.spec_sheet_link
							_debug(f"Line {line.line_id}: Fallback 1 – cf.spec_sheet_link = {spec_url!r}", warnings)

							# 2) Direct lookup on the Fixture Template (always authoritative)
							if not spec_url and cf.fixture_template:
								template_data = frappe.db.get_value(
									"ilL-Fixture-Template",
									cf.fixture_template,
									["spec_sheet", "spec_submittal_template"],
									as_dict=True,
								)
								_debug(
									f"Line {line.line_id}: Fallback 2 – template {cf.fixture_template} → "
									f"spec_sheet={template_data.spec_sheet if template_data else None!r}, "
									f"spec_submittal_template={template_data.spec_submittal_template if template_data else None!r}",
									warnings,
								)
								if template_data:
									spec_url = template_data.spec_sheet or template_data.spec_submittal_template

							# 3) Look for ANY PDF file attached to the Fixture Template
							if not spec_url and cf.fixture_template:
								attached = frappe.get_all(
									"File",
									filters={
										"attached_to_doctype": "ilL-Fixture-Template",
										"attached_to_name": cf.fixture_template,
										"file_url": ["like", "%.pdf"],
									},
									fields=["file_url", "file_name"],
									order_by="creation desc",
								)
								_debug(
									f"Line {line.line_id}: Fallback 3 – attached PDFs on template: {attached}",
									warnings,
								)
								if attached:
									spec_url = attached[0].file_url

							if spec_url:
								doc_info["spec_document_url"] = spec_url
								_debug(f"Line {line.line_id}: ✓ Spec sheet fallback resolved to {spec_url}", warnings)
							else:
								_debug(f"Line {line.line_id}: ✗ ALL spec fallbacks exhausted – no document found", warnings)

			elif include_all_specs:
				# Unconfigured line - use template override or fixture template
				template_name = line.fixture_template_override or line.fixture_template
				_debug(f"Line {line.line_id}: Unconfigured ILLUMENATE, template_name={template_name}", warnings)
				if template_name:
					doc_info["fixture_template"] = template_name
					template_spec = frappe.db.get_value(
						"ilL-Fixture-Template", template_name, "spec_sheet"
					)
					_debug(f"Line {line.line_id}: Template spec_sheet = {template_spec!r}", warnings)
					if template_spec:
						doc_info["spec_document_url"] = template_spec

		elif line.manufacturer_type == "OTHER" and include_all_specs:
			# Other manufacturer - use attached spec sheet
			_debug(f"Line {line.line_id}: OTHER mfr, spec_sheet={line.spec_sheet!r}", warnings)
			if line.spec_sheet:
				doc_info["spec_document_url"] = line.spec_sheet

		elif line.manufacturer_type == "ACCESSORY" and line.accessory_item:
			# Accessory / non-linear item - look for spec sheet on the Item
			item_code = line.accessory_item
			# Try to find a spec submittal or spec sheet attached to the item
			# First check if the item has a spec_submittal_template or spec_sheet field
			item_data = frappe.db.get_value(
				"Item",
				item_code,
				["item_name"],
				as_dict=True,
			)
			if item_data:
				# Look for attached PDF files on this Item
				attached_files = frappe.get_all(
					"File",
					filters={
						"attached_to_doctype": "Item",
						"attached_to_name": item_code,
						"file_url": ["like", "%.pdf"],
					},
					fields=["file_url", "file_name"],
					order_by="creation desc",
				)
				if attached_files:
					# Use the first attached PDF as the spec document
					doc_info["spec_document_url"] = attached_files[0].file_url

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
		line_documents = _gather_line_documents(schedule_name, include_all_specs, warnings)

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
				_debug(
					f"Retrieving PDF for line {doc_info['line_id']}: {doc_info['spec_document_url']}",
					warnings,
				)
				pdf_bytes = _get_pdf_bytes_from_url(doc_info["spec_document_url"])
				if pdf_bytes:
					_debug(f"Line {doc_info['line_id']}: ✓ Got PDF ({len(pdf_bytes)} bytes)", warnings)
					pdf_parts.append(pdf_bytes)
				else:
					_debug(f"Line {doc_info['line_id']}: ✗ _get_pdf_bytes_from_url returned None", warnings)
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
			_debug("generate_spec_submittal_packet: FAIL – no pdf_parts at all (only cover page possible)", warnings)
			return {
				"success": False,
				"message": _("No spec documents found to include in packet"),
				"warnings": warnings,
			}

		_debug(f"generate_spec_submittal_packet: merging {len(pdf_parts)} PDF parts", warnings)

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
def generate_filled_submittal(configured_fixture_name: str, warnings: list | None = None) -> dict:
	"""
	Generate a filled spec submittal PDF for a configured fixture.

	Uses the fixture template's spec_submittal_template and field mappings
	to create a filled PDF.

	Args:
		configured_fixture_name: Name of the ilL-Configured-Fixture
		warnings: Optional list that debug messages are appended to

	Returns:
		dict: Result with keys:
			- success: bool
			- file_url: URL of the generated submittal (if successful)
			- message: Status message
	"""
	try:
		_debug(f"generate_filled_submittal: START for CF={configured_fixture_name}", warnings)

		# Get the configured fixture
		cf = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_name)

		if not cf.fixture_template:
			msg = "Configured fixture has no fixture template"
			_debug(f"generate_filled_submittal: FAIL – {msg}", warnings)
			return {"success": False, "message": _(msg)}

		# Get the fixture template
		template = frappe.get_doc("ilL-Fixture-Template", cf.fixture_template)

		_debug(
			f"generate_filled_submittal: template={cf.fixture_template}, "
			f"spec_submittal_template={template.spec_submittal_template!r}, "
			f"spec_sheet={template.spec_sheet!r}",
			warnings,
		)

		# Get the PDF template - prefer spec_submittal_template, fall back to spec_sheet
		pdf_template = template.spec_submittal_template or template.spec_sheet
		if not pdf_template:
			msg = (
				f"Fixture template '{cf.fixture_template}' has no spec_submittal_template "
				f"AND no spec_sheet attached – cannot generate filled submittal"
			)
			_debug(f"generate_filled_submittal: FAIL – {msg}", warnings)
			return {"success": False, "message": _(msg)}

		_debug(f"generate_filled_submittal: using pdf_template={pdf_template!r}", warnings)

		# Get field mappings
		mappings = _gather_field_mappings(cf.fixture_template)

		_debug(f"generate_filled_submittal: found {len(mappings)} field mappings", warnings)

		if not mappings:
			msg = f"No field mappings defined for fixture template '{cf.fixture_template}'"
			_debug(f"generate_filled_submittal: FAIL – {msg}", warnings)
			return {"success": False, "message": _(msg)}

		# Get project and schedule context (if available)
		schedule = None
		project = None
		schedule_line = None

		# Try to find the schedule line that references this configured fixture
		schedule_line_data = frappe.db.get_value(
			"ilL-Child-Fixture-Schedule-Line",
			{"configured_fixture": configured_fixture_name},
			["name", "parent"],
			as_dict=True,
		)
		if schedule_line_data:
			schedule_line = frappe.get_doc(
				"ilL-Child-Fixture-Schedule-Line", schedule_line_data.name
			)
			# Get the parent schedule
			if schedule_line_data.parent:
				schedule = frappe.get_doc(
					"ilL-Project-Fixture-Schedule", schedule_line_data.parent
				)
				# Get the project from the schedule
				if schedule and schedule.ill_project:
					project = frappe.get_doc("ilL-Project", schedule.ill_project)

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
				schedule_line=schedule_line,
			)
			transformed_value = _apply_transformation(value, mapping.get("transformation"))
			field_values[mapping["pdf_field_name"]] = transformed_value

		_debug(
			f"generate_filled_submittal: field_values built ({len(field_values)} fields): "
			f"{list(field_values.keys())}",
			warnings,
		)

		# Fill the PDF using the template we found earlier
		filled_pdf = _fill_pdf_form_fields(pdf_template, field_values, warnings=warnings)

		if not filled_pdf:
			msg = f"_fill_pdf_form_fields returned None/empty for template={pdf_template!r}"
			_debug(f"generate_filled_submittal: FAIL – {msg}", warnings)
			return {"success": False, "message": _("Failed to fill PDF form fields")}

		_debug(f"generate_filled_submittal: filled PDF size = {len(filled_pdf)} bytes", warnings)

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

		_debug(f"generate_filled_submittal: SUCCESS – file_url={file_doc.file_url}", warnings)

		return {
			"success": True,
			"file_url": file_doc.file_url,
			"message": _("Spec submittal generated successfully"),
		}

	except Exception as e:
		_debug(f"generate_filled_submittal: EXCEPTION – {type(e).__name__}: {e}", warnings)
		frappe.log_error(
			f"Error generating filled submittal: {str(e)}",
			"Spec Submittal Generation Error",
		)
		return {
			"success": False,
			"message": _("Error generating spec submittal: {0}").format(str(e)),
		}
