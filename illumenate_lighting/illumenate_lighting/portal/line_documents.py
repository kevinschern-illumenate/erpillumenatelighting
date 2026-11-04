"""Independent, versioned line-document associations with verified private uploads."""

import hashlib
import json
import re

import frappe

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.portal.configuration import resolve_line, schedule_context

DOCTYPE = "ilL-Line-Document"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_DIGESTS = 10


def duplicate_check_enabled():
	"""Plan 4.8 kill switch: on unless a site sets ``ill_portal_upload_duplicate_check`` false."""
	from illumenate_lighting.illumenate_lighting.portal.site_flags import upload_duplicate_check_enabled

	return upload_duplicate_check_enabled()


def line_label(schedule, line_key):
	for row in schedule.get("lines") or []:
		if line_key in (row.get("line_key"), row.get("name")):
			return str(row.get("line_id") or row.get("idx") or line_key)
	return str(line_key)


def _digests(hashes):
	if isinstance(hashes, str):
		try:
			hashes = json.loads(hashes or "[]")
		except ValueError:
			raise ValueError("hashes must be a JSON list of SHA-256 digests") from None
	if not isinstance(hashes, list):
		raise ValueError("hashes must be a JSON list of SHA-256 digests")
	digests = []
	for value in hashes:
		value = str(value or "").strip().lower()
		if SHA256.match(value) and value not in digests:
			digests.append(value)
	return digests[:MAX_DIGESTS]


def active(schedule, line):
	return frappe.get_all(
		DOCTYPE,
		filters={"schedule": schedule, "line_key": line.get("line_key") or line.name, "active": 1},
		fields=["name", "file", "file_name", "sha256", "is_primary", "title", "purpose", "caption"],
		order_by="is_primary desc, creation asc, name asc",
	)


@frappe.whitelist()
def list_documents(schedule_name, line_key):
	from illumenate_lighting.illumenate_lighting.portal.media import PURPOSES, thumbnail_urls

	schedule = schedule_context(schedule_name)
	line = resolve_line(schedule, line_key)
	documents = active(schedule.name, line)
	thumbs = thumbnail_urls([row.file for row in documents])
	for row in documents:
		row["thumbnail_url"] = thumbs.get(row.file) or ""
	return {
		"success": True,
		"modified": str(schedule.modified),
		"documents": documents,
		"manufacturer_type": line.manufacturer_type,
		"purposes": list(PURPOSES),
	}


@frappe.whitelist()
def find_duplicates(schedule_name, line_key=None, hashes=None):
	"""Plan 4.8: which of these SHA-256 digests are already active documents on this schedule.

	Read-only and scoped by ``schedule_context`` (portal read access); the client hashes files
	before uploading so it can warn instead of storing the same bytes twice.
	"""
	schedule = schedule_context(schedule_name)
	digests = _digests(hashes)
	if not digests or not duplicate_check_enabled():
		return {"success": True, "duplicates": []}
	current = None
	if line_key:
		line = resolve_line(schedule, line_key)
		current = line.get("line_key") or line.name
	rows = frappe.get_all(
		DOCTYPE,
		filters={"schedule": schedule.name, "active": 1, "sha256": ["in", digests]},
		fields=["sha256", "line_key", "file_name"],
		order_by="creation asc",
		limit_page_length=50,
	)
	return {
		"success": True,
		"duplicates": [
			{
				"sha256": row.sha256,
				"file_name": row.file_name,
				"line_key": row.line_key,
				"line_label": line_label(schedule, row.line_key),
				"same_line": row.line_key == current,
			}
			for row in rows
		],
	}


