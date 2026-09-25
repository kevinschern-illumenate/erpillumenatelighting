import frappe
from frappe.model.document import Document


class ilLPortalEvent(Document):
	def validate(self):
		if not self.is_new() or not self.flags.notification_service_write:
			frappe.throw("Notification records are service-owned")

	def on_trash(self):
		frappe.throw("Notification evidence must be retained")
