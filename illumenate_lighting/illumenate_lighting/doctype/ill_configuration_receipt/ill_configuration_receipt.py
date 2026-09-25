import frappe
from frappe.model.document import Document


class ilLConfigurationReceipt(Document):
	def validate(self):
		if not self.is_new() or not self.flags.configuration_service_write:
			frappe.throw("Configuration save receipts are immutable and service-owned")

	def on_trash(self):
		frappe.throw("Configuration save receipts must be retained")
