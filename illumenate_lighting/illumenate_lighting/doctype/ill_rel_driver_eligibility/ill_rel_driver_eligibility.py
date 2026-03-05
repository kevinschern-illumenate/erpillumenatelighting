# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

VALID_TEMPLATE_TYPES = ("ilL-Fixture-Template", "ilL-Tape-Neon-Template")


class ilLRelDriverEligibility(Document):
	def before_save(self):
		if not self.template_type:
			self.template_type = "ilL-Fixture-Template"
		if self.template_type not in VALID_TEMPLATE_TYPES:
			frappe.throw(f"Invalid template type '{self.template_type}'. Must be one of {VALID_TEMPLATE_TYPES}")
