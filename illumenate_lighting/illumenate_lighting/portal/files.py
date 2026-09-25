"""Private artifact-owned uploads with current-context authorization.

File ownership is deliberately Administrator. Frappe's native download checks
then reach the upload artifact's permission hook even after uploader revocation.
An upload never adopts caller-selected URLs or changes another File's privacy.
"""

import json

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.file_validation import (
	MAX_FILE_BYTES,
	MAX_FILES,
	validate_content,
)

UPLOAD_DOCTYPE = "ilL-Portal-Upload"
ALLOWED_PARENTS = (
	"ilL-Document-Request",
	"ilL-Project-Fixture-Schedule",
	"Issue",
	"ilL-Portal-Message",
	"ilL-Order-Intake",
	"ilL-Quote-Request",
	"ilL-Order-Change",
)


def _context_access(doctype, name, ptype="read", user=None):
	user = user or frappe.session.user
	if user == "Guest" or doctype not in ALLOWED_PARENTS or not name:
		return False
	if not frappe.db.exists(doctype, name):
		return False
	doc = frappe.get_doc(doctype, name)
	if doctype == "ilL-Order-Change":
		from illumenate_lighting.illumenate_lighting.portal.order_changes import can_access

		return can_access(doc, ptype, user)
	if doctype == "ilL-Quote-Request":
		from illumenate_lighting.illumenate_lighting.portal.quotes import has_permission

		return has_permission(doc, "read", user) and (
			ptype == "read" or doc.state not in ("ISSUED", "CLOSED")
		)
	if doctype == "ilL-Order-Intake":
		from illumenate_lighting.illumenate_lighting.portal.order_intake import can_access

		return can_access(doc, ptype, user)
	if doctype == "ilL-Portal-Message":
		from illumenate_lighting.illumenate_lighting.portal.conversations import has_permission

		return has_permission(doc, "read", user) and (ptype == "read" or doc.actor == user)
	if doctype == "ilL-Project-Fixture-Schedule":
		from illumenate_lighting.illumenate_lighting.portal.access import schedule_permission

		return schedule_permission(doc, ptype, user) and (ptype == "read" or not doc.is_locked)
	if doctype == "ilL-Document-Request":
		from illumenate_lighting.illumenate_lighting.doctype.ill_document_request.ill_document_request import (
			has_permission,
		)

		return has_permission(doc, ptype, user)
	from illumenate_lighting.illumenate_lighting.portal.support import can_read

	return can_read(doc, user)


def has_permission(doc, ptype="read", user=None):
	user = user or frappe.session.user
	if doc.state == "GENERATED_PUBLIC" and ptype in ("read", "select"):
		return True
	if user == "Guest":
		return False
	if ptype not in ("read", "select"):
		return user == "Administrator"
	if doc.state == "STAGING" and doc.requested_by != user:
		return user == "Administrator"
	if not doc.parent_name:
		return doc.requested_by == user and doc.state in ("STAGING", "GENERATED_PRIVATE")
	return _context_access(doc.parent_type, doc.parent_name, "read", user)


