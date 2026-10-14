import frappe
from frappe.model.document import Document


class ilLPortalDelivery(Document):
	def validate(self):
		if not self.flags.notification_service_write:
			frappe.throw("Notification records are service-owned")
		if not self.recipient and not self.recipient_email:
			frappe.throw("A delivery needs a recipient account or email")

	def on_trash(self):
		frappe.throw("Notification evidence must be retained")
