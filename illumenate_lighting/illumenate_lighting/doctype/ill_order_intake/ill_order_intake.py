import frappe
from frappe.model.document import Document


class ilLOrderIntake(Document):
	def validate(self):
		old = self.get_doc_before_save()
		if not old:
			return
		for field in (
			"sales_order",
			"schedule",
			"customer",
			"requested_by",
			"request_snapshot",
			"request_hash",
		):
			if self.get(field) != old.get(field):
				frappe.throw("Original order intake is immutable")
		if old.state == "APPROVED" and any(
			self.get(field) != old.get(field)
			for field in ("state", "approved_snapshot", "approved_by", "approved_on", "acknowledged_hash")
		):
			frappe.throw("Approved acknowledgment is immutable")
		for field in (
			"intake_key",
			"intake_hash",
			"intake_json",
			"files_json",
			"acknowledgment_file",
			"acknowledgment_sha256",
		):
			if old.get(field) and self.get(field) != old.get(field):
				frappe.throw("Submitted intake and acknowledgment evidence are immutable")
		previous = [row.as_dict() for row in old.decisions or []]
		current = [row.as_dict() for row in self.decisions or []]
		for i, row in enumerate(previous):
			for key in ("action", "actor", "recorded_on", "revision_hash", "note"):
				if i >= len(current) or row.get(key) != current[i].get(key):
					frappe.throw("Order decisions are append-only")
