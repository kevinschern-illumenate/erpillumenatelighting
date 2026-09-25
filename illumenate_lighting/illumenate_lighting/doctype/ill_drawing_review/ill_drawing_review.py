import frappe
from frappe.model.document import Document


class ilLDrawingReview(Document):
	def validate(self):
		if not self.is_new():
			frappe.throw("Drawing decisions are immutable; publish a new revision for another review")
