# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.system_design.geometry import cross_section_problems


class ilLSpecAccessory(Document):
	def validate(self):
		problems = cross_section_problems(self.get("cross_section_json"))
		if problems:
			frappe.throw("<br>".join(problems))
