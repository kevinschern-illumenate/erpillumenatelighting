from frappe.model.document import Document


class ilLMeetingAgendaItem(Document):
	def validate(self):
		# a half-filled link (type without record or the reverse) is treated as no link
		if not (self.reference_doctype and self.reference_name):
			self.reference_doctype = None
			self.reference_name = None
