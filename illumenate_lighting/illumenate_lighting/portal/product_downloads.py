"""Isolated product-only generation; personalized output stays private."""

import hashlib
import inspect
import shutil
from functools import wraps
from pathlib import Path
from uuid import uuid4

import frappe
from frappe import _


def isolated_download(function):
	@wraps(function)
	def wrapped(*args, **kwargs):
		values = inspect.signature(function).bind(*args, **kwargs)
		values.apply_defaults()
		personalized = any(
			values.arguments.get(key) for key in ("project_name", "project_location", "fixture_type")
		)
		if personalized and frappe.session.user == "Guest":
			return {
				"success": False,
				"code": "LOGIN_REQUIRED",
				"error": _("Sign in to generate a private PDF with project labels."),
				"login_required": True,
			}
		if not frappe.db.exists(
			"ilL-Webflow-Product", {"product_slug": values.arguments["product_slug"], "is_active": 1}
		):
			return {"success": False, "error": _("Product unavailable")}
		previous = frappe.flags.get("ill_product_download")
		frappe.flags.ill_product_download = "private" if personalized else "public"
		try:
			return function(*args, **kwargs)
		finally:
			frappe.flags.ill_product_download = previous

	return wrapped


def save_generated(filename, content):
	"""Use a new artifact and URL; never downgrade or move a reused private File."""
	from frappe.utils.file_manager import save_file

	from illumenate_lighting.illumenate_lighting.portal.file_validation import validate_content

	metadata = validate_content(filename, content)
	public = frappe.flags.get("ill_product_download") == "public"
	if not public and frappe.session.user == "Guest":
		frappe.throw(_("Please sign in"), frappe.PermissionError)
	artifact = frappe.get_doc(
		{
			"doctype": "ilL-Portal-Upload",
			"requested_by": frappe.session.user,
			"state": "GENERATED_PUBLIC" if public else "GENERATED_PRIVATE",
			"sha256": metadata["sha256"],
			"file_size": len(content),
			"mime_type": "application/pdf",
		}
	).insert(ignore_permissions=True)
	previous = frappe.flags.ignore_permissions
	try:
		frappe.flags.ignore_permissions = True
		file = save_file(filename, content, artifact.doctype, artifact.name, is_private=1)
	finally:
		frappe.flags.ignore_permissions = previous
	frappe.db.set_value("File", file.name, "owner", "Administrator", update_modified=False)
	if public:
		# Public copies get their own path. Keep the private source intact because
		# Frappe may deduplicate its bytes with another private artifact.
		public_name = f"product-{uuid4().hex}.pdf"
		target = Path(frappe.get_site_path("public", "files", public_name))
		shutil.copyfile(file.get_full_path(), target)
		if hashlib.sha256(target.read_bytes()).hexdigest() != metadata["sha256"]:
			target.unlink(missing_ok=True)
			frappe.throw(_("Generated file checksum mismatch"))
		frappe.db.after_rollback.add(lambda: target.unlink(missing_ok=True))
		frappe.db.set_value(
			"File", file.name, {"is_private": 0, "file_url": f"/files/{public_name}"}, update_modified=False
		)
		file.reload()
	artifact.file = file.name
	artifact.save(ignore_permissions=True)
	return file
