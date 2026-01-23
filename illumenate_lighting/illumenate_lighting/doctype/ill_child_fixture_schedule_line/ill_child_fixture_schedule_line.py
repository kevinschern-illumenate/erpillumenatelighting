# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ilLChildFixtureScheduleLine(Document):
	def validate(self):
		"""Validate and update configuration status."""
		self.update_configuration_status()
		self.update_linked_spec_document()

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

	def update_linked_spec_document(self):
		"""
		Compute and store the linked_spec_document based on line type
		and configuration status.

		Priority order:
		1. For configured ILLUMENATE fixtures: use spec_sheet from configured fixture's template
		2. For unconfigured ILLUMENATE lines with fixture_template_override: use that template's spec_sheet
		3. For unconfigured ILLUMENATE lines with fixture_template: use that template's spec_sheet
		4. For OTHER manufacturer lines: use the attached spec_sheet
		5. For ACCESSORY lines: no spec document
		"""
		self.linked_spec_document = None

		if self.manufacturer_type == "ILLUMENATE":
			# Priority 1: Configured fixture - get spec sheet from its template
			if self.configured_fixture:
				template_name = frappe.db.get_value(
					"ilL-Configured-Fixture", self.configured_fixture, "fixture_template"
				)
				if template_name:
					self.linked_spec_document = frappe.db.get_value(
						"ilL-Fixture-Template", template_name, "spec_sheet"
					)
			# Priority 2: Unconfigured with template override
			elif self.fixture_template_override:
				self.linked_spec_document = frappe.db.get_value(
					"ilL-Fixture-Template", self.fixture_template_override, "spec_sheet"
				)
			# Priority 3: Unconfigured with fixture template selected
			elif self.fixture_template:
				self.linked_spec_document = frappe.db.get_value(
					"ilL-Fixture-Template", self.fixture_template, "spec_sheet"
				)

		elif self.manufacturer_type == "OTHER":
			# Priority 4: Use attached spec sheet for OTHER manufacturers
			self.linked_spec_document = self.spec_sheet

		# ACCESSORY lines don't have spec documents

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
