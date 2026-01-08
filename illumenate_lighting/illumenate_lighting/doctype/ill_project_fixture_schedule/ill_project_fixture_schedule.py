# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ilLProjectFixtureSchedule(Document):
	@frappe.whitelist()
	def create_sales_order(self):
		"""
		Create a Sales Order from this fixture schedule.

		Creates a Sales Order for the schedule's customer with SO lines for
		manufacturer_type = ILLUMENATE only. Each SO line links to the chosen
		ilL-Configured-Fixture and copies qty, location/notes, and key computed
		fields into custom SO Item fields for quick visibility.

		Returns:
			str: Name of the created Sales Order document
		"""
		if not self.customer:
			frappe.throw(_("Customer is required to create a Sales Order"))

		# Filter lines to only ILLUMENATE manufacturer type with configured fixtures
		illumenate_lines = [
			line for line in self.lines
			if line.manufacturer_type == "ILLUMENATE" and line.configured_fixture
		]

		if not illumenate_lines:
			frappe.throw(
				_("No ilLumenate fixture lines with configured fixtures found in this schedule")
			)

		# Create Sales Order
		so = frappe.new_doc("Sales Order")
		so.customer = self.customer
		so.project = self.project if self.project else None
		so.delivery_date = frappe.utils.add_days(frappe.utils.nowdate(), 30)

		# Add SO items for each ILLUMENATE line
		for line in illumenate_lines:
			# Fetch the configured fixture to get computed values
			configured_fixture = frappe.get_doc(
				"ilL-Configured-Fixture", line.configured_fixture
			)

			# Get template code from the fixture template
			template_code = None
			if configured_fixture.fixture_template:
				template_code = configured_fixture.fixture_template

			# Get the configured item or use a placeholder
			# The configured_item is the sellable Item linked from the configured fixture
			item_code = configured_fixture.configured_item
			if not item_code:
				# If no configured item yet, use a placeholder or error
				frappe.throw(
					_(
						"Line {0}: Configured Fixture {1} does not have a configured Item. "
						"Please ensure the fixture has been fully configured."
					).format(line.line_id or line.idx, line.configured_fixture)
				)

			so_item = so.append("items", {})
			so_item.item_code = item_code
			so_item.qty = line.qty or 1
			so_item.description = self._build_item_description(line, configured_fixture)

			# Set custom fields for quick visibility
			so_item.ill_configured_fixture = line.configured_fixture
			so_item.ill_template_code = template_code
			so_item.ill_requested_length_mm = configured_fixture.requested_overall_length_mm
			so_item.ill_mfg_length_mm = configured_fixture.manufacturable_overall_length_mm
			so_item.ill_runs_count = configured_fixture.runs_count
			so_item.ill_total_watts = configured_fixture.total_watts
			so_item.ill_finish = configured_fixture.finish
			so_item.ill_lens = configured_fixture.lens_appearance
			so_item.ill_engine_version = configured_fixture.engine_version

		so.insert()

		# Update schedule status to ORDERED
		self.db_set("status", "ORDERED")

		frappe.msgprint(
			_("Sales Order {0} created successfully").format(
				frappe.utils.get_link_to_form("Sales Order", so.name)
			),
			indicator="green",
			alert=True,
		)

		return so.name

	def _build_item_description(self, line, configured_fixture):
		"""Build a descriptive text for the SO item."""
		parts = []

		if configured_fixture.fixture_template:
			parts.append(configured_fixture.fixture_template)

		if configured_fixture.manufacturable_overall_length_mm:
			length_ft = configured_fixture.manufacturable_overall_length_mm / 304.8
			parts.append(f"{length_ft:.2f}ft ({configured_fixture.manufacturable_overall_length_mm}mm)")

		if configured_fixture.finish:
			parts.append(configured_fixture.finish)

		if configured_fixture.lens_appearance:
			parts.append(configured_fixture.lens_appearance)

		if line.location:
			parts.append(f"Location: {line.location}")

		if line.notes:
			parts.append(f"Notes: {line.notes}")

		return " | ".join(parts) if parts else None
