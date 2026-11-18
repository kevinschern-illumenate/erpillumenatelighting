# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ilLPurchasingSettings(Document):
	def validate(self):
		seen = set()
		for row in self.get("default_lead_times") or []:
			if row.item_group in seen:
				frappe.throw(
					_("Item Group {0} is listed twice in Default Lead Times.").format(row.item_group)
				)
			seen.add(row.item_group)
		types = set()
		for row in self.get("cost_type_defaults") or []:
			if row.cost_type in types:
				frappe.throw(_("Cost Type {0} is listed twice in Cost Type Defaults.").format(row.cost_type))
			types.add(row.cost_type)
