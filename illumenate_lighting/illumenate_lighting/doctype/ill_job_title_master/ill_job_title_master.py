# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Job Title Master DocType

Manages standardized job titles for the lighting industry.
Used as a Link field option in CRM Lead to maintain data quality.
"""

from frappe.model.document import Document


class ilLJobTitleMaster(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		category: DF.Select | None
		description: DF.SmallText | None
		is_active: DF.Check
		job_title_name: DF.Data
		sort_order: DF.Int

	# end: auto-generated types

	def validate(self):
		"""Validation logic before save"""
		# Ensure job title name is properly formatted
		if self.job_title_name:
			self.job_title_name = self.job_title_name.strip()

		# Validate sort_order is positive
		if self.sort_order and self.sort_order < 0:
			self.sort_order = 10

	def before_rename(self, old_name, new_name, merge=False):
		"""Called before renaming the document"""
		# Update the job_title_name field to match new name
		self.job_title_name = new_name
