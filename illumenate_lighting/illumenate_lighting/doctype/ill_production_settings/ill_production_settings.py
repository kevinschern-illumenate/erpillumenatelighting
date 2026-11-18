# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from illumenate_lighting.illumenate_lighting.api import build_points


class ilLProductionSettings(Document):
	def validate(self):
		for field in [*build_points.WEIGHT_FIELDS.values(), *("release_" + f for f in build_points.WEIGHT_FIELDS.values())]:
			if flt(self.get(field)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(self.meta.get_label(field)))
		if flt(self.points_per_person_day) <= 0:
			frappe.throw(_("Points Per Person Per Day must be greater than 0."))
		if flt(self.paid_hours_per_day) <= 0 or flt(self.shift_hours) <= 0:
			frappe.throw(_("Paid Hours and Shift Working Hours must be greater than 0."))
		if not 2 <= cint(self.pixel_conductors) <= 6:
			frappe.throw(_("Pixel Tape Conductor Bucket must be between 2 and 6."))

	def on_update(self):
		before = self.get_doc_before_save()
		fields = [*build_points.WEIGHT_FIELDS.values(), "points_per_person_day", "paid_hours_per_day"]
		if before and all(flt(before.get(f)) == flt(self.get(f)) for f in fields):
			return
		# Stored counts are re-scored in the background; nothing is recounted.
		frappe.enqueue(
			"illumenate_lighting.illumenate_lighting.api.build_points.rescore",
			queue="long",
			enqueue_after_commit=True,
		)
