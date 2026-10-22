"""Private packet preparation with source snapshots and a staff-only issue log."""

import hashlib
import io
import json
from urllib.parse import urlsplit

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import parse_bool
from illumenate_lighting.illumenate_lighting.portal.packet_manifest import assemble_manifest
from illumenate_lighting.illumenate_lighting.portal.packet_pages import contents_html


def _part_number(line):
	"""The part number a customer recognizes; engine-built linear fixtures are named by config hash."""
	if line.manufacturer_type == "OTHER":
		return line.get("fixture_model_number")
	if line.manufacturer_type == "ACCESSORY":
		from illumenate_lighting.illumenate_lighting.portal.driver_configuration import driver_configuration

		driver = driver_configuration(line)
		return (driver or {}).get("part_number") or line.get("accessory_item")
	if line.get("configured_group"):
		return line.get("group_part_number") or frappe.db.get_value(
			"ilL-Configured-Group", line.configured_group, "template"
		)
	for field, doctype, column in (
		("configured_fixture", "ilL-Configured-Fixture", "display_part_number"),
		("configured_tape_neon", "ilL-Configured-Tape-Neon", "part_number"),
		("configured_led_sheet", "ilL-Configured-LED-Sheet", "part_number"),
	):
		if line.get(field):
			return frappe.db.get_value(doctype, line.get(field), column) or line.get(field)
	if line.get("kit_template"):
		return line.get("ill_item_code") or line.kit_template
	return None


# A configured power supply or controller line: how its template is found and its submittal filled.
_VARIANT_KINDS = {
	"ilL-Driver-Template": (
		"power supply",
		"_driver_document_source",
		"generate_filled_driver_line_submittal",
	),
	"ilL-Controller-Template": (
		"controller",
		"_controller_document_source",
		"generate_filled_controller_line_submittal",
	),
}


def _driver_submittal(line, entry, warnings, template_doctype="ilL-Driver-Template"):
	"""Use the exact driver or controller template's submittal or spec sheet before Item literature."""
	from illumenate_lighting.illumenate_lighting.api import spec_submittal as pdf

	noun, resolve, render = _VARIANT_KINDS[template_doctype]
	label = line.line_id or f"Row {line.idx}"
	try:
		source = getattr(pdf, resolve)(line)
	except ValueError as error:
		warning = f"Line {label}: {error}"
		entry["warnings"] = [warning]
		warnings.append(warning)
		return False
	if not source:
		return False
	template = source["template"]
	entry["build"] = {"doctype": template_doctype, "name": template}
	line_warnings = []
	try:
		result = getattr(pdf, render)(template, warnings=line_warnings, schedule_line=line.name)
	except (ValueError, frappe.ValidationError) as error:
		result = {"success": False, "message": str(error)}
	warnings.extend(line_warnings)
	notes = [note for note in line_warnings if not note.startswith("[DEBUG]")]
	if not result.get("success"):
		_, _, spec_sheet = _template_spec_sheet(entry["build"])
		if spec_sheet:
			reason = "; ".join(
				dict.fromkeys([result.get("message") or "Submittal generation failed", *notes])
			)
			warning = f"Line {label}: used the {template} spec sheet because the {noun} submittal could not be generated ({reason})"
			entry.update(
				spec_document_url=spec_sheet,
				has_submittal=True,
				source_kind="template_spec_sheet",
				filled_required=False,
				provenance={
					"template_type": template_doctype,
					"template": template,
					"source_url": spec_sheet,
				},
				warnings=[warning],
			)
			warnings.append(warning)
			return True
		warning = (
			f"Line {label}: {noun} submittal unavailable ({result.get('message')}); using its Item literature"
		)
		entry["warnings"] = [warning]
		warnings.append(warning)
		return False
	entry.update(
		spec_document_url=result.get("file_url"),
		has_submittal=True,
		source_kind="filled_submittal",
		provenance=result.get("provenance"),
		warnings=[f"Line {label}: {note}" for note in dict.fromkeys(notes)],
	)
	return True


