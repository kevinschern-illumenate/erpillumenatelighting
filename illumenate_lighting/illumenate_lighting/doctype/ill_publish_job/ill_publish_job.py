import frappe
from frappe.model.document import Document


class ilLPublishJob(Document):
	def validate(self):
		if not self.flags.publication_write:
			frappe.throw("Use the publication service to change this record", frappe.PermissionError)
