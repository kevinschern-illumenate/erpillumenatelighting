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

import hashlib
import inspect
import io
import json
import traceback
from datetime import datetime
from typing import Any

import frappe
from frappe import _
from frappe.utils import now, nowdate

from illumenate_lighting.illumenate_lighting.portal.pdf_mapping import set_value as _set_mapped_value

# Conversion constants
MM_PER_INCH = 25.4
MM_PER_FOOT = 304.8

# ── DEBUG FLAG  ─────────────────────────────────────────────────────
# Set to True to emit detailed spec-submittal diagnostic messages.
# These show up in the browser warnings list *and* in the Error Log.
SPEC_DEBUG = False
# ────────────────────────────────────────────────────────────────────


def _debug(msg: str, warnings: list | None = None) -> None:
	"""Emit a debug message to the Error Log and optionally to the warnings list."""
	if not SPEC_DEBUG:
		return
	frappe.log_error(title="Spec Submittal DEBUG", message=msg)
	if warnings is not None:
		warnings.append(f"[DEBUG] {msg}")


def _warn(msg: str, warnings: list | None = None) -> None:
	"""Surface an operational warning to the caller.

	Unlike :func:`_debug`, this always appends to the ``warnings`` list
	regardless of ``SPEC_DEBUG`` so that PDF-fill mismatches (a common
	cause of silently blank submittals) reach the API response.
	"""
	if warnings is not None:
		warnings.append(msg)


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

	if transformation == "MAX_FOOTAGE_100W":
		# 80W / (W/ft) = max footage at 80% derating of a 100W supply
		try:
			watts = float(value)
			if not watts:
				return ""
			return str(round(80.0 / watts, 1))
		except (ValueError, TypeError):
			return str(value)

	return str(value)


def _apply_logic(value: str, logic: str | None) -> str:
	"""
	Apply a post-transformation logic modifier to a value.

	Args:
		value: The (already transformed) value as a string
		logic: The logic modifier to apply

	Returns:
		str: The modified value
	"""
	if not logic or logic == "None":
		return value

	if logic == "0.00_TO_BLANK":
		if value is None:
			return ""
		stripped = str(value).strip()
		if stripped == "":
			return ""
		try:
			if float(stripped) == 0.0:
				return ""
		except (ValueError, TypeError):
			pass
		return value

	return value


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


def _get_linked_webflow_product(link_field: str, template_name: str, warnings: list | None = None) -> Any:
	"""
	Find the ilL-Webflow-Product linked to a fixture or tape/neon template.

	Args:
		link_field: The link field on ilL-Webflow-Product that references the
			template ("fixture_template" or "tape_neon_template").
		template_name: Name of the template to match.
		warnings: Optional list that debug messages are appended to.

	Returns:
		The loaded ilL-Webflow-Product document, or None if none is linked.
	"""
	if not template_name:
		return None
	try:
		# Prefer an active product; fall back to any linked product.
		name = frappe.db.get_value(
			"ilL-Webflow-Product",
			{link_field: template_name, "is_active": 1},
			"name",
		) or frappe.db.get_value(
			"ilL-Webflow-Product",
			{link_field: template_name},
			"name",
		)
		if not name:
			_debug(
				f"_get_linked_webflow_product: no ilL-Webflow-Product with "
				f"{link_field}={template_name!r}",
				warnings,
			)
			return None
		doc = frappe.get_doc("ilL-Webflow-Product", name)
		_debug(
			f"_get_linked_webflow_product: {link_field}={template_name!r} → {name!r}",
			warnings,
		)
		return doc
	except Exception as e:
		_debug(
			f"_get_linked_webflow_product: EXCEPTION for {link_field}={template_name!r} – "
			f"{type(e).__name__}: {e}",
			warnings,
		)
		return None


def _explicit_schedule_context(field, configured_name, line_name):
	if not line_name or frappe.flags.get("ill_product_download"):
		return None, None, None
	from illumenate_lighting.illumenate_lighting.portal.access import can_read_schedule

	line = frappe.get_doc("ilL-Child-Fixture-Schedule-Line", line_name)
	if line.get(field) != configured_name or line.parenttype != "ilL-Project-Fixture-Schedule":
		frappe.throw("This line does not reference the requested build", frappe.PermissionError)
	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", line.parent)
	if not can_read_schedule(schedule, frappe.session.user):
		frappe.throw("Schedule access denied", frappe.PermissionError)
	project = frappe.get_doc("ilL-Project", schedule.ill_project) if schedule.ill_project else None
	return schedule, project, line


def _commercial_source_blocked(doctype, field):
	if not (frappe.flags.get("ill_product_download") or frappe.flags.get("ill_packet_job")):
		return False
	# These documents are an unpriced engineering projection.
	terms = ("price", "cost", "rate", "margin", "discount", "msrp", "valuation", "amount", "customer", "dealer", "pricing")
	return any(term in (field or "").lower().split("_") for term in terms) or doctype in ("Item Price", "Customer", "Quotation", "Sales Order")