# Where each configured build's template, and so its spec sheet, lives.
_TEMPLATE_FIELDS = {
	"ilL-Configured-Fixture": ("fixture_template", "ilL-Fixture-Template"),
	"ilL-Configured-Tape-Neon": ("tape_neon_template", "ilL-Tape-Neon-Template"),
	"ilL-Configured-LED-Sheet": ("sheet_template", "ilL-LED-Sheet-Template"),
}
_GROUP_TEMPLATES = {
	"Linear Fixture": "ilL-Fixture-Template",
	"LED Tape": "ilL-Tape-Neon-Template",
	"COB Tape": "ilL-Tape-Neon-Template",
	"LED Neon": "ilL-Tape-Neon-Template",
	"LED Sheet": "ilL-LED-Sheet-Template",
}


def _template_spec_sheet(build):
	"""The (template doctype, template, spec sheet URL) backing a configured build."""
	doctype, name = build["doctype"], build["name"]
	if doctype in ("ilL-Extrusion-Kit-Template", "ilL-Driver-Template", "ilL-Controller-Template"):
		template_doctype, template = doctype, name
	elif doctype == "ilL-Configured-Group":
		group = frappe.db.get_value(doctype, name, ["family", "template"], as_dict=True) or {}
		template_doctype, template = _GROUP_TEMPLATES.get(group.get("family")), group.get("template")
	else:
		field, template_doctype = _TEMPLATE_FIELDS[doctype]
		template = frappe.db.get_value(doctype, name, field)
	if not (template_doctype and template):
		return template_doctype, template, None
	return template_doctype, template, frappe.db.get_value(template_doctype, template, "spec_sheet")


def gather(schedule, warnings, pinned=None):
	from illumenate_lighting.illumenate_lighting.api import spec_submittal as pdf
	from illumenate_lighting.illumenate_lighting.portal.build_documents import generate_group

	families = (
		("configured_group", "ilL-Configured-Group", generate_group),
		("configured_fixture", "ilL-Configured-Fixture", pdf.generate_filled_submittal),
		("configured_tape_neon", "ilL-Configured-Tape-Neon", pdf.generate_filled_neon_submittal),
		("configured_led_sheet", "ilL-Configured-LED-Sheet", pdf.generate_filled_sheet_submittal),
		# A configured kit's build lives on the line itself; its template supplies the submittal.
		("kit_template", "ilL-Extrusion-Kit-Template", pdf.generate_filled_kit_submittal),
	)
	lines = []
	for line in schedule.lines:
		entry = {
			"line_key": line.get("line_key") or line.name,
			"schedule_line": line.name,
			"idx": line.idx,
			"line_id": line.line_id,
			"qty": line.qty,
			"location": line.location,
			"notes": line.notes,
			"manufacturer_type": line.manufacturer_type,
			"part_number": _part_number(line),
			"spec_document_url": None,
			"has_submittal": False,
			"required": True,
		}
		prior = (pinned or {}).get(entry["line_key"])
		if prior and prior.get("source_file"):
			entry.update(
				spec_document_url=frappe.db.get_value("File", prior["source_file"], "file_url"),
				source_kind=prior.get("source_kind"),
				build=prior.get("build"),
				provenance=prior.get("provenance"),
				expected_sha256=prior.get("sha256"),
				has_submittal=prior.get("source_kind") in ("filled_submittal", "template_spec_sheet"),
				warnings=prior.get("warnings"),
			)
		elif line.manufacturer_type == "ILLUMENATE":
			entry["render_error"] = "The line has no configured build; configure it before exporting"
			for field, doctype, renderer in families:
				if line.get(field):
					entry["build"] = {"doctype": doctype, "name": line.get(field)}
					# Keep this line's diagnostics separate so its failure reason reaches the packet error.
					line_warnings = []
					try:
						result = renderer(line.get(field), warnings=line_warnings, schedule_line=line.name)
					except (ValueError, frappe.ValidationError) as error:
						result = {"success": False, "message": str(error)}
					warnings.extend(line_warnings)
					notes = [note for note in line_warnings if not note.startswith("[DEBUG]")]
					label = line.line_id or f"Row {line.idx}"
					entry.pop("render_error")
					if result.get("success"):
						entry.update(
							spec_document_url=result.get("file_url"),
							has_submittal=True,
							source_kind="filled_submittal",
							provenance=result.get("provenance"),
							warnings=[f"Line {label}: {note}" for note in dict.fromkeys(notes)],
						)
						break
					# A template without a usable spec submittal falls back to its spec sheet, and a
					# template with neither is left out with a warning instead of stopping the packet.
					failure = result.get("message") or "The spec submittal could not be generated"
					reason = "; ".join(dict.fromkeys([failure, *notes]))
					template_doctype, template, spec_sheet = _template_spec_sheet(entry["build"])
					if spec_sheet:
						warning = f"Line {label}: used the {template} spec sheet because the spec submittal could not be generated ({reason})"
						entry.update(
							spec_document_url=spec_sheet,
							source_kind="template_spec_sheet",
							filled_required=False,
							provenance={
								"template_type": template_doctype,
								"template": template,
								"source_url": spec_sheet,
							},
						)
					else:
						warning = f"Line {label}: left out because {template or 'its template'} has no spec submittal or spec sheet ({reason})"
						entry.update(
							required=False,
							exclusion_reason="No spec submittal or spec sheet available",
						)
					entry["warnings"] = [warning]
					warnings.append(warning)
					break
		elif line.manufacturer_type == "OTHER":
			entry.update(spec_document_url=line.spec_sheet, source_kind="uploaded_literature")
		elif line.manufacturer_type == "ACCESSORY" and (
			_driver_submittal(line, entry, warnings)
			or _driver_submittal(line, entry, warnings, "ilL-Controller-Template")
		):
			# A power supply or controller gets its template's filled submittal or spec sheet.
			pass
		elif line.manufacturer_type == "ACCESSORY":
			registry = frappe.db.get_value(
				"ilL-Item-Literature",
				{"item": line.accessory_item, "active": 1},
				["document", "no_document_required", "exclusion_reason", "sha256"],
				as_dict=True,
			)
			if registry:
				entry.update(
					required=not registry.no_document_required,
					exclusion_reason=registry.exclusion_reason,
					spec_document_url=frappe.db.get_value("File", registry.document, "file_url")
					if registry.document
					else None,
					expected_sha256=registry.sha256,
					source_kind="approved_item_literature",
				)
		from illumenate_lighting.illumenate_lighting.portal.line_documents import active

		attachments = active(schedule.name, line)
		for document in attachments:
			url = frappe.db.get_value("File", document.file, "file_url")
			if not prior and document.is_primary and line.manufacturer_type in ("OTHER", "ACCESSORY"):
				entry.update(
					spec_document_url=url,
					expected_sha256=document.sha256,
					source_kind="selected_line_document",
					required=True,
				)
		lines.append(entry)
		for document in attachments:
			url = frappe.db.get_value("File", document.file, "file_url")
			if url == entry.get("spec_document_url") or (
				document.is_primary and prior and prior.get("source_kind") == "selected_line_document"
			):
				continue
			lines.append(
				{
					**entry,
					"line_key": f"{entry['line_key']}:{document.name}",
					"spec_document_url": url,
					"source_kind": "selected_line_document",
					"provenance": {
						"line_document": document.name,
						"source_file": document.file,
						"sha256": document.sha256,
					},
					"expected_sha256": document.sha256,
					"filled_required": False,
					"required": True,
					"warnings": None,
				}
			)
	for entry in lines:
		prior = (pinned or {}).get(entry["line_key"])
		if prior and prior.get("source_file"):
			entry.update(
				spec_document_url=frappe.db.get_value("File", prior["source_file"], "file_url"),
				expected_sha256=prior.get("sha256"),
			)
	return lines


