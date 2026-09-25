import frappe
from frappe.model.document import Document


class ilLItemLiterature(Document):
	def validate(self):
		from illumenate_lighting.illumenate_lighting.portal.file_validation import validate_content
		from illumenate_lighting.illumenate_lighting.portal.staff import require

		require("catalog")
		frappe.db.sql("select name from `tabItem` where name=%s for update", self.item)
		if self.active and frappe.db.exists(
			self.doctype, {"item": self.item, "active": 1, "name": ["!=", self.name]}
		):
			frappe.throw("Retire the current literature approval before activating its replacement.")
		if self.no_document_required:
			if not self.exclusion_reason or self.document:
				frappe.throw("An explicit omission needs a reason and no document.")
		else:
			if not self.document:
				frappe.throw("Select the approved Item document.")
			file = frappe.get_doc("File", self.document)
			if file.is_private or file.attached_to_doctype != "Item" or file.attached_to_name != self.item:
				frappe.throw("Item literature must be an approved public file attached to this Item.")
			self.sha256 = validate_content(file.file_name, file.get_content())["sha256"]
		self.approved_by, self.approved_on = frappe.session.user, frappe.utils.now()
