# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import now_datetime


class ilLQBOSyncLog(Document):
	def before_insert(self):
		if not self.received_at:
			self.received_at = now_datetime()
		if not self.status:
			self.status = "Received"
