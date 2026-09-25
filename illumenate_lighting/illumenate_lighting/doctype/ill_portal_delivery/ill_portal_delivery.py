import frappe
from frappe.model.document import Document


class ilLPortalDelivery(Document):
	def validate(self):
		if not self.flags.notification_service_write:
			frappe.throw("Notification records are service-owned")

	def on_trash(self):
		frappe.throw("Notification evidence must be retained")
