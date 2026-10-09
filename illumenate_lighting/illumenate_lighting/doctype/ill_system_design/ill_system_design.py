# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLSystemDesign(Document):
	"""Saved through ``system_design.designs.save_design``; access follows the schedule (WP-2.4)."""

	def validate(self):
		if not self.title and self.fixture_schedule:
			self.title = f"{self.fixture_schedule} design"


def has_permission(doc, ptype="read", user=None):
	from illumenate_lighting.illumenate_lighting.system_design.access import design_permission

	return design_permission(doc, ptype, user)


def get_permission_query_conditions(user=None):
	from illumenate_lighting.illumenate_lighting.system_design.access import design_query_conditions

	return design_query_conditions(user)
