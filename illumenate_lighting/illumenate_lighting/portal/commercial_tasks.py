"""Validated assignment for commercial and account request queues."""

import frappe

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.portal.staff import allowed

TYPES = ("ilL-Quote-Request", "ilL-Order-Intake", "ilL-Order-Change", "ilL-Account-Request")


@frappe.whitelist(methods=["POST"])
@atomic_build
def assign(doctype, name, assigned_to=None, due_date=None, expected_modified=None):
	if doctype not in TYPES:
		frappe.throw("Unsupported work queue")
	capabilities = ("sales", "support") if doctype == "ilL-Account-Request" else ("sales",)
	if not any(allowed(capability) for capability in capabilities) or not frappe.has_permission(
		doctype, "read", doc=name
	):
		frappe.throw("Staff queue access required", frappe.PermissionError)
	frappe.db.sql(f"select name from `tab{doctype}` where name=%s for update", name)
	doc = frappe.get_doc(doctype, name)
	if str(doc.modified) != str(expected_modified):
		frappe.throw("This request changed. Reload before assigning it.")
	if assigned_to and (
		not any(allowed(capability, assigned_to) for capability in capabilities)
		or not frappe.has_permission(doctype, "read", doc=doc, user=assigned_to)
	):
		frappe.throw("Choose an enabled staff user with access to this queue")
	doc.assigned_to = assigned_to or None
	if doctype != "ilL-Account-Request":
		doc.due_date = str(frappe.utils.getdate(due_date)) if due_date else None
	doc.flags.account_service = True
	doc.save(ignore_permissions=True)
	return {"success": True, "modified": str(doc.modified)}
