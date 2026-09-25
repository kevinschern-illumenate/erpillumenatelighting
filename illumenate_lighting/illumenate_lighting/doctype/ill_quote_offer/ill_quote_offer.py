import frappe
from frappe.model.document import Document


class ilLQuoteOffer(Document):
	def validate(self):
		if not self.flags.offer_write:
			frappe.throw("Use the issued-offer service", frappe.PermissionError)
		previous = self.get_doc_before_save()
		if not previous:
			return
		for field in (
			"quotation",
			"quote_request",
			"schedule",
			"customer",
			"valid_until",
			"issued_by",
			"issued_on",
			"snapshot_json",
			"snapshot_hash",
			"schedule_hash",
		):
			if self.get(field) != previous.get(field):
				frappe.throw("Issued offer content is immutable; issue an amended Quotation")
		for field in (
			"pdf_file",
			"pdf_sha256",
			"sales_order",
			"response_hash",
			"responded_by",
			"responded_on",
			"response_note",
		):
			if previous.get(field) and self.get(field) != previous.get(field):
				frappe.throw("Issued offer artifacts and buyer responses are immutable")
