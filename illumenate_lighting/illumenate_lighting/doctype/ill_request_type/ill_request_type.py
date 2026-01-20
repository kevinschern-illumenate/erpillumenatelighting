# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ilLRequestType(Document):
	def validate(self):
		"""Validate request type configuration."""
		if not self.portal_label:
			self.portal_label = self.type_name

	def get_sla_hours(self, priority: str) -> int:
		"""
		Get SLA hours for a given priority.

		Args:
			priority: Normal, High, or Rush

		Returns:
			int: SLA hours for the priority
		"""
		priority_map = {
			"Normal": self.sla_hours_normal or 72,
			"High": self.sla_hours_high or 48,
			"Rush": self.sla_hours_rush or 24,
		}
		return priority_map.get(priority, 72)
