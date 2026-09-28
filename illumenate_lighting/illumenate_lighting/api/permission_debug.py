# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Temporary System Manager-only diagnostic for File create permission denials."""

import frappe
from frappe import _


@frappe.whitelist()
def file_create_debug(
	user: str,
	attached_to_doctype: str = "ilL-Webflow-Product",
	attached_to_name: str = "",
	attached_to_field: str = "featured_image",
):
	"""Explain why `user` may be denied creating a File.

	Call: /api/method/illumenate_lighting.illumenate_lighting.api.permission_debug.file_create_debug?user=<email>&attached_to_name=ill-fs01-sw
	"""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("System Manager role required"), frappe.PermissionError)

	result = {
		"user": user,
		"roles": frappe.get_roles(user),
		"docperm_file_create": frappe.has_permission("File", "create", user=user),
		"hooks": {},
	}

	doc = frappe.new_doc("File")
	doc.attached_to_doctype = attached_to_doctype
	doc.attached_to_name = attached_to_name or None
	doc.attached_to_field = attached_to_field
	doc.folder = "Home"
	doc.file_name = "debug.jpg"
	doc.is_private = 0

	for path in frappe.get_hooks("has_permission").get("File", []):
		try:
			result["hooks"][path] = repr(frappe.get_attr(path)(doc=doc, ptype="create", user=user))
		except Exception as e:
			result["hooks"][path] = f"raised {type(e).__name__}: {e}"

	if attached_to_name:
		try:
			ref = frappe.get_doc(attached_to_doctype, attached_to_name)
			result["attached_doc"] = {
				"write": ref.has_permission("write", user=user),
				"read": ref.has_permission("read", user=user),
				"docstatus": ref.docstatus,
				"owner": ref.owner,
			}
		except Exception as e:
			result["attached_doc"] = f"raised {type(e).__name__}: {e}"

	try:
		result["file_permission_create"] = frappe.has_permission(doc=doc, ptype="create", user=user)
	except Exception as e:
		result["file_permission_create"] = f"raised {type(e).__name__}: {e}"
	result["session_user"] = frappe.session.user

	try:
		result["user_permissions_on_file"] = frappe.get_all(
			"User Permission", filters={"user": user, "allow": "File"}, fields=["for_value"]
		)
	except Exception:
		pass
	return result
