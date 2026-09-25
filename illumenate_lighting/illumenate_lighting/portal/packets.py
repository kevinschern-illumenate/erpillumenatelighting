"""Private packet preparation with source snapshots and a fail-closed manifest."""

import hashlib
import html
import io
import json

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import parse_bool
from illumenate_lighting.illumenate_lighting.portal.packet_manifest import assemble_manifest


def gather(schedule, warnings, pinned=None):
	from illumenate_lighting.illumenate_lighting.api import spec_submittal as pdf
	from illumenate_lighting.illumenate_lighting.portal.build_documents import generate_group

	families = (
		("configured_group", "ilL-Configured-Group", generate_group),
		("configured_fixture", "ilL-Configured-Fixture", pdf.generate_filled_submittal),
		("configured_tape_neon", "ilL-Configured-Tape-Neon", pdf.generate_filled_neon_submittal),
		("configured_led_sheet", "ilL-Configured-LED-Sheet", pdf.generate_filled_sheet_submittal),
	)
	lines = []
	for line in schedule.lines:
		entry = {
			"line_key": line.get("line_key") or line.name,
			"schedule_line": line.name,
			"line_id": line.line_id,
			"qty": line.qty,
			"location": line.location,
			"notes": line.notes,
			"manufacturer_type": line.manufacturer_type,
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
				has_submittal=prior.get("source_kind") == "filled_submittal",
			)
		elif line.manufacturer_type == "ILLUMENATE":
			for field, doctype, renderer in families:
				if line.get(field):
					entry["build"] = {"doctype": doctype, "name": line.get(field)}
					try:
						result = renderer(line.get(field), warnings=warnings, schedule_line=line.name)
					except (ValueError, frappe.ValidationError) as error:
						result = {"success": False, "message": str(error)}
					if result.get("success"):
						entry.update(
							spec_document_url=result.get("file_url"),
							has_submittal=True,
							source_kind="filled_submittal",
							provenance=result.get("provenance"),
						)
					else:
						warnings.append(result.get("message") or f"Could not render line {line.line_id}")
					break
		elif line.manufacturer_type == "OTHER":
			entry.update(spec_document_url=line.spec_sheet, source_kind="uploaded_literature")
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


def _incomplete_watermark(content, get_pdf):
	from pypdf import PdfReader, PdfWriter, Transformation

	overlay = PdfReader(
		io.BytesIO(
			get_pdf(
				'<html><body><p style="font:bold 18pt Arial;color:#b00020;text-align:center">INCOMPLETE DRAFT - SEE OMISSIONS IN INDEX</p></body></html>'
			)
		)
	).pages[0]
	writer = PdfWriter()
	for page in PdfReader(io.BytesIO(content)).pages:
		page.merge_transformed_page(
			overlay,
			Transformation().scale(
				float(page.mediabox.width) / float(overlay.mediabox.width),
				float(page.mediabox.height) / float(overlay.mediabox.height),
			),
		)
		writer.add_page(page)
	stream = io.BytesIO()
	writer.write(stream)
	return stream.getvalue()


