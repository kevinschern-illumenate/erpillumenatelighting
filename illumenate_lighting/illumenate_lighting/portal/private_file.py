"""Narrow native-download guard for portal-owned artifacts and request files."""

import frappe
from frappe.core.doctype.file.file import File


def portal_file_permission(doc, ptype="read", user=None):
	if ptype not in ("read", "select", "print", "export"):
		return None
	user = user or frappe.session.user
	if doc.attached_to_doctype == "ilL-Order-Intake":
		from illumenate_lighting.illumenate_lighting.portal.order_intake import can_access

		return can_access(frappe.get_doc("ilL-Order-Intake", doc.attached_to_name), "read", user)
	if doc.attached_to_doctype == "ilL-Quote-Offer":
		from illumenate_lighting.illumenate_lighting.portal.offers import can_read

		return can_read(frappe.get_doc("ilL-Quote-Offer", doc.attached_to_name), user)
	if doc.attached_to_doctype == "ilL-Export-Job":
		from illumenate_lighting.illumenate_lighting.doctype.ill_export_job.ill_export_job import (
			has_permission,
		)

		return has_permission(frappe.get_doc("ilL-Export-Job", doc.attached_to_name), "read", user)
	if doc.attached_to_doctype == "ilL-Portal-Upload":
		from illumenate_lighting.illumenate_lighting.portal.files import has_permission

		if has_permission(frappe.get_doc("ilL-Portal-Upload", doc.attached_to_name), "read", user):
			return True
		from illumenate_lighting.illumenate_lighting.portal.line_documents import file_access

		return file_access(doc.name, user)
	if doc.attached_to_doctype != "ilL-Document-Request":
		return None
	from illumenate_lighting.illumenate_lighting.doctype.ill_document_request.ill_document_request import (
		_is_request_staff,
		has_permission,
	)

	request = frappe.get_doc("ilL-Document-Request", doc.attached_to_name)
	if not has_permission(request, "read", user):
		return False
	if _is_request_staff(request, user):
		return True
	matching = [row for row in request.deliverables or [] if row.file == doc.file_url]
	if matching:
		return any(row.is_published_to_portal for row in matching)
	return doc.owner == request.requester_user


class PortalFile(File):
	def is_downloadable(self):
		decision = portal_file_permission(self)
		return super().is_downloadable() if decision is None else decision