@frappe.whitelist(methods=["POST"])
def upload(parent_type=None, parent_name=None):
	"""Receive multipart bytes. A parentless upload is a support-intake draft."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in before uploading"), frappe.PermissionError)
	if parent_name or parent_type:
		if not _context_access(parent_type, parent_name, "write"):
			frappe.throw(_("Upload context is unavailable"), frappe.PermissionError)
	files = frappe.request.files
	if "file" not in files:
		frappe.throw(_("Select a file to upload"))
	source = files["file"]
	content = source.stream.read(MAX_FILE_BYTES + 1)
	try:
		metadata = validate_content(source.filename, content)
	except ValueError as exc:
		frappe.throw(str(exc))
	artifact = frappe.get_doc(
		{
			"doctype": UPLOAD_DOCTYPE,
			"parent_type": parent_type,
			"parent_name": parent_name,
			"requested_by": frappe.session.user,
			"state": "STAGING",
			"sha256": metadata["sha256"],
			"file_size": metadata["size"],
			"mime_type": metadata["mime_type"],
		}
	).insert(ignore_permissions=True)
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": metadata["filename"],
			"content": content,
			"is_private": 1,
			"owner": "Administrator",
			"attached_to_doctype": UPLOAD_DOCTYPE,
			"attached_to_name": artifact.name,
		}
	).insert(ignore_permissions=True)
	# Some File backends may reuse bytes but must never reuse a public URL.
	if not file.is_private or not file.file_url.startswith("/private/files/"):
		frappe.throw(_("Upload storage did not produce a private file"))
	artifact.file = file.name
	artifact.save(ignore_permissions=True)
	return {
		"success": True,
		"upload_id": artifact.name,
		"file_id": file.name,
		"file_url": file.file_url,
		**metadata,
	}


def verify_upload(file_id, parent_type, parent_name, *, allow_unbound=False):
	if not _context_access(parent_type, parent_name, "write"):
		frappe.throw(_("Upload context is unavailable"), frappe.PermissionError)
	file = frappe.get_doc("File", file_id)
	if file.attached_to_doctype != UPLOAD_DOCTYPE or not file.is_private:
		frappe.throw(_("Use a verified private upload"), frappe.PermissionError)
	artifact = frappe.get_doc(UPLOAD_DOCTYPE, file.attached_to_name)
	if artifact.requested_by != frappe.session.user or artifact.file != file.name:
		frappe.throw(_("This upload is unavailable"), frappe.PermissionError)
	unbound = (
		allow_unbound
		and not artifact.parent_type
		and not artifact.parent_name
		and artifact.state == "STAGING"
	)
	if not unbound and (artifact.parent_type != parent_type or artifact.parent_name != parent_name):
		frappe.throw(_("The upload belongs to another request"), frappe.PermissionError)
	if artifact.state not in ("STAGING", "FINALIZED"):
		frappe.throw(_("The upload is not ready"))
	metadata = validate_content(file.file_name, file.get_content())
	if metadata["sha256"] != artifact.sha256:
		frappe.throw(_("Uploaded content changed; upload the file again"))
	return artifact, file


def finalize_files(file_ids, parent_type, parent_name, *, allow_unbound=False):
	if isinstance(file_ids, str):
		file_ids = json.loads(file_ids)
	if not isinstance(file_ids, list) or len(file_ids) > MAX_FILES or len(set(file_ids)) != len(file_ids):
		frappe.throw(_("Choose at most 10 distinct uploaded files"))
	if parent_type not in ALLOWED_PARENTS or not _context_access(parent_type, parent_name, "write"):
		frappe.throw(_("Files unavailable"), frappe.PermissionError)
	frappe.db.sql(f"select name from `tab{parent_type}` where name=%s for update", parent_name)
	if parent_type in ("ilL-Document-Request", "Issue", "ilL-Portal-Message"):
		existing = set(
			frappe.get_all(
				UPLOAD_DOCTYPE,
				filters={"parent_type": parent_type, "parent_name": parent_name, "state": "FINALIZED"},
				pluck="file",
			)
		)
		if len(existing | set(file_ids)) > MAX_FILES:
			frappe.throw(_("An intake can contain at most 10 files"))
	validated = [
		verify_upload(file_id, parent_type, parent_name, allow_unbound=allow_unbound) for file_id in file_ids
	]
	for artifact, _file in validated:
		artifact.parent_type, artifact.parent_name, artifact.state = parent_type, parent_name, "FINALIZED"
		artifact.save(ignore_permissions=True)
	return [
		{"name": file.name, "file_name": file.file_name, "file_url": file.file_url, "sha256": artifact.sha256}
		for artifact, file in validated
	]


def finalize_spec(file_id, schedule_name):
	return finalize_files([file_id], "ilL-Project-Fixture-Schedule", schedule_name)[0]["file_url"]


def list_files(parent_type, parent_name):
	if not _context_access(parent_type, parent_name):
		frappe.throw(_("Files unavailable"), frappe.PermissionError)
	result = []
	for artifact in frappe.get_all(
		UPLOAD_DOCTYPE,
		filters={"parent_type": parent_type, "parent_name": parent_name, "state": "FINALIZED"},
		fields=["file", "sha256"],
	):
		file = frappe.get_doc("File", artifact.file)
		result.append(
			{
				"name": file.name,
				"file_name": file.file_name,
				"file_url": file.file_url,
				"sha256": artifact.sha256,
			}
		)
	return result
