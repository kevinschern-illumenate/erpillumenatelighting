import frappe
from frappe.model.document import Document


class ilLGalleryPublication(Document):
	def validate(self):
		if not self.flags.publication_write:
			frappe.throw("Use the gallery publication service to change this record", frappe.PermissionError)
