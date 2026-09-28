# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Temporary System Manager-only diagnostic for File create permission denials."""

import frappe
from frappe import _


@frappe.whitelist()
def file_create_debug(user: str, attached_to_doctype: str = "ilL-Webflow-Product"):
	"""Explain why `user` may be denied creating a File.

	Call: /api/method/illumenate_lighting.illumenate_lighting.api.permission_debug.file_create_debug?user=<email>
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
	doc.is_private = 0

	for path in frappe.get_hooks("has_permission").get("File", []):
		try:
			result["hooks"][path] = repr(frappe.get_attr(path)(doc=doc, ptype="create", user=user))
		except Exception as e:
			result["hooks"][path] = f"raised {type(e).__name__}: {e}"

	controller = frappe.get_attr("frappe.core.doctype.file.file.File")
	method = getattr(controller, "has_permission", None)
	if method:
		try:
			result["controller_has_permission"] = repr(method(doc, "create", user))
		except Exception as e:
			result["controller_has_permission"] = f"raised {type(e).__name__}: {e}"

	try:
		result["user_permissions_on_file"] = frappe.get_all(
			"User Permission", filters={"user": user, "allow": "File"}, fields=["for_value"]
		)
	except Exception:
		pass
	return result