def full_literature(schedule, lines, pinned, warnings):
	"""FULL adds each configured build's template spec sheet after its submittal, never an arbitrary
	attachment. A template without a spec sheet is noted for staff instead of failing the line."""
	lines = list(lines)
	for line in schedule.lines:
		entry = next(entry for entry in lines if entry.get("schedule_line") == line.name)
		literature = {
			**entry,
			"line_key": f"{line.name}:literature",
			"source_kind": "approved_literature",
			"filled_required": False,
			"has_submittal": True,
			"warnings": None,
		}
		prior = pinned.get(literature["line_key"])
		if prior and prior.get("source_file"):
			lines.append(
				{
					**literature,
					"spec_document_url": frappe.db.get_value("File", prior["source_file"], "file_url"),
					"expected_sha256": prior["sha256"],
					"provenance": prior.get("provenance"),
				}
			)
			continue
		build = entry.get("build")
		# A line that already fell back to its spec sheet would only repeat it.
		if not build or entry.get("source_kind") == "template_spec_sheet":
			continue
		template_doctype, template, url = _template_spec_sheet(build)
		if not url:
			warning = f"Line {line.line_id or f'Row {line.idx}'}: {template or 'its template'} has no spec sheet to add to the full submittal"
			entry["warnings"] = [*(entry.get("warnings") or []), warning]
			warnings.append(warning)
			continue
		lines.append(
			{
				**literature,
				"spec_document_url": url,
				"expected_sha256": None,
				"provenance": {"template_type": template_doctype, "template": template, "source_url": url},
			}
		)
	return lines


