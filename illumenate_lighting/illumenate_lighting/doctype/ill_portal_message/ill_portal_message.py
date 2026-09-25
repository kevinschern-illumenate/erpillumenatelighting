import frappe
from frappe.model.document import Document


class ilLPortalMessage(Document):
	def validate(self):
		if not self.is_new() or not self.flags.conversation_service_write:
			frappe.throw("Conversation messages are immutable and service-owned")

	def on_trash(self):
		frappe.throw("Conversation messages must be retained")
