# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class IlLConfiguratorSession(Document):
	def before_insert(self):
		self.session_token = frappe.generate_hash(length=32)
		self.user = frappe.session.user
