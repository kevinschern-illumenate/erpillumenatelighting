# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.system_design import wire

ITEM_FIELDS = ["name", "is_sales_item", "disabled", "has_variants", "stock_uom"]


class ilLSpecWire(Document):
	def validate(self):
		self.category = wire.category_label(self.category) or self.category
		applications, _unknown = wire.split_applications(self.applications)
		if applications:
			self.applications = ",".join(applications)
		if self.sales_uom_mode != "Per Spool":
			self.spool_length_ft = None
		item = frappe.db.get_value("Item", self.item, ITEM_FIELDS, as_dict=True) if self.item else None
		problems = (
			wire.spec_problems(self.as_dict())
			+ wire.conductor_problems([row.as_dict() for row in self.conductors])
			+ wire.item_problems(item, self.sales_uom_mode)
		)
		if problems:
			frappe.throw(_("Wire spec is not valid:") + "<br>" + "<br>".join(problems))
