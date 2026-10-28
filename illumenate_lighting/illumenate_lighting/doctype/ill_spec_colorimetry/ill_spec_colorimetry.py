# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.photometrics import refresh_templates

# Measured value -> the CRI class minimum it should meet.
CLASS_MINIMUMS = (("ra", "minimum_ra"), ("r9", "r9"), ("tm30_rf", "tm30_rf"), ("tm30_rg", "tm30_rg"))


class ilLSpecColorimetry(Document):
	def validate(self):
		if self.ra is not None and not 0 <= self.ra <= 100:
			frappe.throw("Ra must be between 0 and 100.")
		if self.tm30_rf is not None and not 0 <= self.tm30_rf <= 100:
			frappe.throw("TM-30 Rf must be between 0 and 100.")
		self.check_class_minimums()

	def check_class_minimums(self):
		"""Warn, without blocking, when a measured value falls below its CRI class minimum."""
		if not self.cri_class:
			return []
		minimums = (
			frappe.db.get_value(
				"ilL-Attribute-CRI", self.cri_class, [m for _, m in CLASS_MINIMUMS], as_dict=True
			)
			or {}
		)
		short = [
			f"{self.meta.get_label(field)} {self.get(field)} is below the {self.cri_class} class minimum {minimums[minimum]}"
			for field, minimum in CLASS_MINIMUMS
			if self.get(field) and minimums.get(minimum) and self.get(field) < minimums[minimum]
		]
		if short:
			frappe.msgprint("<br>".join(short), title="Below CRI class", indicator="orange")
		return short

	def on_update(self):
		refresh_templates(self)
