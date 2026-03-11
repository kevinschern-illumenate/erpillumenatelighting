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
import json
import traceback
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


def _apply_prefix_suffix(value: str, prefix: str | None, suffix: str | None) -> str:
	"""
	Apply prefix and/or suffix to a value.

	Prefix and suffix are applied independently of any transformation.
	If the value is empty but a prefix or suffix is provided, the prefix
	and/or suffix will still be applied.

	Args:
		value: The value string (may be empty)
		prefix: Text to prepend before the value
		suffix: Text to append after the value

	Returns:
		str: The value with prefix and/or suffix applied
	"""
	if not value and not prefix and not suffix:
		return value

	result = value or ""
	if prefix:
		result = prefix + result
	if suffix:
		result = result + suffix
	return result


def _get_source_value(
	source_doctype: str,
	source_field: str,
	configured_fixture: Any = None,
	fixture_template: Any = None,
	schedule: Any = None,
	project: Any = None,
	schedule_line: Any = None,
	warnings: list | None = None,
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
		warnings: Optional list that debug messages are appended to

	Returns:
		The value from the source field, or None if not found
	"""
	try:
		if source_doctype == "ilL-Configured-Fixture" and configured_fixture:
			val = getattr(configured_fixture, source_field, None)
			_debug(
				f"_get_source_value: {source_doctype}.{source_field} → {val!r} "
				f"(doc={configured_fixture.name})",
				warnings,
			)
			return val

		if source_doctype == "ilL-Fixture-Template" and fixture_template:
			val = getattr(fixture_template, source_field, None)
			_debug(
				f"_get_source_value: {source_doctype}.{source_field} → {val!r} "
				f"(doc={fixture_template.name})",
				warnings,
			)
			return val

		if source_doctype == "ilL-Project-Fixture-Schedule" and schedule:
			val = getattr(schedule, source_field, None)
			_debug(
				f"_get_source_value: {source_doctype}.{source_field} → {val!r} "
				f"(doc={schedule.name})",
				warnings,
			)
			return val

		if source_doctype == "ilL-Project" and project:
			val = getattr(project, source_field, None)
			_debug(
				f"_get_source_value: {source_doctype}.{source_field} → {val!r} "
				f"(doc={project.name})",
				warnings,
			)
			return val

		if source_doctype == "ilL-Child-Fixture-Schedule-Line" and schedule_line:
			val = getattr(schedule_line, source_field, None)
			_debug(
				f"_get_source_value: {source_doctype}.{source_field} → {val!r} "
				f"(doc={schedule_line.name})",
				warnings,
			)
			return val

		if source_doctype == "ilL-Rel-Tape Offering" and configured_fixture:
			tape_offering = configured_fixture.tape_offering
			_debug(
				f"_get_source_value: {source_doctype}.{source_field} – "
				f"tape_offering={tape_offering!r}",
				warnings,
			)
			if tape_offering:
				val = frappe.db.get_value(
					"ilL-Rel-Tape Offering", tape_offering, source_field
				)
				_debug(f"_get_source_value: {source_doctype}.{source_field} → {val!r}", warnings)
				return val

		if source_doctype == "ilL-Spec-LED Tape" and configured_fixture:
			tape_offering = configured_fixture.tape_offering
			_debug(
				f"_get_source_value: {source_doctype}.{source_field} – "
				f"tape_offering={tape_offering!r}",
				warnings,
			)
			if tape_offering:
				tape_spec = frappe.db.get_value(
					"ilL-Rel-Tape Offering", tape_offering, "tape_spec"
				)
				_debug(
					f"_get_source_value: {source_doctype}.{source_field} – "
					f"tape_spec={tape_spec!r}",
					warnings,
				)
				if tape_spec:
					val = frappe.db.get_value(
						"ilL-Spec-LED Tape", tape_spec, source_field
					)
					_debug(f"_get_source_value: {source_doctype}.{source_field} → {val!r}", warnings)
					return val

		if source_doctype == "ilL-Spec-Profile":
			# Priority 1: Configured fixture's resolved profile_item
			# ilL-Spec-Profile is autonamed by field:item, so profile_item IS the doc name
			if configured_fixture:
				profile_item = getattr(configured_fixture, "profile_item", None)
				_debug(
					f"_get_source_value: {source_doctype}.{source_field} – "
					f"profile_item={profile_item!r}",
					warnings,
				)
				if profile_item and frappe.db.exists("ilL-Spec-Profile", profile_item):
					val = frappe.db.get_value("ilL-Spec-Profile", profile_item, source_field)
					_debug(f"_get_source_value: {source_doctype}.{source_field} → {val!r} (via profile_item)", warnings)
					return val
			# Priority 2: Fixture template's default_profile_spec
			if fixture_template:
				profile_spec = fixture_template.default_profile_spec
				_debug(
					f"_get_source_value: {source_doctype}.{source_field} – "
					f"default_profile_spec={profile_spec!r}",
					warnings,
				)
				if profile_spec:
					val = frappe.db.get_value("ilL-Spec-Profile", profile_spec, source_field)
					_debug(f"_get_source_value: {source_doctype}.{source_field} → {val!r} (via default_profile_spec)", warnings)
					return val

		if source_doctype == "ilL-Spec-Lens" and configured_fixture:
			lens_appearance = configured_fixture.lens_appearance
			_debug(
				f"_get_source_value: {source_doctype}.{source_field} – "
				f"lens_appearance={lens_appearance!r}",
				warnings,
			)
			if lens_appearance:
				# Get the lens spec linked to this appearance
				lens_spec = frappe.db.get_value(
					"ilL-Attribute-Lens Appearance", lens_appearance, "lens_spec"
				)
				_debug(
					f"_get_source_value: {source_doctype}.{source_field} – "
					f"lens_spec={lens_spec!r}",
					warnings,
				)
				if lens_spec:
					val = frappe.db.get_value("ilL-Spec-Lens", lens_spec, source_field)
					_debug(f"_get_source_value: {source_doctype}.{source_field} → {val!r}", warnings)
					return val

		if source_doctype == "ilL-Spec-Driver" and configured_fixture:
			# Get driver from the first driver allocation if available
			# ilL-Child-Driver-Allocation has driver_item (Link→Item), not driver_spec
			# ilL-Spec-Driver is autonamed by field:item, so driver_item IS the doc name
			has_drivers = configured_fixture.drivers and len(configured_fixture.drivers) > 0
			_debug(
				f"_get_source_value: {source_doctype}.{source_field} – "
				f"has_drivers={has_drivers}, "
				f"driver_count={len(configured_fixture.drivers) if configured_fixture.drivers else 0}",
				warnings,
			)
			if has_drivers:
				driver_item = configured_fixture.drivers[0].driver_item
				_debug(
					f"_get_source_value: {source_doctype}.{source_field} – "
					f"driver_item={driver_item!r}, "
					f"exists={frappe.db.exists('ilL-Spec-Driver', driver_item) if driver_item else False}",
					warnings,
				)
				if driver_item and frappe.db.exists("ilL-Spec-Driver", driver_item):
					# input_protocols is a child table – flatten to comma-separated labels
					if source_field == "input_protocols":
						rows = frappe.get_all(
							"ilL-Child-Driver-Input-Protocol",
							filters={"parent": driver_item},
							fields=["protocol"],
							order_by="idx",
						)
						val = ", ".join(r.protocol for r in rows if r.protocol) or None
						_debug(f"_get_source_value: {source_doctype}.{source_field} → {val!r} (input_protocols)", warnings)
						return val
					val = frappe.db.get_value("ilL-Spec-Driver", driver_item, source_field)
					_debug(f"_get_source_value: {source_doctype}.{source_field} → {val!r}", warnings)
					return val

		# If we got here, no branch matched – log why
		_debug(
			f"_get_source_value: NO MATCH for {source_doctype}.{source_field} – "
			f"configured_fixture={'yes' if configured_fixture else 'NO'}, "
			f"fixture_template={'yes' if fixture_template else 'NO'}, "
			f"schedule={'yes' if schedule else 'NO'}, "
			f"project={'yes' if project else 'NO'}, "
			f"schedule_line={'yes' if schedule_line else 'NO'}",
			warnings,
		)

	except Exception as e:
		tb = traceback.format_exc()
		_debug(
			f"_get_source_value: EXCEPTION for {source_doctype}.{source_field} – "
			f"{type(e).__name__}: {e}\n{tb}",
			warnings,
		)

	return None


def _gather_field_mappings(fixture_template_name: str) -> list[dict]:
	"""
	Get all field mappings for a fixture template.

	Args:
		fixture_template_name: Name of the fixture template

	Returns:
		list: List of mapping dictionaries with pdf_field_name, source_doctype,
			  source_field, transformation, prefix, suffix, and webflow_field
	"""
	base_fields = ["pdf_field_name", "source_doctype", "source_field", "transformation", "prefix", "suffix"]
	try:
		return frappe.get_all(
			"ilL-Spec-Submittal-Mapping",
			filters={"fixture_template": fixture_template_name},
			fields=base_fields + ["webflow_field"],
		)
	except Exception as e:
		# webflow_field column may not exist yet if migration is pending;
		# log the error so it's not silently masked, then fall back.
		frappe.log_error(
			title="Spec Submittal: webflow_field query failed, falling back",
			message=f"Error querying webflow_field for {fixture_template_name}: {e}",
		)
		return frappe.get_all(
			"ilL-Spec-Submittal-Mapping",
			filters={"fixture_template": fixture_template_name},
			fields=base_fields,
		)


def _get_file_doc_by_url(file_url: str, warnings: list | None = None):
	"""
	Look up a Frappe File record by file_url, handling duplicates from re-uploads.

	When a file is re-uploaded to an Attach field, old File records may remain,
	leading to multiple records with different URLs pointing to different physical
	files.  More critically, if the old physical file was removed and re-uploaded
	with the same name, duplicates with the *same* file_url can appear.

	This helper always picks the most recent File record (by creation DESC) so we
	read the latest physical file.  It also catches all lookup errors instead of
	only DoesNotExistError.

	Args:
		file_url: The Frappe file URL (e.g. /files/template.pdf)
		warnings: Optional list that debug messages are appended to

	Returns:
		File document object, or None if not found
	"""
	if not file_url:
		return None

	try:
		# Use get_all to handle duplicate File records gracefully.
		# Sort by creation DESC so we always pick the most recently uploaded copy.
		matches = frappe.get_all(
			"File",
			filters={"file_url": file_url},
			fields=["name"],
			order_by="creation desc",
			limit_page_length=1,
		)
		if not matches:
			_debug(f"_get_file_doc_by_url: no File record found for {file_url!r}", warnings)
			return None

		return frappe.get_doc("File", matches[0].name)
	except Exception as e:
		_debug(f"_get_file_doc_by_url: lookup failed for {file_url!r}: {e}", warnings)
		frappe.log_error(
			title="Spec Submittal: File lookup failed",
			message=f"Could not look up File record for {file_url}: {e}",
		)
		return None


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
		from pypdf.generic import BooleanObject, NameObject, NumberObject

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
		file_doc = _get_file_doc_by_url(pdf_template_path, warnings)
		if not file_doc:
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
			# Log mismatch detection: compare mapping field names against PDF form field names
			pdf_field_names = set(all_fields.keys())
			mapping_field_names = set(field_values.keys())
			matched = mapping_field_names & pdf_field_names
			in_mapping_not_pdf = mapping_field_names - pdf_field_names
			in_pdf_not_mapping = pdf_field_names - mapping_field_names
			_debug(
				f"_fill_pdf_form_fields: FIELD MATCH REPORT – "
				f"matched={len(matched)}, "
				f"in_mapping_but_NOT_in_pdf={len(in_mapping_not_pdf)}, "
				f"in_pdf_but_NOT_in_mapping={len(in_pdf_not_mapping)}",
				warnings,
			)
			if in_mapping_not_pdf:
				_debug(
					f"_fill_pdf_form_fields: ⚠ MAPPING FIELDS NOT IN PDF: {sorted(in_mapping_not_pdf)}",
					warnings,
				)
			if in_pdf_not_mapping:
				_debug(
					f"_fill_pdf_form_fields: ⚠ PDF FIELDS NOT IN MAPPING: {sorted(in_pdf_not_mapping)}",
					warnings,
				)

			# Log actual values being written for matched fields
			_debug(
				f"_fill_pdf_form_fields: FIELD VALUES BEING WRITTEN: "
				+ ", ".join(
					f"{k}={field_values[k]!r}" for k in sorted(matched)
				),
				warnings,
			)

			for page in writer.pages:
				writer.update_page_form_field_values(page, field_values)

			# Explicitly set /NeedAppearances so PDF viewers regenerate
			# appearance streams from the /V values we just wrote.
			# update_page_form_field_values with auto_regenerate=True
			# (default) should do this, but can fail silently when the
			# writer was created via clone_from.
			if "/AcroForm" in writer._root_object:
				writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)
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
		from pypdf import PdfWriter

		writer = PdfWriter()

		for pdf_bytes in pdf_list:
			if pdf_bytes:
				# Use append() instead of add_page() so that the full
				# document structure—including the AcroForm dictionary
				# and its /NeedAppearances flag—is preserved.  add_page()
				# only copies page objects, which strips the AcroForm and
				# causes filled form-field values to become invisible.
				writer.append(io.BytesIO(pdf_bytes))

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
		file_doc = _get_file_doc_by_url(file_url)
		if not file_doc:
			_debug(f"_get_pdf_bytes_from_url: no File record for {file_url!r}")
			return None
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
					# SPEC_SUBMITTAL mode: always (re)generate the filled submittal
					# so that the latest field mappings and data values are used.
					_debug(f"Line {line.line_id}: Generating filled submittal (regenerate)...", warnings)
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
						# Filled submittal generation failed – fall back to spec sheet
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

			elif getattr(line, "configured_tape_neon", None):
				# ── Tape/Neon submittal logic ──────────────────────────────
				ctn = frappe.get_doc("ilL-Configured-Tape-Neon", line.configured_tape_neon)
				doc_info["configured_tape_neon"] = line.configured_tape_neon
				doc_info["tape_neon_template"] = ctn.tape_neon_template

				if include_all_specs:
					# FULL mode: use static spec sheet from template
					spec_url = None
					if ctn.tape_neon_template:
						template_data = frappe.db.get_value(
							"ilL-Tape-Neon-Template", ctn.tape_neon_template,
							["spec_sheet", "spec_submittal_template"], as_dict=True,
						)
						if template_data:
							spec_url = template_data.spec_sheet or template_data.spec_submittal_template
					if spec_url:
						doc_info["spec_document_url"] = spec_url
						_debug(f"Line {line.line_id}: ✓ Neon spec sheet resolved to {spec_url}", warnings)
					else:
						_debug(f"Line {line.line_id}: ✗ No neon spec sheet found", warnings)
				else:
					# SUBMITTAL mode: always (re)generate the filled neon submittal
					# so that the latest field mappings and data values are used.
					_debug(f"Line {line.line_id}: Generating filled neon submittal (regenerate)...", warnings)
					result = generate_filled_neon_submittal(line.configured_tape_neon, warnings=warnings)
					if result.get("success") and result.get("file_url"):
						doc_info["spec_document_url"] = result["file_url"]
						doc_info["has_submittal"] = True
					else:
						# Fall back to static spec sheet
						spec_url = None
						if ctn.tape_neon_template:
							template_data = frappe.db.get_value(
								"ilL-Tape-Neon-Template", ctn.tape_neon_template,
								["spec_sheet", "spec_submittal_template"], as_dict=True,
							)
							if template_data:
								spec_url = template_data.spec_sheet or template_data.spec_submittal_template
						if spec_url:
							doc_info["spec_document_url"] = spec_url
							_debug(f"Line {line.line_id}: ✓ Neon spec sheet fallback resolved to {spec_url}", warnings)
						else:
							_debug(f"Line {line.line_id}: ✗ ALL neon spec fallbacks exhausted", warnings)

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

		elif line.manufacturer_type == "OTHER":
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
	# Handle include_cover arriving as string from the frontend
	if isinstance(include_cover, str):
		include_cover = include_cover.lower() not in ("0", "false", "no", "")

	warnings = []
	pdf_parts = []
	job_name = None

	try:
		# Validate schedule access
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_check_schedule_access,
			_create_export_job,
			_update_export_job_status,
		)

		has_access, error = _check_schedule_access(schedule_name)
		if not has_access:
			return {
				"success": False,
				"message": error or _("Access denied"),
				"warnings": [],
			}

		# Create export job record for tracking
		job_name = _create_export_job(schedule_name, export_type)

		# Determine if we should include all spec sheets
		include_all_specs = export_type == "SPEC_SUBMITTAL_FULL"

		_update_export_job_status(job_name, "RUNNING")

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
			_update_export_job_status(job_name, "FAILED", error_log="No spec documents found")
			return {
				"success": False,
				"message": _("No spec documents found to include in packet"),
				"warnings": warnings,
			}

		_debug(f"generate_spec_submittal_packet: merging {len(pdf_parts)} PDF parts", warnings)

		# Merge all PDFs
		merged_pdf = _merge_pdfs(pdf_parts)
		if not merged_pdf:
			_update_export_job_status(job_name, "FAILED", error_log="Failed to merge PDF documents")
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

		_update_export_job_status(job_name, "COMPLETE", output_file=file_doc.file_url)

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
		if job_name:
			_update_export_job_status(job_name, "FAILED", error_log=str(e))
		return {
			"success": False,
			"message": _("Error generating spec submittal packet: {0}").format(str(e)),
			"warnings": warnings,
		}


@frappe.whitelist()
def generate_filled_submittal(configured_fixture_name: str, warnings: list | None = None, webflow_overrides: dict | None = None, is_private: int = 1) -> dict:
	"""
	Generate a filled spec submittal PDF for a configured fixture.

	Uses the fixture template's spec_submittal_template and field mappings
	to create a filled PDF.

	Args:
		configured_fixture_name: Name of the ilL-Configured-Fixture
		warnings: Optional list that debug messages are appended to
		webflow_overrides: Optional dict of webflow parameter values
			(e.g. {"project_name": "...", "fixture_type": "..."}).
			When a mapping has a webflow_field set and the corresponding
			key exists in this dict, the webflow value takes priority
			over the source_doctype/source_field value.
		is_private: 1 for private files (default, used by project schedules),
			0 for public files (used by Webflow guest downloads).

	Returns:
		dict: Result with keys:
			- success: bool
			- file_url: URL of the generated submittal (if successful)
			- message: Status message
	"""
	# Handle parameters that may arrive as JSON strings from the API
	if isinstance(warnings, str):
		try:
			warnings = json.loads(warnings)
		except (json.JSONDecodeError, TypeError):
			warnings = None
	if isinstance(webflow_overrides, str):
		try:
			webflow_overrides = json.loads(webflow_overrides)
		except (json.JSONDecodeError, TypeError):
			webflow_overrides = None

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
		_debug(
			f"generate_filled_submittal: webflow_overrides={webflow_overrides!r}",
			warnings,
		)
		field_values = {}
		for mapping in mappings:
			pdf_field = mapping["pdf_field_name"]
			src_dt = mapping["source_doctype"]
			src_fld = mapping["source_field"]

			# Check for webflow override first
			webflow_key = mapping.get("webflow_field")
			if webflow_key and webflow_overrides and webflow_key in webflow_overrides:
				value = webflow_overrides[webflow_key]
				_debug(
					f"  mapping[{pdf_field}]: WEBFLOW OVERRIDE {webflow_key!r} → {value!r}",
					warnings,
				)
			else:
				if webflow_key and not webflow_overrides:
					_debug(
						f"  mapping[{pdf_field}]: webflow_field={webflow_key!r} set but no overrides provided",
						warnings,
					)
				elif webflow_key and webflow_overrides and webflow_key not in webflow_overrides:
					_debug(
						f"  mapping[{pdf_field}]: webflow_field={webflow_key!r} set but key not in overrides {list(webflow_overrides.keys())}",
						warnings,
					)
				value = _get_source_value(
					src_dt,
					src_fld,
					configured_fixture=cf,
					fixture_template=template,
					schedule=schedule,
					project=project,
					schedule_line=schedule_line,
					warnings=warnings,
				)
			transformed_value = _apply_transformation(value, mapping.get("transformation"))
			transformed_value = _apply_prefix_suffix(
				transformed_value, mapping.get("prefix"), mapping.get("suffix")
			)
			field_values[pdf_field] = transformed_value
			_debug(
				f"  mapping[{pdf_field}]: {src_dt}.{src_fld} "
				f"raw={value!r} → final={transformed_value!r}"
				+ (f" (transform={mapping.get('transformation')})" if mapping.get("transformation") else "")
				+ (f" (prefix={mapping.get('prefix')!r})" if mapping.get("prefix") else "")
				+ (f" (suffix={mapping.get('suffix')!r})" if mapping.get("suffix") else ""),
				warnings,
			)

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

		# Save the filled PDF and update the configured fixture.
		# Under Guest context (Webflow downloads) the user has no write
		# permission on ilL-Configured-Fixture.  Temporarily switching to
		# Administrator is the most reliable way to bypass every permission
		# check in Frappe (save_file, File doc hooks, doc.save, etc.).
		filename = f"Spec_Submittal_{configured_fixture_name}_{nowdate()}.pdf"
		_prev_user = frappe.session.user
		try:
			frappe.set_user("Administrator")
			file_doc = save_file(
				filename,
				filled_pdf,
				"ilL-Configured-Fixture",
				configured_fixture_name,
				is_private=is_private,
			)

			# Update the configured fixture with the submittal link
			cf.spec_submittal = file_doc.file_url
			cf.save(ignore_permissions=True)
		finally:
			frappe.set_user(_prev_user)

		_debug(f"generate_filled_submittal: SUCCESS – file_url={file_doc.file_url}", warnings)

		return {
			"success": True,
			"file_url": file_doc.file_url,
			"message": _("Spec submittal generated successfully"),
		}

	except Exception as e:
		_debug(f"generate_filled_submittal: EXCEPTION – {type(e).__name__}: {e}", warnings)
		frappe.log_error(
			f"Error generating filled submittal: {type(e).__name__}: {e}\n{traceback.format_exc()}",
			"Spec Submittal Generation Error",
		)
		return {
			"success": False,
			"message": _("Error generating spec submittal: {0}: {1}").format(
				type(e).__name__, str(e) or "insufficient permissions"
			),
		}


# ═══════════════════════════════════════════════════════════════════════
# NEON / TAPE SUBMITTAL SUPPORT
# ═══════════════════════════════════════════════════════════════════════


def _get_neon_source_value(
	source_doctype: str,
	source_field: str,
	configured_tape_neon: Any = None,
	tape_neon_template: Any = None,
	schedule: Any = None,
	project: Any = None,
	schedule_line: Any = None,
	warnings: list | None = None,
) -> Any:
	"""
	Get a value from the specified source doctype and field for tape/neon products.

	Mirrors _get_source_value() but resolves fields for the tape/neon doctype chain.

	Args:
		source_doctype: The DocType to pull the value from
		source_field: The field name to get
		configured_tape_neon: The configured tape/neon document (if applicable)
		tape_neon_template: The tape/neon template document (if applicable)
		schedule: The schedule document
		project: The project document
		schedule_line: The fixture schedule line (child table row, if applicable)
		warnings: Optional list that debug messages are appended to

	Returns:
		The value from the source field, or None if not found
	"""
	try:
		if source_doctype == "ilL-Configured-Tape-Neon" and configured_tape_neon:
			val = getattr(configured_tape_neon, source_field, None)
			_debug(
				f"_get_neon_source_value: {source_doctype}.{source_field} → {val!r} "
				f"(doc={configured_tape_neon.name})",
				warnings,
			)
			return val

		if source_doctype == "ilL-Tape-Neon-Template" and tape_neon_template:
			val = getattr(tape_neon_template, source_field, None)
			_debug(
				f"_get_neon_source_value: {source_doctype}.{source_field} → {val!r} "
				f"(doc={tape_neon_template.name})",
				warnings,
			)
			return val

		if source_doctype == "ilL-Spec-LED Tape" and configured_tape_neon:
			tape_spec = getattr(configured_tape_neon, "tape_spec", None)
			_debug(
				f"_get_neon_source_value: {source_doctype}.{source_field} – "
				f"tape_spec={tape_spec!r}",
				warnings,
			)
			if tape_spec:
				val = frappe.db.get_value("ilL-Spec-LED Tape", tape_spec, source_field)
				_debug(f"_get_neon_source_value: {source_doctype}.{source_field} → {val!r}", warnings)
				return val

		if source_doctype == "ilL-Rel-Tape Offering" and configured_tape_neon:
			tape_offering = getattr(configured_tape_neon, "tape_offering", None)
			_debug(
				f"_get_neon_source_value: {source_doctype}.{source_field} – "
				f"tape_offering={tape_offering!r}",
				warnings,
			)
			if tape_offering:
				val = frappe.db.get_value("ilL-Rel-Tape Offering", tape_offering, source_field)
				_debug(f"_get_neon_source_value: {source_doctype}.{source_field} → {val!r}", warnings)
				return val

		if source_doctype == "ilL-Project-Fixture-Schedule" and schedule:
			val = getattr(schedule, source_field, None)
			_debug(
				f"_get_neon_source_value: {source_doctype}.{source_field} → {val!r} "
				f"(doc={schedule.name})",
				warnings,
			)
			return val

		if source_doctype == "ilL-Project" and project:
			val = getattr(project, source_field, None)
			_debug(
				f"_get_neon_source_value: {source_doctype}.{source_field} → {val!r} "
				f"(doc={project.name})",
				warnings,
			)
			return val

		if source_doctype == "ilL-Child-Fixture-Schedule-Line" and schedule_line:
			val = getattr(schedule_line, source_field, None)
			_debug(
				f"_get_neon_source_value: {source_doctype}.{source_field} → {val!r} "
				f"(doc={schedule_line.name})",
				warnings,
			)
			return val

		# If we got here, no branch matched – log why
		_debug(
			f"_get_neon_source_value: NO MATCH for {source_doctype}.{source_field} – "
			f"configured_tape_neon={'yes' if configured_tape_neon else 'NO'}, "
			f"tape_neon_template={'yes' if tape_neon_template else 'NO'}, "
			f"schedule={'yes' if schedule else 'NO'}, "
			f"project={'yes' if project else 'NO'}, "
			f"schedule_line={'yes' if schedule_line else 'NO'}",
			warnings,
		)

	except Exception as e:
		tb = traceback.format_exc()
		_debug(
			f"_get_neon_source_value: EXCEPTION for {source_doctype}.{source_field} – "
			f"{type(e).__name__}: {e}\n{tb}",
			warnings,
		)

	return None


def _gather_neon_field_mappings(tape_neon_template_name: str) -> list[dict]:
	"""
	Get all field mappings for a tape/neon template.

	Args:
		tape_neon_template_name: Name of the tape/neon template

	Returns:
		list: List of mapping dictionaries with pdf_field_name, source_doctype,
			  source_field, transformation, prefix, suffix, and webflow_field
	"""
	base_fields = ["pdf_field_name", "source_doctype", "source_field", "transformation", "prefix", "suffix"]
	try:
		return frappe.get_all(
			"ilL-Neon-Submittal-Mapping",
			filters={"tape_neon_template": tape_neon_template_name},
			fields=base_fields + ["webflow_field"],
		)
	except Exception as e:
		# webflow_field column may not exist yet if migration is pending;
		# log the error so it's not silently masked, then fall back.
		frappe.log_error(
			title="Neon Submittal: webflow_field query failed, falling back",
			message=f"Error querying webflow_field for {tape_neon_template_name}: {e}",
		)
		return frappe.get_all(
			"ilL-Neon-Submittal-Mapping",
			filters={"tape_neon_template": tape_neon_template_name},
			fields=base_fields,
		)


@frappe.whitelist()
def generate_filled_neon_submittal(configured_tape_neon_name: str, warnings: list | None = None, webflow_overrides: dict | None = None) -> dict:
	"""
	Generate a filled spec submittal PDF for a configured tape/neon product.

	Uses the tape/neon template's spec_submittal_template and field mappings
	to create a filled PDF.

	Args:
		configured_tape_neon_name: Name of the ilL-Configured-Tape-Neon
		warnings: Optional list that debug messages are appended to
		webflow_overrides: Optional dict of webflow parameter values
			(e.g. {"project_name": "...", "fixture_type": "..."}).
			When a mapping has a webflow_field set and the corresponding
			key exists in this dict, the webflow value takes priority
			over the source_doctype/source_field value.

	Returns:
		dict: Result with keys:
			- success: bool
			- file_url: URL of the generated submittal (if successful)
			- message: Status message
	"""
	# Handle parameters that may arrive as JSON strings from the API
	if isinstance(warnings, str):
		try:
			warnings = json.loads(warnings)
		except (json.JSONDecodeError, TypeError):
			warnings = None
	if isinstance(webflow_overrides, str):
		try:
			webflow_overrides = json.loads(webflow_overrides)
		except (json.JSONDecodeError, TypeError):
			webflow_overrides = None

	try:
		_debug(f"generate_filled_neon_submittal: START for CTN={configured_tape_neon_name}", warnings)

		# Get the configured tape/neon
		ctn = frappe.get_doc("ilL-Configured-Tape-Neon", configured_tape_neon_name)

		if not ctn.tape_neon_template:
			msg = "Configured tape/neon has no tape_neon_template"
			_debug(f"generate_filled_neon_submittal: FAIL – {msg}", warnings)
			return {"success": False, "message": _(msg)}

		# Get the tape/neon template
		template = frappe.get_doc("ilL-Tape-Neon-Template", ctn.tape_neon_template)

		_debug(
			f"generate_filled_neon_submittal: template={ctn.tape_neon_template}, "
			f"spec_submittal_template={template.spec_submittal_template!r}, "
			f"spec_sheet={template.spec_sheet!r}",
			warnings,
		)

		# Get the PDF template - prefer spec_submittal_template, fall back to spec_sheet
		pdf_template = template.spec_submittal_template or template.spec_sheet
		if not pdf_template:
			msg = (
				f"Tape/Neon template '{ctn.tape_neon_template}' has no spec_submittal_template "
				f"AND no spec_sheet attached – cannot generate filled submittal"
			)
			_debug(f"generate_filled_neon_submittal: FAIL – {msg}", warnings)
			return {"success": False, "message": _(msg)}

		_debug(f"generate_filled_neon_submittal: using pdf_template={pdf_template!r}", warnings)

		# Get field mappings
		mappings = _gather_neon_field_mappings(ctn.tape_neon_template)

		_debug(f"generate_filled_neon_submittal: found {len(mappings)} field mappings", warnings)

		if not mappings:
			msg = f"No field mappings defined for tape/neon template '{ctn.tape_neon_template}'"
			_debug(f"generate_filled_neon_submittal: FAIL – {msg}", warnings)
			return {"success": False, "message": _(msg)}

		# Get project and schedule context (if available)
		schedule = None
		project = None
		schedule_line = None

		# Try to find the schedule line that references this configured tape/neon
		schedule_line_data = frappe.db.get_value(
			"ilL-Child-Fixture-Schedule-Line",
			{"configured_tape_neon": configured_tape_neon_name},
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
		_debug(
			f"generate_filled_neon_submittal: webflow_overrides={webflow_overrides!r}",
			warnings,
		)
		field_values = {}
		for mapping in mappings:
			pdf_field = mapping["pdf_field_name"]
			src_dt = mapping["source_doctype"]
			src_fld = mapping["source_field"]

			# Check for webflow override first
			webflow_key = mapping.get("webflow_field")
			if webflow_key and webflow_overrides and webflow_key in webflow_overrides:
				value = webflow_overrides[webflow_key]
				_debug(
					f"  mapping[{pdf_field}]: WEBFLOW OVERRIDE {webflow_key!r} → {value!r}",
					warnings,
				)
			else:
				if webflow_key and not webflow_overrides:
					_debug(
						f"  mapping[{pdf_field}]: webflow_field={webflow_key!r} set but no overrides provided",
						warnings,
					)
				elif webflow_key and webflow_overrides and webflow_key not in webflow_overrides:
					_debug(
						f"  mapping[{pdf_field}]: webflow_field={webflow_key!r} set but key not in overrides {list(webflow_overrides.keys())}",
						warnings,
					)
				value = _get_neon_source_value(
					src_dt,
					src_fld,
					configured_tape_neon=ctn,
					tape_neon_template=template,
					schedule=schedule,
					project=project,
					schedule_line=schedule_line,
					warnings=warnings,
				)
			transformed_value = _apply_transformation(value, mapping.get("transformation"))
			transformed_value = _apply_prefix_suffix(
				transformed_value, mapping.get("prefix"), mapping.get("suffix")
			)
			field_values[pdf_field] = transformed_value
			_debug(
				f"  mapping[{pdf_field}]: {src_dt}.{src_fld} "
				f"raw={value!r} → final={transformed_value!r}"
				+ (f" (transform={mapping.get('transformation')})" if mapping.get("transformation") else "")
				+ (f" (prefix={mapping.get('prefix')!r})" if mapping.get("prefix") else "")
				+ (f" (suffix={mapping.get('suffix')!r})" if mapping.get("suffix") else ""),
				warnings,
			)

		_debug(
			f"generate_filled_neon_submittal: field_values built ({len(field_values)} fields): "
			f"{list(field_values.keys())}",
			warnings,
		)

		# Fill the PDF using the template we found earlier
		filled_pdf = _fill_pdf_form_fields(pdf_template, field_values, warnings=warnings)

		if not filled_pdf:
			msg = f"_fill_pdf_form_fields returned None/empty for template={pdf_template!r}"
			_debug(f"generate_filled_neon_submittal: FAIL – {msg}", warnings)
			return {"success": False, "message": _("Failed to fill PDF form fields")}

		_debug(f"generate_filled_neon_submittal: filled PDF size = {len(filled_pdf)} bytes", warnings)

		# Save the filled PDF and update the configured tape/neon.
		# Elevate to Administrator to bypass permission checks that
		# fail under Guest or limited-role contexts.
		filename = f"Spec_Submittal_{configured_tape_neon_name}_{nowdate()}.pdf"
		_prev_user = frappe.session.user
		try:
			frappe.set_user("Administrator")
			file_doc = save_file(
				filename,
				filled_pdf,
				"ilL-Configured-Tape-Neon",
				configured_tape_neon_name,
				is_private=1,
			)

			# Update the configured tape/neon with the submittal link
			ctn.spec_submittal = file_doc.file_url
			ctn.save(ignore_permissions=True)
		finally:
			frappe.set_user(_prev_user)

		_debug(f"generate_filled_neon_submittal: SUCCESS – file_url={file_doc.file_url}", warnings)

		return {
			"success": True,
			"file_url": file_doc.file_url,
			"message": _("Spec submittal generated successfully"),
		}

	except Exception as e:
		_debug(f"generate_filled_neon_submittal: EXCEPTION – {type(e).__name__}: {e}", warnings)
		frappe.log_error(
			f"Error generating filled neon submittal: {type(e).__name__}: {e}\n{traceback.format_exc()}",
			"Neon Spec Submittal Generation Error",
		)
		return {
			"success": False,
			"message": _("Error generating neon spec submittal: {0}: {1}").format(
				type(e).__name__, str(e) or "insufficient permissions"
			),
		}
