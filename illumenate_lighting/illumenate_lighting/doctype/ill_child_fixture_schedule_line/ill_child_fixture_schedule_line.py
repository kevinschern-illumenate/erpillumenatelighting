# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ilLChildFixtureScheduleLine(Document):
	def validate(self):
		"""Validate and update configuration status."""
		self.update_configuration_status()

	def update_configuration_status(self):
		"""
		Update the configuration_status field based on whether
		the line has a fully configured fixture.

		For ILLUMENATE manufacturer type:
		- Pending: No configured_fixture linked yet
		- Configured: Has a linked configured_fixture
		"""
		if self.manufacturer_type == "ILLUMENATE":
			if self.configured_fixture:
				self.configuration_status = "Configured"
			else:
				self.configuration_status = "Pending"
		else:
			# OTHER manufacturer type - no configuration tracking needed
			self.configuration_status = ""

	def is_fully_configured(self):
		"""
		Check if this line is ready for order conversion.

		Returns:
			bool: True if line is configured (or is OTHER manufacturer type)
		"""
		if self.manufacturer_type == "OTHER":
			# OTHER lines are always considered configured
			return True

		# ILLUMENATE lines need a configured fixture
		return bool(self.configured_fixture)
