import frappe
from frappe.model.document import Document


class ilLQuoteRequest(Document):
	def validate(self):
		previous = self.get_doc_before_save()
		if previous and any(
			self.get(key) != previous.get(key)
			for key in (
				"schedule",
				"customer",
				"project",
				"requested_by",
				"request_snapshot",
				"request_hash",
				"idempotency_key",
				"notes",
			)
		):
			frappe.throw("Submitted quote intake is immutable. Create a new request revision.")
