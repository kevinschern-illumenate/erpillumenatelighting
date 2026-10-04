import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from illumenate_lighting.illumenate_lighting.portal.product_finder import verification


class ilLProductVerificationRequest(Document):
	def validate(self):
		previous = self.get_doc_before_save()
		old = previous.state if previous else None
		if old and old != self.state:
			if not verification.staff() and not self.flags.finder_service_write:
				frappe.throw("Only verification staff can change the decision", frappe.PermissionError)
			if self.state not in verification.TRANSITIONS.get(old, set()):
				frappe.throw("This verification transition is not allowed")
		if not old and self.state != "REQUESTED":
			frappe.throw("A verification request must start as Requested")
		if self.state in ("VERIFIED", "NOT_FEASIBLE"):
			if not (self.resolution or "").strip():
				frappe.throw("Enter a resolution before deciding this request")
			if old != self.state:
				self.resolved_by, self.resolved_on = frappe.session.user, now_datetime()
		if not self.due_date:
			self.due_date = verification.due_date()

	def on_update(self):
		old = self.get_doc_before_save()
		if self.state in verification.FINAL and (not old or old.state != self.state):
			verification.propagate(self)
