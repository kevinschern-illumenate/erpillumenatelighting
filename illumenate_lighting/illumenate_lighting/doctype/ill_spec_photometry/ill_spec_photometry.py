# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.photometrics import refresh_templates

NON_NEGATIVE = (
	"beam_angle",
	"field_angle",
	"max_candela",
	"ugr",
	"delivered_lumens_per_ft",
	"efficacy_lm_per_w",
	"watts_per_ft_tested",
)


class ilLSpecPhotometry(Document):
	def validate(self):
		for field in NON_NEGATIVE:
			if (self.get(field) or 0) < 0:
				frappe.throw(f"{self.meta.get_label(field)} cannot be negative.")
		for field in ("beam_angle", "field_angle"):
			if (self.get(field) or 0) > 360:
				frappe.throw(f"{self.meta.get_label(field)} must be at most 360°.")
		if self.beam_angle and self.field_angle and self.field_angle < self.beam_angle:
			frappe.msgprint(
				"Field angle is usually wider than beam angle; check the values.", indicator="orange"
			)

	def on_update(self):
		refresh_templates(self)
