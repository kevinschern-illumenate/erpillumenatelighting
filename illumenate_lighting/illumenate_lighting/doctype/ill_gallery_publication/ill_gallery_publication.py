import frappe
from frappe.model.document import Document


class ilLGalleryPublication(Document):
	def validate(self):
		if not self.flags.publication_write:
			frappe.throw("Use the gallery publication service to change this record", frappe.PermissionError)

	def on_update(self):
		# The gallery lists its status, so every change here is copied to it.
		from illumenate_lighting.illumenate_lighting.api.gallery_publication import sync_status

		sync_status(self.gallery)
