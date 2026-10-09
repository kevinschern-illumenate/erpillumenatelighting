# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class ilLSystemDesignerSettings(Document):
	def validate(self):
		for field in ("vd_target_class2_pct", "vd_target_line_pct", "vd_target_landscape_pct"):
			if not 0 < flt(self.get(field)) <= 10:
				frappe.throw(
					_("{0} must be greater than 0 and at most 10.").format(self.meta.get_label(field))
				)
		for field in ("wire_waste_pct", "plan_route_slack_pct"):
			if not 0 <= flt(self.get(field)) <= 100:
				frappe.throw(_("{0} must be between 0 and 100.").format(self.meta.get_label(field)))
		if flt(self.review_gate_watts) <= 0:
			frappe.throw(_("Review Above Connected Load must be greater than 0."))
		if cint(self.share_max_days) < 1 or not 1 <= cint(self.share_default_days) <= cint(
			self.share_max_days
		):
			frappe.throw(_("Default Expiry must be at least one day and no longer than Maximum Expiry."))
		if cint(self.group_threshold_qty) < 2:
			frappe.throw(_("Group Identical Builds From Quantity must be at least 2."))
