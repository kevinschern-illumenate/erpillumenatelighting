import frappe
from frappe.model.document import Document


class ilLPortalInvitation(Document):
	def validate(self):
		if not self.flags.get("account_service"):
			frappe.throw("Use the account service to maintain this record", frappe.PermissionError)

	def on_trash(self):
		frappe.throw("Account decisions and invitation receipts are retained")
