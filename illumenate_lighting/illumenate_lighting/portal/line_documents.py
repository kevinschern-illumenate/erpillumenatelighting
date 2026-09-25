"""Independent, versioned line-document associations with verified private uploads."""

import hashlib

import frappe

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.portal.configuration import resolve_line, schedule_context

DOCTYPE = "ilL-Line-Document"


def active(schedule, line):
	return frappe.get_all(
		DOCTYPE,
		filters={"schedule": schedule, "line_key": line.get("line_key") or line.name, "active": 1},
		fields=["name", "file", "file_name", "sha256", "is_primary", "title"],
		order_by="is_primary desc, creation asc, name asc",
	)


@frappe.whitelist()
def list_documents(schedule_name, line_key):
	schedule = schedule_context(schedule_name)
	line = resolve_line(schedule, line_key)
	return {
		"success": True,
		"modified": str(schedule.modified),
		"documents": active(schedule.name, line),
		"manufacturer_type": line.manufacturer_type,
	}


@frappe.whitelist(methods=["POST"])
@atomic_build
def attach(schedule_name, line_key, file_ids, primary_file=None, expected_modified=None):
	from illumenate_lighting.illumenate_lighting.portal.files import finalize_files

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
	for file in files:
		if any(row.file == file["name"] for row in existing):
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
	return {"success": True, "modified": str(schedule.modified), "documents": active(schedule.name, line)}


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


def clone(source_schedule, source_line, target_schedule, target_line):
	for row in active(source_schedule, source_line):
		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				**{key: row.get(key) for key in ("file", "file_name", "sha256", "title", "is_primary")},
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