def _get_source_value(
	source_doctype: str,
	source_field: str,
	configured_fixture: Any = None,
	fixture_template: Any = None,
	schedule: Any = None,
	project: Any = None,
	schedule_line: Any = None,
	webflow_product: Any = None,
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
		webflow_product: The Webflow product linked to the fixture template (if applicable)
		warnings: Optional list that debug messages are appended to

	Returns:
		The value from the source field, or None if not found
	"""
	if _commercial_source_blocked(source_doctype, source_field):
		return None
	from illumenate_lighting.illumenate_lighting.api.engineering_sources import resolve
	handled, value = resolve(configured_fixture, source_doctype, source_field)
	if handled:
		return value
	try:
		if source_doctype == "ilL-Webflow-Product" and webflow_product:
			val = getattr(webflow_product, source_field, None)
			_debug(
				f"_get_source_value: {source_doctype}.{source_field} → {val!r} "
				f"(doc={webflow_product.name})",
				warnings,
			)
			return val

		if source_doctype == "ilL-Configured-Fixture" and configured_fixture:
			# Computed virtual fields (prefixed with __) – resolve before getattr fallback
			if source_field == "__start_leader_cable_len_mm":
				segs = getattr(configured_fixture, "segments", None)
				val = segs[0].start_leader_len_mm if segs and len(segs) > 0 else None
				_debug(
					f"_get_source_value: {source_doctype}.{source_field} → {val!r} "
					f"(doc={configured_fixture.name}, segments={len(segs) if segs else 0})",
					warnings,
				)
				return val
			if source_field == "__end_length_indicator":
				val = "J" if configured_fixture.is_multi_segment else ""
				_debug(
					f"_get_source_value: {source_doctype}.{source_field} → {val!r} "
					f"(doc={configured_fixture.name}, is_multi_segment={configured_fixture.is_multi_segment})",
					warnings,
				)
				return val

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
			f"webflow_product={'yes' if webflow_product else 'NO'}, "
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
	base_fields = ["required_value", "pdf_field_name", "source_doctype", "source_field", "transformation", "logic", "prefix", "suffix"]
	webflow_fields = ["webflow_field", "webflow_skip_transformation", "webflow_prefix_suffix", "webflow_prefix", "webflow_suffix"]
	try:
		return frappe.get_all(
			"ilL-Spec-Submittal-Mapping",
			filters={"fixture_template": fixture_template_name},
			fields=base_fields + webflow_fields,
		)
	except Exception as e:
		# webflow columns may not exist yet if migration is pending;
		# log the error so it's not silently masked, then fall back.
		frappe.log_error(
			title="Spec Submittal: webflow fields query failed, falling back",
			message=f"Error querying webflow fields for {fixture_template_name}: {e}",
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
			ignore_permissions=True,
		)
		if not matches:
			_debug(f"_get_file_doc_by_url: no File record found for {file_url!r}", warnings)
			return None

		return frappe.get_doc("File", matches[0].name, ignore_permissions=True)
	except Exception as e:
		_debug(f"_get_file_doc_by_url: lookup failed for {file_url!r}: {e}", warnings)
		frappe.log_error(
			title="Spec Submittal: File lookup failed",
			message=f"Could not look up File record for {file_url}: {e}",
		)
		return None


def _make_form_fields_unique(writer, warnings: list | None = None) -> None:
	"""
	Give every top-level AcroForm field in ``writer`` a document-unique name.

	When several filled copies of the *same* PDF template are merged into one
	packet, AcroForm fields that share a fully-qualified name are treated by the
	PDF specification as a single field with a single value. That is why the
	spec-submittal data was repeating across every fixture in the packet: each
	filled submittal reused the template's field names, so merging collapsed
	them into one shared value.

	Prefixing each document's field names with a random, document-unique token
	keeps the fields — and their filled values and appearance streams —
	independent after merging, while preserving the rendered text. This is a
	version-independent safeguard that complements pypdf's native flattening
	(which removes the fields entirely when available).
	"""
	try:
		import uuid

		from pypdf.generic import NameObject, TextStringObject

		root = writer._root_object
		if "/AcroForm" not in root:
			return
		acroform = root["/AcroForm"].get_object()
		if "/Fields" not in acroform:
			return

		prefix = f"f{uuid.uuid4().hex[:10]}_"
		renamed = 0
		for field_ref in acroform["/Fields"]:
			field = field_ref.get_object()
			# Only rename top-level fields. Child widgets inherit their
			# fully-qualified name from the parent, so prefixing the parent is
			# sufficient (and prefixing a child would break that inheritance).
			if "/Parent" in field:
				continue
			if "/T" in field:
				field[NameObject("/T")] = TextStringObject(prefix + str(field["/T"]))
				renamed += 1
		_debug(
			f"_make_form_fields_unique: prefixed {renamed} field name(s) with {prefix!r}",
			warnings,
		)
	except Exception as e:  # pragma: no cover - defensive
		_debug(
			f"_make_form_fields_unique: EXCEPTION – {type(e).__name__}: {e}",
			warnings,
		)


def _remove_form_fields(writer, warnings: list | None = None) -> None:
	"""
	Remove every AcroForm widget annotation and the AcroForm dictionary.

	pypdf's native flattening — ``update_page_form_field_values(..., flatten=True)``
	— bakes each field's appearance stream into the page content stream but, per
	its documented API contract, *does not remove the widget annotation itself*.
	A PDF viewer then renders both the baked-in text **and** the still-live widget
	appearance, overlaying each value on top of itself (the doubled/overlapping
	text seen after export). Dropping the now-redundant widgets (and the empty
	AcroForm) ensures every flattened value is rendered exactly once.
	"""
	try:
		from pypdf.generic import ArrayObject, NameObject

		removed = 0
		for page in writer.pages:
			if "/Annots" not in page:
				continue
			kept = ArrayObject()
			for annot_ref in page["/Annots"]:
				annot = annot_ref.get_object()
				if annot.get("/Subtype") == "/Widget":
					removed += 1
					continue
				kept.append(annot_ref)
			page[NameObject("/Annots")] = kept

		root = writer._root_object
		if "/AcroForm" in root:
			del root[NameObject("/AcroForm")]

		_debug(
			f"_remove_form_fields: removed {removed} widget annotation(s) after native flatten",
			warnings,
		)
	except Exception as e:  # pragma: no cover - defensive
		_debug(
			f"_remove_form_fields: EXCEPTION – {type(e).__name__}: {e}",
			warnings,
		)


def _fill_pdf_form_fields(
	pdf_template_path: str,
	field_values: dict[str, str],
	warnings: list | None = None,
	*, provenance: dict | None = None,
) -> bytes | None:
	"""
	Fill form fields in a PDF template with the provided values and flatten the result.

	Uses pypdf to fill AcroForm fields in the PDF, then flattens the PDF so the
	values become part of the page content. Flattening happens *per fixture*,
	before the filled copies are merged into a packet, so that identically named
	fields from different copies cannot collapse into a single shared value.

	When the installed pypdf supports native flattening it is used directly;
	otherwise every field is given a document-unique name as a fallback so the
	merge cannot collapse same-named fields.

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
		if provenance is not None:
			provenance.update(master_file=file_doc.name, master_url=pdf_template_path,
				master_sha256=hashlib.sha256(pdf_content).hexdigest())
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
		if not all_fields or not field_values or set(field_values) - set(all_fields):
			_warn("PDF filling blocked: the template must contain every mapped form field.", warnings)
			return None
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
				_warn(
					f"PDF template is missing {len(in_mapping_not_pdf)} mapped field(s); "
					f"these values were not written: {sorted(in_mapping_not_pdf)}",
					warnings,
				)
			if in_pdf_not_mapping:
				_debug(
					f"_fill_pdf_form_fields: ⚠ PDF FIELDS NOT IN MAPPING: {sorted(in_pdf_not_mapping)}",
					warnings,
				)
				_warn(
					f"{len(in_pdf_not_mapping)} PDF field(s) have no mapping and will be left "
					f"blank: {sorted(in_pdf_not_mapping)}",
					warnings,
				)
			if not matched:
				_warn(
					"No PDF form fields matched the field mapping; the generated "
					"submittal will be blank.",
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

			# Flatten each filled submittal *before* it is merged into a packet.
			# Every copy of the same template carries identically named AcroForm
			# fields, and merging live forms collapses same-named fields into a
			# single shared value — which is why the submittal data was repeating
			# across every fixture. Native pypdf flattening (pypdf>=4.3) bakes the
			# values into the page and removes the fields entirely; older versions
			# fall back to the unique field-name safeguard below.
			try:
				supports_flatten = "flatten" in inspect.signature(
					writer.update_page_form_field_values
				).parameters
			except (TypeError, ValueError):
				supports_flatten = False

			for page in writer.pages:
				if supports_flatten:
					writer.update_page_form_field_values(
						page, field_values, flatten=True
					)
				else:
					writer.update_page_form_field_values(page, field_values)

			if supports_flatten:
				# Native flatten bakes each field's appearance stream into the
				# page content but, per pypdf's API, leaves the widget annotation
				# in place. Left alone, the viewer renders both the baked-in text
				# and the live widget appearance, overlaying each value on itself.
				# Remove the redundant widgets (and the AcroForm) so each value
				# renders exactly once.
				_remove_form_fields(writer, warnings)
				_debug(
					"_fill_pdf_form_fields: form fields flattened via native pypdf flatten",
					warnings,
				)

			# Explicitly set /NeedAppearances so PDF viewers regenerate
			# appearance streams from the /V values we just wrote. This is a
			# no-op when native flattening already removed the fields.
			# update_page_form_field_values with auto_regenerate=True
			# (default) should do this, but can fail silently when the
			# writer was created via clone_from.
			if "/AcroForm" in writer._root_object:
				writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)

			# Give any remaining fields document-unique names so that merging
			# multiple filled copies cannot collapse identically named fields
			# into one shared value. When native flattening removed the fields
			# this is a harmless no-op.
			_make_form_fields_unique(writer, warnings)
		else:
			_debug(
				"_fill_pdf_form_fields: WARNING – PDF has no AcroForm fields; "
				"the template may not be a fillable PDF",
				warnings,
			)
			_warn(
				"PDF template has no fillable form fields; the generated submittal "
				"will not contain any filled values.",
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


def _gather_line_documents(schedule_name: str, include_all_specs: bool = False, warnings: list | None = None) -> list[dict]:
	from illumenate_lighting.illumenate_lighting.portal.packets import gather

	return gather(frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name), warnings if warnings is not None else [])


@frappe.whitelist(methods=["POST"])
def generate_spec_submittal_packet(schedule_name: str, export_type: str = "SPEC_SUBMITTAL", include_cover: bool = True, allow_partial: bool = False) -> dict:
	from illumenate_lighting.illumenate_lighting.portal.packet_jobs import request

	return request(schedule_name, export_type, include_cover, allow_partial=allow_partial)


def generate_filled_submittal(configured_fixture_name: str, warnings: list | None = None, webflow_overrides: dict | None = None, is_private: int = 1, schedule_line: str | None = None, *, _configured_doc=None, _schedule_context=None) -> dict:
	"""
	Generate a filled spec submittal PDF for a configured fixture.

	Uses the fixture template's spec_submittal_template and field mappings
	to create a filled PDF.

	.. note::
		This is an internal helper and is intentionally **not** whitelisted.
		Callers that need to expose it over HTTP (e.g. project schedule
		packets or Webflow spec-sheet downloads) must do so through their
		own whitelisted entry points, which are responsible for access
		control (``_check_schedule_access``) and for publishing the file.

	Args:
		configured_fixture_name: Name of the ilL-Configured-Fixture
		warnings: Optional list that debug/warning messages are appended to
		webflow_overrides: Optional dict of webflow parameter values
			(e.g. {"project_name": "...", "fixture_type": "..."}).
			When a mapping has a webflow_field set and the corresponding
			key exists in this dict, the webflow value takes priority
			over the source_doctype/source_field value.
		is_private: Retained for backwards compatibility but ignored; the
			file is always created private. Callers that need a public file
			must explicitly publish it after generation (e.g. via
			``_ensure_public_file``).

	Returns:
		dict: Result with keys:
			- success: bool
			- file_url: URL of the generated submittal (if successful)
			- message: Status message
			- warnings: list of warnings raised during generation
	"""
	# Handle parameters that may arrive as JSON strings from the API
	if isinstance(warnings, str):
		try:
			warnings = json.loads(warnings)
		except (json.JSONDecodeError, TypeError):
			warnings = None
	if warnings is None:
		warnings = []
	# Security: never allow this helper to create a public file. Public
	# exposure must be an explicit downstream step so it cannot be forced
	# by an untrusted caller.
	is_private = 1
	if isinstance(webflow_overrides, str):
		try:
			webflow_overrides = json.loads(webflow_overrides)
		except (json.JSONDecodeError, TypeError):
			webflow_overrides = None

	try:
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_save_file_ignore_permissions,
		)

		_debug(f"generate_filled_submittal: START for CF={configured_fixture_name}", warnings)

		# Get the configured fixture
		cf = _configured_doc if _configured_doc is not None else frappe.get_doc("ilL-Configured-Fixture", configured_fixture_name)

		if not cf.fixture_template:
			msg = "Configured fixture has no fixture template"
			_debug(f"generate_filled_submittal: FAIL – {msg}", warnings)
			return {"success": False, "message": _(msg), "warnings": warnings}

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
			return {"success": False, "message": _(msg), "warnings": warnings}

		_debug(f"generate_filled_submittal: using pdf_template={pdf_template!r}", warnings)

		# Get field mappings
		mappings = _gather_field_mappings(cf.fixture_template)

		_debug(f"generate_filled_submittal: found {len(mappings)} field mappings", warnings)

		if not mappings:
			msg = f"No field mappings defined for fixture template '{cf.fixture_template}'"
			_debug(f"generate_filled_submittal: FAIL – {msg}", warnings)
			return {"success": False, "message": _(msg), "warnings": warnings}

		schedule, project, schedule_line = _schedule_context or _explicit_schedule_context("configured_fixture", configured_fixture_name, schedule_line)

		# Get the Webflow product linked to this fixture template (if any)
		webflow_product = _get_linked_webflow_product(
			"fixture_template", cf.fixture_template, warnings
		)

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
			webflow_active = webflow_key and webflow_overrides and webflow_key in webflow_overrides
			if webflow_active:
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
					webflow_product=webflow_product,
					warnings=warnings,
				)
			# Skip the transformation when a Webflow value is active and the
			# mapping opts out (the Webflow value is already in its final format).
			if webflow_active and mapping.get("webflow_skip_transformation"):
				transformed_value = "" if value is None else str(value)
			else:
				transformed_value = _apply_transformation(value, mapping.get("transformation"))

			transformed_value = _apply_logic(transformed_value, mapping.get("logic"))

			# Determine prefix/suffix based on webflow_prefix_suffix setting
			if webflow_active:
				ps_mode = mapping.get("webflow_prefix_suffix") or "Keep"
				if ps_mode == "Override":
					prefix = mapping.get("webflow_prefix")
					suffix = mapping.get("webflow_suffix")
				elif ps_mode == "None":
					prefix = None
					suffix = None
				else:  # Keep or blank
					prefix = mapping.get("prefix")
					suffix = mapping.get("suffix")
			else:
				prefix = mapping.get("prefix")
				suffix = mapping.get("suffix")

			transformed_value = _apply_prefix_suffix(
				transformed_value, prefix, suffix
			)
			_set_mapped_value(field_values, mapping, value, transformed_value)
			_debug(
				f"  mapping[{pdf_field}]: {src_dt}.{src_fld} "
				f"raw={value!r} → final={transformed_value!r}"
				+ (f" (transform={mapping.get('transformation')})" if mapping.get("transformation") else "")
				+ (f" (logic={mapping.get('logic')})" if mapping.get("logic") else "")
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
		from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint

		mapping_snapshot = json.loads(frappe.as_json(mappings))
		provenance = {"mapping_snapshot": mapping_snapshot, "mapping_hash": fingerprint(mapping_snapshot),
			"values_hash": fingerprint(field_values), "template": {"doctype": template.doctype, "name": template.name}}
		filled_pdf = _fill_pdf_form_fields(pdf_template, field_values, warnings=warnings, provenance=provenance)

		if not filled_pdf:
			msg = f"_fill_pdf_form_fields returned None/empty for template={pdf_template!r}"
			_debug(f"generate_filled_submittal: FAIL – {msg}", warnings)
			return {"success": False, "message": _("Failed to fill PDF form fields"), "warnings": warnings}

		_debug(f"generate_filled_submittal: filled PDF size = {len(filled_pdf)} bytes", warnings)

		# Save the filled PDF – use ignore_permissions to avoid switching
		# the session user (which corrupts the Frappe session for portal users).
		filename = f"Spec_Submittal_{configured_fixture_name}_{nowdate()}.pdf"
		file_doc = _save_file_ignore_permissions(
			filename, filled_pdf, "ilL-Configured-Fixture", configured_fixture_name,
			is_private=is_private,
		)

		# Update the configured fixture with the submittal link
		if not (frappe.flags.get("ill_product_download") or frappe.flags.get("ill_packet_job")):
			cf.spec_submittal = file_doc.file_url
			cf.save(ignore_permissions=True)

		_debug(f"generate_filled_submittal: SUCCESS – file_url={file_doc.file_url}", warnings)

		return {
			"success": True,
			"file_url": file_doc.file_url,
			"provenance": provenance,
			"message": _("Spec submittal generated successfully"),
			"warnings": warnings,
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
			"warnings": warnings,
		}




# ═══════════════════════════════════════════════════════════════════════
# LED SHEET SUBMITTAL SUPPORT
# ═══════════════════════════════════════════════════════════════════════


def _gather_sheet_field_mappings(led_sheet_template_name: str) -> list[dict]:
	base_fields = ["required_value", "pdf_field_name", "source_doctype", "source_field", "transformation", "logic", "prefix", "suffix"]
	webflow_fields = ["webflow_field", "webflow_skip_transformation", "webflow_prefix_suffix", "webflow_prefix", "webflow_suffix"]
	try:
		return frappe.get_all("ilL-LED-Sheet-Submittal-Mapping", filters={"led_sheet_template": led_sheet_template_name}, fields=base_fields + webflow_fields)
	except Exception:
		return frappe.get_all("ilL-LED-Sheet-Submittal-Mapping", filters={"led_sheet_template": led_sheet_template_name}, fields=base_fields)


def _get_sheet_source_value(source_doctype, source_field, configured_sheet_doc=None, template_doc=None, spec_doc=None, schedule_doc=None, project_doc=None, line_doc=None, warnings=None):
	if _commercial_source_blocked(source_doctype, source_field):
		return None
	if source_doctype == "ilL-Spec-LED-Sheet" and configured_sheet_doc and configured_sheet_doc.get("engine_version") == "led-sheet-2":
		# A new PDF may use today's form/marketing copy, but its electrical and
		# dimensional values must still describe the pinned physical build.
		build = json.loads(configured_sheet_doc.get("build_snapshot_json") or "{}") or configured_sheet_doc
		engineering = build.get("sheet_engineering") or {}
		if source_field == "total_sheet_watts":
			return build.get("watts_per_panel")
		return engineering.get(source_field, build.get(source_field))
	lookup = {
		"ilL-Configured-LED-Sheet": configured_sheet_doc,
		"ilL-LED-Sheet-Template": template_doc,
		"ilL-Spec-LED-Sheet": spec_doc,
		"ilL-Project-Fixture-Schedule": schedule_doc,
		"ilL-Project": project_doc,
		"ilL-Child-Fixture-Schedule-Line": line_doc,
	}
	doc = lookup.get(source_doctype)
	if doc:
		try:
			val = getattr(doc, source_field, None)
			_debug(f"_get_sheet_source_value: {source_doctype}.{source_field} → {val!r}", warnings)
			return val
		except Exception as e:
			_debug(f"_get_sheet_source_value: missing {source_doctype}.{source_field}: {e}", warnings)
			return None
	_debug(f"_get_sheet_source_value: NO MATCH for {source_doctype}.{source_field}", warnings)
	return None


def generate_filled_sheet_submittal(configured_sheet_name: str, warnings: list | None = None, webflow_overrides: dict | None = None, is_private: int = 1, schedule_line: str | None = None, *, _configured_doc=None, _schedule_context=None) -> dict:
	if isinstance(warnings, str):
		try:
			warnings = json.loads(warnings)
		except Exception:
			warnings = None
	if warnings is None:
		warnings = []
	if isinstance(webflow_overrides, str):
		try:
			webflow_overrides = json.loads(webflow_overrides)
		except Exception:
			webflow_overrides = None
	try:
		from illumenate_lighting.illumenate_lighting.api.exports import _save_file_ignore_permissions
		configured = _configured_doc if _configured_doc is not None else frappe.get_doc("ilL-Configured-LED-Sheet", configured_sheet_name)
		if not configured.sheet_template:
			return {"success": False, "message": _("Configured LED Sheet has no sheet_template"), "warnings": warnings}
		template = frappe.get_doc("ilL-LED-Sheet-Template", configured.sheet_template)
		spec = frappe.get_doc("ilL-Spec-LED-Sheet", configured.sheet_spec) if configured.sheet_spec else None
		pdf_template = template.spec_submittal_template or template.spec_sheet
		if not pdf_template:
			return {"success": False, "message": _("LED Sheet template has no spec submittal template or spec sheet"), "warnings": warnings}
		mappings = _gather_sheet_field_mappings(configured.sheet_template)
		if not mappings:
			return {"success": False, "message": _("No LED Sheet field mappings defined"), "warnings": warnings}
		schedule, project, line = _schedule_context or _explicit_schedule_context("configured_led_sheet", configured_sheet_name, schedule_line)
		field_values = {}
		for mapping in mappings:
			webflow_key = mapping.get("webflow_field")
			webflow_active = webflow_key and webflow_overrides and webflow_key in webflow_overrides
			value = webflow_overrides[webflow_key] if webflow_active else _get_sheet_source_value(mapping.get("source_doctype"), mapping.get("source_field"), configured, template, spec, schedule, project, line, warnings)
			transformed = "" if value is None else str(value) if webflow_active and mapping.get("webflow_skip_transformation") else _apply_transformation(value, mapping.get("transformation"))
			transformed = _apply_logic(transformed, mapping.get("logic"))
			prefix, suffix = mapping.get("prefix"), mapping.get("suffix")
			if webflow_active:
				mode = mapping.get("webflow_prefix_suffix") or "Keep"
				if mode == "Override":
					prefix, suffix = mapping.get("webflow_prefix"), mapping.get("webflow_suffix")
				elif mode == "None":
					prefix = suffix = None
			_set_mapped_value(field_values, mapping, value, _apply_prefix_suffix(transformed, prefix, suffix))
		from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint

		mapping_snapshot = json.loads(frappe.as_json(mappings))
		provenance = {"mapping_snapshot": mapping_snapshot, "mapping_hash": fingerprint(mapping_snapshot),
			"values_hash": fingerprint(field_values), "template": {"doctype": template.doctype, "name": template.name}}
		filled_pdf = _fill_pdf_form_fields(pdf_template, field_values, warnings=warnings, provenance=provenance)
		if not filled_pdf:
			return {"success": False, "message": _("Failed to fill LED Sheet PDF form fields"), "warnings": warnings}
		filename = f"Spec_Submittal_{configured_sheet_name}_{nowdate()}.pdf"
		file_doc = _save_file_ignore_permissions(filename, filled_pdf, "ilL-Configured-LED-Sheet", configured_sheet_name, is_private=is_private)
		if not (frappe.flags.get("ill_product_download") or frappe.flags.get("ill_packet_job")):
			configured.spec_submittal = file_doc.file_url
			configured.save(ignore_permissions=True)
		return {"success": True, "file_url": file_doc.file_url, "provenance": provenance, "message": _("Spec submittal generated successfully"), "warnings": warnings}
	except Exception as exc:
		_debug(f"generate_filled_sheet_submittal: EXCEPTION – {type(exc).__name__}: {exc}", warnings)
		return {"success": False, "message": str(exc), "warnings": warnings}


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
	webflow_product: Any = None,
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
		webflow_product: The Webflow product linked to the tape/neon template (if applicable)
		warnings: Optional list that debug messages are appended to

	Returns:
		The value from the source field, or None if not found
	"""
	if _commercial_source_blocked(source_doctype, source_field):
		return None
	try:
		if source_doctype == "ilL-Webflow-Product" and webflow_product:
			val = getattr(webflow_product, source_field, None)
			_debug(
				f"_get_neon_source_value: {source_doctype}.{source_field} → {val!r} "
				f"(doc={webflow_product.name})",
				warnings,
			)
			return val

		if source_doctype == "ilL-Child-Tape-Neon-Segment" and configured_tape_neon:
			segments = getattr(configured_tape_neon, "segments", None)
			if segments:
				first_seg = next(
					(s for s in segments if (s.segment_index or 0) == 1),
					segments[0],
				)
				val = getattr(first_seg, source_field, None)
				_debug(
					f"_get_neon_source_value: {source_doctype}.{source_field} → {val!r} "
					f"(segment_index={first_seg.segment_index})",
					warnings,
				)
				return val

		if source_doctype == "ilL-Configured-Tape-Neon" and configured_tape_neon:
			val = getattr(configured_tape_neon, source_field, None)
			# For neon products, several user-facing fields (start/end feed
			# direction, lead/cable lengths, ip_rating, end_type) live on the
			# first segment row rather than the parent doc.  When the parent
			# doesn't expose the field directly, fall back to segment #1 so
			# existing PDF mappings keep working without per-template changes.
			if val in (None, "") and getattr(configured_tape_neon, "segments", None):
				first_seg = None
				for seg in configured_tape_neon.segments:
					if (seg.segment_index or 0) == 1:
						first_seg = seg
						break
				if first_seg is None:
					first_seg = configured_tape_neon.segments[0]
				seg_val = getattr(first_seg, source_field, None)
				if seg_val not in (None, ""):
					val = seg_val
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
			from illumenate_lighting.illumenate_lighting.api.engineering_sources import resolve
			handled, value = resolve(configured_tape_neon, source_doctype, source_field)
			if handled:
				return value
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
			from illumenate_lighting.illumenate_lighting.api.engineering_sources import resolve
			handled, value = resolve(configured_tape_neon, source_doctype, source_field)
			if handled:
				return value
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
			f"webflow_product={'yes' if webflow_product else 'NO'}, "
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
	base_fields = ["required_value", "pdf_field_name", "source_doctype", "source_field", "transformation", "logic", "prefix", "suffix"]
	webflow_fields = ["webflow_field", "webflow_skip_transformation", "webflow_prefix_suffix", "webflow_prefix", "webflow_suffix"]
	try:
		return frappe.get_all(
			"ilL-Neon-Submittal-Mapping",
			filters={"tape_neon_template": tape_neon_template_name},
			fields=base_fields + webflow_fields,
		)
	except Exception as e:
		# webflow columns may not exist yet if migration is pending;
		# log the error so it's not silently masked, then fall back.
		frappe.log_error(
			title="Neon Submittal: webflow fields query failed, falling back",
			message=f"Error querying webflow fields for {tape_neon_template_name}: {e}",
		)
		return frappe.get_all(
			"ilL-Neon-Submittal-Mapping",
			filters={"tape_neon_template": tape_neon_template_name},
			fields=base_fields,
		)


def generate_filled_neon_submittal(configured_tape_neon_name: str, warnings: list | None = None, webflow_overrides: dict | None = None, schedule_line: str | None = None, *, _configured_doc=None, _schedule_context=None) -> dict:
	"""
	Generate a filled spec submittal PDF for a configured tape/neon product.

	Uses the tape/neon template's spec_submittal_template and field mappings
	to create a filled PDF.

	.. note::
		This is an internal helper and is intentionally **not** whitelisted.
		Callers that expose it over HTTP must enforce their own access
		control and are responsible for publishing the file.

	Args:
		configured_tape_neon_name: Name of the ilL-Configured-Tape-Neon
		warnings: Optional list that debug/warning messages are appended to
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
			- warnings: list of warnings raised during generation
	"""
	# Handle parameters that may arrive as JSON strings from the API
	if isinstance(warnings, str):
		try:
			warnings = json.loads(warnings)
		except (json.JSONDecodeError, TypeError):
			warnings = None
	if warnings is None:
		warnings = []
	if isinstance(webflow_overrides, str):
		try:
			webflow_overrides = json.loads(webflow_overrides)
		except (json.JSONDecodeError, TypeError):
			webflow_overrides = None

	try:
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_save_file_ignore_permissions,
		)

		_debug(f"generate_filled_neon_submittal: START for CTN={configured_tape_neon_name}", warnings)

		# Get the configured tape/neon
		ctn = _configured_doc if _configured_doc is not None else frappe.get_doc("ilL-Configured-Tape-Neon", configured_tape_neon_name)

		if not ctn.tape_neon_template:
			msg = "Configured tape/neon has no tape_neon_template"
			_debug(f"generate_filled_neon_submittal: FAIL – {msg}", warnings)
			return {"success": False, "message": _(msg), "warnings": warnings}

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
			return {"success": False, "message": _(msg), "warnings": warnings}

		_debug(f"generate_filled_neon_submittal: using pdf_template={pdf_template!r}", warnings)

		# Get field mappings
		mappings = _gather_neon_field_mappings(ctn.tape_neon_template)

		_debug(f"generate_filled_neon_submittal: found {len(mappings)} field mappings", warnings)

		if not mappings:
			msg = f"No field mappings defined for tape/neon template '{ctn.tape_neon_template}'"
			_debug(f"generate_filled_neon_submittal: FAIL – {msg}", warnings)
			return {"success": False, "message": _(msg), "warnings": warnings}

		schedule, project, schedule_line = _schedule_context or _explicit_schedule_context("configured_tape_neon", configured_tape_neon_name, schedule_line)

		# Get the Webflow product linked to this tape/neon template (if any)
		webflow_product = _get_linked_webflow_product(
			"tape_neon_template", ctn.tape_neon_template, warnings
		)

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
			webflow_active = webflow_key and webflow_overrides and webflow_key in webflow_overrides
			if webflow_active:
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
					webflow_product=webflow_product,
					warnings=warnings,
				)
			# Skip the transformation when a Webflow value is active and the
			# mapping opts out (the Webflow value is already in its final format).
			if webflow_active and mapping.get("webflow_skip_transformation"):
				transformed_value = "" if value is None else str(value)
			else:
				transformed_value = _apply_transformation(value, mapping.get("transformation"))

			transformed_value = _apply_logic(transformed_value, mapping.get("logic"))

			# Determine prefix/suffix based on webflow_prefix_suffix setting
			if webflow_active:
				ps_mode = mapping.get("webflow_prefix_suffix") or "Keep"
				if ps_mode == "Override":
					prefix = mapping.get("webflow_prefix")
					suffix = mapping.get("webflow_suffix")
				elif ps_mode == "None":
					prefix = None
					suffix = None
				else:  # Keep or blank
					prefix = mapping.get("prefix")
					suffix = mapping.get("suffix")
			else:
				prefix = mapping.get("prefix")
				suffix = mapping.get("suffix")

			transformed_value = _apply_prefix_suffix(
				transformed_value, prefix, suffix
			)
			_set_mapped_value(field_values, mapping, value, transformed_value)
			_debug(
				f"  mapping[{pdf_field}]: {src_dt}.{src_fld} "
				f"raw={value!r} → final={transformed_value!r}"
				+ (f" (transform={mapping.get('transformation')})" if mapping.get("transformation") else "")
				+ (f" (logic={mapping.get('logic')})" if mapping.get("logic") else "")
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
		from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint

		mapping_snapshot = json.loads(frappe.as_json(mappings))
		provenance = {"mapping_snapshot": mapping_snapshot, "mapping_hash": fingerprint(mapping_snapshot),
			"values_hash": fingerprint(field_values), "template": {"doctype": template.doctype, "name": template.name}}
		filled_pdf = _fill_pdf_form_fields(pdf_template, field_values, warnings=warnings, provenance=provenance)

		if not filled_pdf:
			msg = f"_fill_pdf_form_fields returned None/empty for template={pdf_template!r}"
			_debug(f"generate_filled_neon_submittal: FAIL – {msg}", warnings)
			return {"success": False, "message": _("Failed to fill PDF form fields"), "warnings": warnings}

		_debug(f"generate_filled_neon_submittal: filled PDF size = {len(filled_pdf)} bytes", warnings)

		# Save the filled PDF – use ignore_permissions to avoid switching
		# the session user (which corrupts the Frappe session for portal users).
		filename = f"Spec_Submittal_{configured_tape_neon_name}_{nowdate()}.pdf"
		file_doc = _save_file_ignore_permissions(
			filename, filled_pdf, "ilL-Configured-Tape-Neon", configured_tape_neon_name,
			is_private=1,
		)

		# Update the configured tape/neon with the submittal link
		if not (frappe.flags.get("ill_product_download") or frappe.flags.get("ill_packet_job")):
			ctn.spec_submittal = file_doc.file_url
			ctn.save(ignore_permissions=True)

		_debug(f"generate_filled_neon_submittal: SUCCESS – file_url={file_doc.file_url}", warnings)

		return {
			"success": True,
			"file_url": file_doc.file_url,
			"provenance": provenance,
			"message": _("Spec submittal generated successfully"),
			"warnings": warnings,
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
			"warnings": warnings,
		}


# ═══════════════════════════════════════════════════════════════════════
# DRIVER / CONTROLLER SUBMITTAL SUPPORT
# ═══════════════════════════════════════════════════════════════════════
#
# Drivers and controllers have no "configured" record: a configuration is
# just a template + one of its pre-defined variant rows. The submittal is
# therefore generated straight from
#   ilL-<Kind>-Template → ilL-Child-<Kind>-Template-Variant → ilL-Spec-<Kind>
# with the same mapping/transformation/webflow-override semantics used by the
# fixture, neon and LED sheet pipelines.

_VARIANT_SUBMITTAL_KINDS = {
	"Driver": {
		"template_doctype": "ilL-Driver-Template",
		"variant_doctype": "ilL-Child-Driver-Template-Variant",
		"spec_doctype": "ilL-Spec-Driver",
		"spec_field": "driver_spec",
		"mapping_doctype": "ilL-Driver-Submittal-Mapping",
		"mapping_filter_field": "driver_template",
		"product_link_field": "driver_template",
	},
	"Controller": {
		"template_doctype": "ilL-Controller-Template",
		"variant_doctype": "ilL-Child-Controller-Template-Variant",
		"spec_doctype": "ilL-Spec-Controller",
		"spec_field": "controller_spec",
		"mapping_doctype": "ilL-Controller-Submittal-Mapping",
		"mapping_filter_field": "controller_template",
		"product_link_field": "controller_template",
	},
}


def _gather_variant_field_mappings(kind: str, template_name: str) -> list[dict]:
	"""Get all submittal field mappings for a driver/controller template."""
	cfg = _VARIANT_SUBMITTAL_KINDS[kind]
	base_fields = ["required_value", "pdf_field_name", "source_doctype", "source_field", "transformation", "logic", "prefix", "suffix"]
	webflow_fields = ["webflow_field", "webflow_skip_transformation", "webflow_prefix_suffix", "webflow_prefix", "webflow_suffix"]
	filters = {cfg["mapping_filter_field"]: template_name}
	try:
		return frappe.get_all(cfg["mapping_doctype"], filters=filters, fields=base_fields + webflow_fields)
	except Exception as e:
		# The webflow columns may not exist yet if migration is pending.
		frappe.log_error(
			title=f"{kind} Submittal: webflow fields query failed, falling back",
			message=f"Error querying webflow fields for {template_name}: {e}",
		)
		return frappe.get_all(cfg["mapping_doctype"], filters=filters, fields=base_fields)


def _get_variant_source_value(
	kind: str,
	source_doctype: str,
	source_field: str,
	template: Any = None,
	variant: Any = None,
	spec: Any = None,
	webflow_product: Any = None,
	warnings: list | None = None,
) -> Any:
	"""Resolve one mapping row against the driver/controller doctype chain."""
	if _commercial_source_blocked(source_doctype, source_field):
		return None
	cfg = _VARIANT_SUBMITTAL_KINDS[kind]
	lookup = {
		cfg["template_doctype"]: template,
		cfg["variant_doctype"]: variant,
		cfg["spec_doctype"]: spec,
		"ilL-Webflow-Product": webflow_product,
	}
	doc = lookup.get(source_doctype)
	if doc is None:
		_debug(
			f"_get_variant_source_value[{kind}]: NO MATCH for {source_doctype}.{source_field}",
			warnings,
		)
		return None
	try:
		val = doc.get(source_field) if hasattr(doc, "get") else getattr(doc, source_field, None)
		_debug(
			f"_get_variant_source_value[{kind}]: {source_doctype}.{source_field} → {val!r}",
			warnings,
		)
		return val
	except Exception as e:
		_debug(
			f"_get_variant_source_value[{kind}]: EXCEPTION for {source_doctype}.{source_field} – "
			f"{type(e).__name__}: {e}",
			warnings,
		)
		return None


def _get_driver_source_value(
	source_doctype: str,
	source_field: str,
	driver_template: Any = None,
	variant: Any = None,
	driver_spec: Any = None,
	webflow_product: Any = None,
	warnings: list | None = None,
) -> Any:
	"""Get a value from the driver template / variant / spec / product chain."""
	return _get_variant_source_value(
		"Driver", source_doctype, source_field,
		template=driver_template, variant=variant, spec=driver_spec,
		webflow_product=webflow_product, warnings=warnings,
	)


def _get_controller_source_value(
	source_doctype: str,
	source_field: str,
	controller_template: Any = None,
	variant: Any = None,
	controller_spec: Any = None,
	webflow_product: Any = None,
	warnings: list | None = None,
) -> Any:
	"""Get a value from the controller template / variant / spec / product chain."""
	return _get_variant_source_value(
		"Controller", source_doctype, source_field,
		template=controller_template, variant=variant, spec=controller_spec,
		webflow_product=webflow_product, warnings=warnings,
	)


def _resolve_template_variant(template: Any, variant_name: str | None):
	"""Pick the variant row to fill from: the requested row, else the default."""
	rows = getattr(template, "variants", None) or []
	if variant_name:
		for row in rows:
			if row.name == variant_name:
				return row
	active = [r for r in rows if r.is_active]
	if not active:
		return None
	default = [r for r in active if r.is_default]
	return (default or active)[0]


def _generate_filled_variant_submittal(
	kind: str,
	template_name: str,
	variant_name: str | None = None,
	warnings: list | None = None,
	webflow_overrides: dict | None = None,
	is_private: int = 1,
) -> dict:
	"""Shared implementation behind the driver and controller submittal generators."""
	cfg = _VARIANT_SUBMITTAL_KINDS[kind]

	if isinstance(warnings, str):
		try:
			warnings = json.loads(warnings)
		except (json.JSONDecodeError, TypeError):
			warnings = None
	if warnings is None:
		warnings = []
	if isinstance(webflow_overrides, str):
		try:
			webflow_overrides = json.loads(webflow_overrides)
		except (json.JSONDecodeError, TypeError):
			webflow_overrides = None

	try:
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_save_file_ignore_permissions,
		)

		_debug(f"_generate_filled_variant_submittal[{kind}]: START template={template_name}", warnings)

		template = frappe.get_doc(cfg["template_doctype"], template_name)

		pdf_template = template.spec_submittal_template or template.spec_sheet
		if not pdf_template:
			msg = (
				f"{kind} template '{template_name}' has no spec_submittal_template "
				f"AND no spec_sheet attached – cannot generate filled submittal"
			)
			_debug(f"_generate_filled_variant_submittal[{kind}]: FAIL – {msg}", warnings)
			return {"success": False, "message": _(msg), "warnings": warnings}

		mappings = _gather_variant_field_mappings(kind, template_name)
		if not mappings:
			msg = f"No field mappings defined for {kind.lower()} template '{template_name}'"
			_debug(f"_generate_filled_variant_submittal[{kind}]: FAIL – {msg}", warnings)
			return {"success": False, "message": _(msg), "warnings": warnings}

		variant = _resolve_template_variant(template, variant_name)
		if not variant:
			msg = f"{kind} template '{template_name}' has no active variant to generate from"
			_debug(f"_generate_filled_variant_submittal[{kind}]: FAIL – {msg}", warnings)
			return {"success": False, "message": _(msg), "warnings": warnings}

		spec_name = variant.get(cfg["spec_field"])
		spec = frappe.get_doc(cfg["spec_doctype"], spec_name) if spec_name else None

		webflow_product = _get_linked_webflow_product(
			cfg["product_link_field"], template_name, warnings
		)

		field_values = {}
		for mapping in mappings:
			webflow_key = mapping.get("webflow_field")
			webflow_active = bool(webflow_key and webflow_overrides and webflow_key in webflow_overrides)

			if webflow_active:
				value = webflow_overrides[webflow_key]
			else:
				value = _get_variant_source_value(
					kind,
					mapping.get("source_doctype"),
					mapping.get("source_field"),
					template=template,
					variant=variant,
					spec=spec,
					webflow_product=webflow_product,
					warnings=warnings,
				)

			if webflow_active and mapping.get("webflow_skip_transformation"):
				transformed = "" if value is None else str(value)
			else:
				transformed = _apply_transformation(value, mapping.get("transformation"))
			transformed = _apply_logic(transformed, mapping.get("logic"))

			prefix, suffix = mapping.get("prefix"), mapping.get("suffix")
			if webflow_active:
				ps_mode = mapping.get("webflow_prefix_suffix") or "Keep"
				if ps_mode == "Override":
					prefix, suffix = mapping.get("webflow_prefix"), mapping.get("webflow_suffix")
				elif ps_mode == "None":
					prefix = suffix = None

			_set_mapped_value(field_values, mapping, value, _apply_prefix_suffix(transformed, prefix, suffix))

		from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint

		mapping_snapshot = json.loads(frappe.as_json(mappings))
		provenance = {"mapping_snapshot": mapping_snapshot, "mapping_hash": fingerprint(mapping_snapshot),
			"values_hash": fingerprint(field_values), "template": {"doctype": template.doctype, "name": template.name}}
		filled_pdf = _fill_pdf_form_fields(pdf_template, field_values, warnings=warnings, provenance=provenance)
		if not filled_pdf:
			msg = f"_fill_pdf_form_fields returned None/empty for template={pdf_template!r}"
			_debug(f"_generate_filled_variant_submittal[{kind}]: FAIL – {msg}", warnings)
			return {"success": False, "message": _("Failed to fill PDF form fields"), "warnings": warnings}

		suffix_code = (variant.get("variant_code") or variant.name or "").replace("/", "-")
		filename = f"Spec_Submittal_{template_name}_{suffix_code}_{nowdate()}.pdf"
		file_doc = _save_file_ignore_permissions(
			filename, filled_pdf, cfg["template_doctype"], template_name, is_private=is_private
		)

		_debug(
			f"_generate_filled_variant_submittal[{kind}]: SUCCESS – file_url={file_doc.file_url}",
			warnings,
		)
		return {
			"success": True,
			"file_url": file_doc.file_url,
			"provenance": provenance,
			"message": _("Spec submittal generated successfully"),
			"warnings": warnings,
		}

	except Exception as e:
		_debug(f"_generate_filled_variant_submittal[{kind}]: EXCEPTION – {type(e).__name__}: {e}", warnings)
		frappe.log_error(
			f"Error generating filled {kind.lower()} submittal: {type(e).__name__}: {e}\n"
			f"{traceback.format_exc()}",
			f"{kind} Spec Submittal Generation Error",
		)
		return {
			"success": False,
			"message": _("Error generating {0} spec submittal: {1}: {2}").format(
				kind.lower(), type(e).__name__, str(e) or "insufficient permissions"
			),
			"warnings": warnings,
		}


def generate_filled_driver_submittal(
	driver_template_name: str,
	variant_name: str | None = None,
	warnings: list | None = None,
	webflow_overrides: dict | None = None,
	is_private: int = 1,
) -> dict:
	"""
	Generate a filled spec submittal PDF for a configured driver.

	.. note::
		This is an internal helper and is intentionally **not** whitelisted.
		Callers that expose it over HTTP must enforce their own access control.

	Args:
		driver_template_name: Name of the ilL-Driver-Template
		variant_name: Child row name of the ilL-Child-Driver-Template-Variant to
			fill from. Falls back to the template's default/first active variant.
		warnings: Optional list that debug/warning messages are appended to
		webflow_overrides: Optional dict of webflow parameter values that take
			priority over the mapped source field (e.g. {"project_name": "..."})
		is_private: Whether the generated File should be private

	Returns:
		dict: {success, file_url, message, warnings}
	"""
	return _generate_filled_variant_submittal(
		"Driver", driver_template_name, variant_name, warnings, webflow_overrides, is_private
	)


def generate_filled_controller_submittal(
	controller_template_name: str,
	variant_name: str | None = None,
	warnings: list | None = None,
	webflow_overrides: dict | None = None,
	is_private: int = 1,
) -> dict:
	"""
	Generate a filled spec submittal PDF for a configured controller.

	.. note::
		This is an internal helper and is intentionally **not** whitelisted.
		Callers that expose it over HTTP must enforce their own access control.

	Args:
		controller_template_name: Name of the ilL-Controller-Template
		variant_name: Child row name of the ilL-Child-Controller-Template-Variant
			to fill from. Falls back to the default/first active variant.
		warnings: Optional list that debug/warning messages are appended to
		webflow_overrides: Optional dict of webflow parameter values that take
			priority over the mapped source field
		is_private: Whether the generated File should be private

	Returns:
		dict: {success, file_url, message, warnings}
	"""
	return _generate_filled_variant_submittal(
		"Controller", controller_template_name, variant_name, warnings, webflow_overrides, is_private
	)
