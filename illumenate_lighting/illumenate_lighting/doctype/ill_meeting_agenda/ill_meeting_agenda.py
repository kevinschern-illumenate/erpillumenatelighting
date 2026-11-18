import frappe
from frappe.model.document import Document


class ilLMeetingAgenda(Document):
	def on_trash(self):
		# items point at the agenda with a required link, so remove them with it
		for name in frappe.get_all("ilL-Meeting-Agenda-Item", filters={"agenda": self.name}, pluck="name"):
			frappe.delete_doc("ilL-Meeting-Agenda-Item", name, ignore_permissions=True)