def generate(
	schedule_name, export_type="SPEC_SUBMITTAL", include_cover=True, *, job_name=None, allow_partial=False
):
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
	allow_partial = parse_bool(allow_partial)
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
	try:
		frappe.flags.ill_packet_job = job_name
		lock_running(job_name)
		frappe.db.commit()
		lines = gather(schedule, warnings, pinned)
		checkpoint(job_name, 60, "Validating and pinning source documents")
		# FULL additionally includes explicitly selected template literature, never an arbitrary attachment.
		if export_type == "SPEC_SUBMITTAL_FULL":
			for line in schedule.lines:
				entry = next(entry for entry in lines if entry.get("schedule_line") == line.name)
				prior_literature = pinned.get(f"{line.name}:literature")
				if prior_literature and prior_literature.get("source_file"):
					lines.append(
						{
							**entry,
							"line_key": f"{line.name}:literature",
							"spec_document_url": frappe.db.get_value(
								"File", prior_literature["source_file"], "file_url"
							),
							"source_kind": "approved_literature",
							"expected_sha256": prior_literature["sha256"],
							"filled_required": False,
							"provenance": prior_literature.get("provenance"),
						}
					)
					continue
				build = entry.get("build")
				if not build:
					continue
				configured = frappe.get_doc(build["doctype"], build["name"])
				if build["doctype"] == "ilL-Configured-Group":
					field = {
						"Linear Fixture": "fixture_template",
						"LED Tape": "tape_neon_template",
						"LED Neon": "tape_neon_template",
						"LED Sheet": "sheet_template",
					}[configured.family]
					configured.set(field, configured.template)
				for field, doctype in (
					("fixture_template", "ilL-Fixture-Template"),
					("tape_neon_template", "ilL-Tape-Neon-Template"),
					("sheet_template", "ilL-LED-Sheet-Template"),
				):
					if configured.get(field):
						url = frappe.db.get_value(doctype, configured.get(field), "spec_sheet")
						if url:
							lines.append(
								{
									**entry,
									"line_key": f"{line.name}:literature",
									"spec_document_url": url,
									"source_kind": "approved_literature",
									"provenance": {
										"template_type": doctype,
										"template": configured.get(field),
										"source_url": url,
									},
									"expected_sha256": None,
									"filled_required": False,
									"has_submittal": True,
								}
							)
						break
		cover = (
			pdf._generate_cover_page(schedule_name, schedule.ill_project, lines) if include_cover else None
		)
		if include_cover and not cover:
			raise ValueError("Cover generation failed")
		cover_pages = len(PdfReader(io.BytesIO(cover)).pages) if cover else 0

		def load_source(url):
			if not url.startswith(("/files/", "/private/files/")) or ".." in url.split("/"):
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
		if errors and (not allow_partial or not parts):
			lock_running(job_name)
			exports._update_export_job_status(job_name, "FAILED", error_log="\n".join(errors))
			return {
				"success": False,
				"export_job": job_name,
				"manifest": manifest,
				"warnings": warnings + errors,
			}
		from frappe.utils.pdf import get_pdf

		schedule_pdf = get_pdf(
			exports._generate_pdf_content(
				exports._get_schedule_data(schedule_name, include_pricing=False), include_pricing=False
			)
		)
		schedule_pages = len(PdfReader(io.BytesIO(schedule_pdf)).pages)
		index_pages = 0
		for _attempt in range(4):
			page = cover_pages + schedule_pages + index_pages + 1
			for entry in manifest:
				if entry.get("page_count"):
					entry.update(page_start=page, page_end=page + entry["page_count"] - 1)
					page += entry["page_count"]
			rows = "".join(
				"<tr><td>"
				+ html.escape(str(entry.get("designation") or ""))
				+ "</td><td>"
				+ html.escape(str(entry["line_key"]))
				+ "</td><td>"
				+ html.escape(str(entry.get("page_start") or entry.get("reason") or entry["status"]))
				+ "</td></tr>"
				for entry in manifest
			)
			index_pdf = get_pdf(
				"<html><head><style>body{font:10pt Arial} table{width:100%;border-collapse:collapse} td,th{border-bottom:1px solid #ddd;padding:8px;word-break:break-all} thead{display:table-header-group} tr{page-break-inside:avoid}</style></head><body><h1>Packet page index</h1><table><thead><tr><th>Designation</th><th>Line / document</th><th>First page / omission</th></tr></thead><tbody>"
				+ rows
				+ "</tbody></table></body></html>"
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
		result_status = "INCOMPLETE" if errors else "COMPLETE"
		if errors:
			merged = _incomplete_watermark(merged, get_pdf)
		file = exports._save_file_ignore_permissions(
			f"{result_status}_Packet_{job_name}.pdf", merged, "ilL-Export-Job", job_name
		)
		frappe.db.set_value("ilL-Export-Job", job_name, "output_sha256", hashlib.sha256(merged).hexdigest())
		frappe.db.set_value(
			"ilL-Export-Job",
			job_name,
			{"progress": 100, "progress_message": result_status},
			update_modified=False,
		)
		exports._update_export_job_status(
			job_name, result_status, output_file=file.file_url, error_log="\n".join(errors)
		)
		return {
			"success": True,
			"export_job": job_name,
			"file_url": file.file_url,
			"manifest": manifest,
			"warnings": warnings + errors,
			"status": result_status,
			"message": "Incomplete draft generated" if errors else "Spec submittal packet generated",
		}
	except InterruptedPacket:
		raise
	except Exception as error:
		lock_running(job_name)
		frappe.log_error(frappe.get_traceback(), "Packet generation failed")
		exports._update_export_job_status(job_name, "FAILED", error_log=str(error))
		return {"success": False, "export_job": job_name, "message": str(error), "warnings": warnings}
	finally:
		frappe.flags.ill_packet_job = previous
