import frappe
from frappe.model.document import Document


class ilLLineDocument(Document):
	def validate(self):
		if not self.flags.line_document_service:
			frappe.throw(
				"Use the schedule document manager to change specification associations.",
				frappe.PermissionError,
			)
		old = self.get_doc_before_save()
		if old and any(
			self.get(key) != old.get(key) for key in ("schedule", "line_key", "file", "sha256", "copied_from")
		):
			frappe.throw("Specification associations are immutable. Attach a replacement.")
