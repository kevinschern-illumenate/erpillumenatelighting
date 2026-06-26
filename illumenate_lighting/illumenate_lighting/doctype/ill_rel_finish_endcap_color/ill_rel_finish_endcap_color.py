# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ilLRelFinishEndcapColor(Document):
	def validate(self):
		self._validate_single_default_per_finish()

	def _validate_single_default_per_finish(self):
		"""Ensure at most one active default endcap color exists per finish.

		``resolve_endcap_color_from_finish`` orders by ``is_default DESC``; when
		two active rows for the same finish are both flagged default the result
		is non-deterministic. Block the second default here so the resolver
		always has a single, stable winner.
		"""
		if not (self.is_default and self.is_active and self.finish):
			return

		conflicting = frappe.db.exists(
			"ilL-Rel-Finish Endcap Color",
			{
				"finish": self.finish,
				"is_default": 1,
				"is_active": 1,
				"name": ("!=", self.name),
			},
		)
		if conflicting:
			frappe.throw(
				_(
					"Finish {0} already has a default endcap color ({1}). "
					"Only one active default is allowed per finish."
				).format(self.finish, conflicting),
				title=_("Duplicate Default Endcap Color"),
			)