@frappe.whitelist(methods=["POST"])
@atomic_build
def attach(
	schedule_name, line_key, file_ids, primary_file=None, expected_modified=None, purpose=None, caption=None
):
	from illumenate_lighting.illumenate_lighting.portal.files import finalize_files
	from illumenate_lighting.illumenate_lighting.portal.media import annotations

	notes = annotations(purpose, caption)
	schedule = schedule_context(schedule_name, write=True, lock=True)
	if str(schedule.modified) != str(expected_modified):
		raise ValueError("Schedule changed. Reload its documents before saving.")
	line = resolve_line(schedule, line_key)
	if primary_file and line.manufacturer_type == "ILLUMENATE":
		raise ValueError(
			"Configured product specifications are generated from the build. Attach reference documents without replacing them."
		)
	files = finalize_files(file_ids, schedule.doctype, schedule.name)
	if primary_file and primary_file not in [file["name"] for file in files]:
		raise ValueError("The primary specification must be one of these verified uploads")
	existing = active(schedule.name, line)
	if (
		len(
			{
				row.file
				for row in existing
				if not (primary_file and row.is_primary and row.file != primary_file)
			}
			| {file["name"] for file in files}
		)
		> 10
	):
		raise ValueError("A line can contain up to 10 selected documents")
	check = duplicate_check_enabled()
	duplicates = []
	for file in files:
		if any(row.file == file["name"] for row in existing):
			continue
		# Plan 4.8: the same bytes already on this line are not stored as a second document.
		same = (
			check
			and file["name"] != primary_file
			and next((row for row in existing if row.sha256 and row.sha256 == file["sha256"]), None)
		)
		if same:
			duplicates.append(
				{
					"file_name": file["file_name"],
					"existing_file_name": same.file_name,
					"line_label": line_label(schedule, line.get("line_key") or line.name),
				}
			)
			continue
		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"schedule": schedule.name,
				"line_key": line.get("line_key") or line.name,
				"file": file["name"],
				"file_name": file["file_name"],
				"sha256": file["sha256"],
				"is_primary": int(file["name"] == primary_file),
				"active": 1,
				"title": file["file_name"],
				"attached_by": frappe.session.user,
				**annotations(file.get("purpose"), file.get("caption")),
				**notes,
			}
		)
		doc.flags.line_document_service = True
		doc.insert(ignore_permissions=True)
	if primary_file:
		for row in active(schedule.name, line):
			frappe.db.set_value(
				DOCTYPE,
				row.name,
				{
					"is_primary": int(row.file == primary_file),
					"active": 0 if row.is_primary and row.file != primary_file else 1,
				},
			)
		if line.manufacturer_type == "OTHER":
			line.spec_sheet = next(file["file_url"] for file in files if file["name"] == primary_file)
	schedule.save(ignore_permissions=True)
	return {
		"success": True,
		"modified": str(schedule.modified),
		"documents": active(schedule.name, line),
		"duplicates": duplicates,
	}


@frappe.whitelist(methods=["POST"])
@atomic_build
def remove(name, expected_modified):
	doc = frappe.get_doc(DOCTYPE, name)
	schedule = schedule_context(doc.schedule, write=True, lock=True)
	if str(schedule.modified) != str(expected_modified):
		raise ValueError("Schedule changed. Reload its documents before saving.")
	line = resolve_line(schedule, doc.line_key)
	frappe.db.set_value(DOCTYPE, doc.name, "active", 0)
	if doc.is_primary and line.manufacturer_type == "OTHER":
		line.spec_sheet = None
	schedule.save(ignore_permissions=True)
	return {"success": True, "modified": str(schedule.modified)}


@frappe.whitelist(methods=["POST"])
@atomic_build
def annotate(name, expected_modified, purpose=None, caption=None):
	"""Change a line document's purpose or caption (hardening plan 4.3); the file never changes."""
	from illumenate_lighting.illumenate_lighting.portal.media import annotations

	doc = frappe.get_doc(DOCTYPE, name)
	schedule = schedule_context(doc.schedule, write=True, lock=True)
	if str(schedule.modified) != str(expected_modified):
		raise ValueError("Schedule changed. Reload its documents before saving.")
	if not doc.active:
		raise ValueError("This document was removed from the line")
	notes = annotations(purpose, caption)
	if notes:
		frappe.db.set_value(DOCTYPE, doc.name, notes)
		schedule.save(ignore_permissions=True)
	return {"success": True, "modified": str(schedule.modified), **notes}


def clone(source_schedule, source_line, target_schedule, target_line):
	for row in active(source_schedule, source_line):
		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				**{
					key: row.get(key)
					for key in ("file", "file_name", "sha256", "title", "is_primary", "purpose", "caption")
				},
				"schedule": target_schedule,
				"line_key": target_line.line_key,
				"active": 1,
				"copied_from": row.name,
				"attached_by": frappe.session.user,
			}
		)
		doc.flags.line_document_service = True
		doc.insert(ignore_permissions=True)


def file_access(file_name, user):
	from illumenate_lighting.illumenate_lighting.portal.access import can_read_schedule

	for name in frappe.get_all(DOCTYPE, filters={"file": file_name}, pluck="schedule", distinct=True):
		if can_read_schedule(frappe.get_doc("ilL-Project-Fixture-Schedule", name), user):
			return True
	return False


@frappe.whitelist()
def download(name):
	doc = frappe.get_doc(DOCTYPE, name)
	schedule_context(doc.schedule)
	file = frappe.get_doc("File", doc.file)
	content = file.get_content()
	if hashlib.sha256(content).hexdigest() != doc.sha256:
		raise ValueError("Specification bytes changed. Replace the document through a new upload.")
	frappe.local.response.update(type="download", filename=doc.file_name, filecontent=content)


def has_permission(doc, ptype="read", user=None):
	from illumenate_lighting.illumenate_lighting.portal.access import can_read_schedule

	return ptype in ("read", "select") and can_read_schedule(
		frappe.get_doc("ilL-Project-Fixture-Schedule", doc.schedule), user
	)


def query_conditions(user=None):
	from illumenate_lighting.illumenate_lighting.portal.access import schedule_query_conditions

	predicate = schedule_query_conditions(user) or "1=1"
	return f"`tabilL-Line-Document`.schedule IN (SELECT name FROM `tabilL-Project-Fixture-Schedule` WHERE {predicate})"