def _issue_log(manifest, errors, notes=()):
	"""Everything that went wrong or was worked around, for staff in Desk only."""
	warnings = [warning for entry in manifest for warning in entry.get("warnings") or []]
	sections = []
	for title, items in (("Errors", [*errors, *notes]), ("Warnings", warnings)):
		items = [item for item in dict.fromkeys(items) if "[DEBUG]" not in item]
		if items:
			sections.append(f"{title} ({len(items)}):\n" + "\n".join(f"- {item}" for item in items))
	return "\n\n".join(sections), len(errors) + len(notes)


def generate(schedule_name, export_type="SPEC_SUBMITTAL", include_cover=True, *, job_name=None):
	"""Both submittals always produce a packet: a document that cannot be included is left out and
	every reason goes to the job's staff-only issue log. The full submittal also adds template spec sheets."""
	from pypdf import PdfReader

	from illumenate_lighting.illumenate_lighting.api import exports
	from illumenate_lighting.illumenate_lighting.api import spec_submittal as pdf
	from illumenate_lighting.illumenate_lighting.portal.packet_jobs import (
		InterruptedPacket,
		checkpoint,
		lock_running,
	)
	from illumenate_lighting.illumenate_lighting.portal.quotes import _snapshot

	include_cover = parse_bool(include_cover, default=True)
	if export_type not in ("SPEC_SUBMITTAL", "SPEC_SUBMITTAL_FULL"):
		frappe.throw("Choose a supported packet type")
	allowed, error = exports._check_schedule_access(schedule_name)
	if not allowed:
		frappe.throw(error or "Access denied", frappe.PermissionError)
	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)
	revision = str(schedule.modified)
	if not job_name:
		job_name = exports._create_export_job(schedule_name, export_type)
		exports._update_export_job_status(job_name, "RUNNING")
	job = frappe.get_doc("ilL-Export-Job", job_name)
	pinned = {}
	if job.get("retry_of"):
		prior = frappe.get_doc("ilL-Export-Job", job.retry_of)
		if prior.source_revision == revision:
			pinned = {
				entry["line_key"]: entry
				for entry in json.loads(prior.manifest_json or "[]")
				if entry["status"] == "included"
			}
	previous = frappe.flags.get("ill_packet_job")
	warnings = []
	notes = []
	try:
		frappe.flags.ill_packet_job = job_name
		lock_running(job_name)
		frappe.db.commit()
		lines = gather(schedule, warnings, pinned)
		checkpoint(job_name, 60, "Validating and pinning source documents")
		if export_type == "SPEC_SUBMITTAL_FULL":
			lines = full_literature(schedule, lines, pinned, warnings)
		cover = (
			pdf._generate_cover_page(schedule_name, schedule.ill_project, lines) if include_cover else None
		)
		if include_cover and not cover:
			notes.append("The cover page could not be generated; the packet was issued without it")
		cover_pages = len(PdfReader(io.BytesIO(cover)).pages) if cover else 0

		def load_source(url):
			# An Attach field may hold this site's full link to the file (https://site/files/...).
			parts = urlsplit(url)
			path = parts.path if parts.scheme in ("http", "https") else url
			if not path.startswith(("/files/", "/private/files/")) or ".." in path.split("/"):
				raise ValueError("Source must be a local registered file")
			file = pdf._get_file_doc_by_url(url)
			if not file:
				raise ValueError("Source file is unavailable")
			# New generated files already belong to this job. Other private sources must be readable now.
			if file.is_private and not (
				file.attached_to_doctype == "ilL-Export-Job" and file.attached_to_name == job_name
			):
				if not file.is_downloadable():
					raise ValueError("Source file access was revoked")
			content = file.get_content()
			# Pin bytes independently of source replacement or template edits.
			pinned = exports._save_file_ignore_permissions(
				file.file_name, content, "ilL-Export-Job", job_name
			)
			pins[url] = pinned.name
			return content, file.file_name

		pins = {}
		manifest, parts, errors = assemble_manifest(lines, load_source, cover_pages=cover_pages)
		for entry in manifest:
			entry["source_file"] = pins.get(entry.get("source_url"))
		frappe.db.set_value(
			"ilL-Export-Job",
			job_name,
			{
				"manifest_json": json.dumps(manifest, sort_keys=True),
				"source_revision": revision,
				"snapshot_json": frappe.as_json(_snapshot(schedule)),
				"manifest_schema_version": 1,
			},
		)
		checkpoint(job_name, 75, "Assembling schedule and page index")
		from frappe.utils.pdf import get_pdf

		schedule_data = exports._get_schedule_data(schedule_name, include_pricing=False)
		project_title = getattr(schedule_data.get("project"), "project_name", None)
		schedule_pdf = get_pdf(
			exports._generate_pdf_content(schedule_data, include_pricing=False, submittal=True)
		)
		schedule_pages = len(PdfReader(io.BytesIO(schedule_pdf)).pages)
		index_pages = 0
		for _attempt in range(4):
			page = cover_pages + schedule_pages + index_pages + 1
			for entry in manifest:
				if entry.get("page_count"):
					entry.update(page_start=page, page_end=page + entry["page_count"] - 1)
					page += entry["page_count"]
			index_pdf = get_pdf(
				contents_html(
					manifest,
					schedule_title=schedule.get("schedule_name"),
					project_title=project_title,
				)
			)
			count = len(PdfReader(io.BytesIO(index_pdf)).pages)
			if count == index_pages:
				break
			index_pages = count
		else:
			raise ValueError("Packet index pagination did not stabilize")
		prefix = ([cover] if cover else []) + [schedule_pdf, index_pdf]
		cover_pages += schedule_pages + index_pages
		for entry in manifest:
			entry["source_file"] = pins.get(entry.get("source_url"))
		frappe.db.set_value(
			"ilL-Export-Job",
			job_name,
			{
				"manifest_json": json.dumps(manifest, sort_keys=True),
				"source_revision": revision,
				"snapshot_json": frappe.as_json(_snapshot(schedule)),
				"manifest_schema_version": 1,
			},
		)
		frappe.db.sql(
			"select name from `tabilL-Project-Fixture-Schedule` where name=%s for update", schedule.name
		)
		if str(frappe.db.get_value(schedule.doctype, schedule.name, "modified")) != revision:
			raise ValueError("Schedule changed during preparation; generate a new packet")
		lock_running(job_name)
		_access, access_error = exports._check_schedule_access(schedule_name)
		if not _access:
			raise PermissionError(access_error or "Access revoked")
		merged = pdf._merge_pdfs(prefix + parts)
		if not merged or len(PdfReader(io.BytesIO(merged)).pages) != cover_pages + sum(
			e.get("page_count", 0) for e in manifest
		):
			raise ValueError("Merged packet page count does not match its manifest")
		# INCOMPLETE keeps the job in staff queues; the customer's copy reads like any other packet.
		result_status = "INCOMPLETE" if errors or notes else "COMPLETE"
		issue_log, issue_count = _issue_log(manifest, errors, notes)
		file = exports._save_file_ignore_permissions(
			f"Spec_Submittal_{job_name}.pdf", merged, "ilL-Export-Job", job_name
		)
		frappe.db.set_value("ilL-Export-Job", job_name, "output_sha256", hashlib.sha256(merged).hexdigest())
		frappe.db.set_value(
			"ilL-Export-Job",
			job_name,
			{
				"progress": 100,
				"progress_message": "Ready",
				"issue_log": issue_log,
				"issue_count": issue_count,
			},
			update_modified=False,
		)
		exports._update_export_job_status(job_name, result_status, output_file=file.file_url)
		return {
			"success": True,
			"export_job": job_name,
			"file_url": file.file_url,
			"manifest": manifest,
			"warnings": warnings + errors + notes,
			"status": result_status,
			"message": "Spec submittal packet generated",
		}
	except InterruptedPacket:
		raise
	except Exception as error:
		lock_running(job_name)
		frappe.log_error(frappe.get_traceback(), "Packet generation failed")
		issue_log, issue_count = _issue_log([], [str(error), *warnings])
		frappe.db.set_value("ilL-Export-Job", job_name, {"issue_log": issue_log, "issue_count": issue_count})
		exports._update_export_job_status(job_name, "FAILED", error_log=str(error))
		return {"success": False, "export_job": job_name, "message": str(error), "warnings": warnings}
	finally:
		frappe.flags.ill_packet_job = previous
