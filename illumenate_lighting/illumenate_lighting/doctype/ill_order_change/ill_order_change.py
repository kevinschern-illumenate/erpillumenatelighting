import frappe
from frappe.model.document import Document


class ilLOrderChange(Document):
	def validate(self):
		old = self.get_doc_before_save()
		if not old:
			if not self.flags.order_change_service:
				frappe.throw("Create order changes through the request service")
			return
		for key in (
			"sales_order",
			"customer",
			"requested_by",
			"request_type",
			"note",
			"request_key",
			"request_hash",
			"original_snapshot",
			"original_hash",
		):
			if self.get(key) != old.get(key):
				frappe.throw("Original change request is immutable")
		if old.state in ("COMPLETED", "REJECTED"):
			for key in (
				"state",
				"staff_note",
				"new_schedule",
				"result_sales_order",
				"result_snapshot",
				"decided_by",
				"decided_on",
			):
				if self.get(key) != old.get(key):
					frappe.throw("Decided requests are immutable")
		if self.state in ("COMPLETED", "REJECTED") and not self.flags.order_change_service:
			frappe.throw("Use the revision-checked decision action")

	def on_trash(self):
		frappe.throw("Keep order-change records for the commercial audit trail")
