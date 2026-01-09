# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ilLConfiguredFixture(Document):
	def autoname(self):
		"""
		Generate part number in format:
		ILL-{Profile Series}-{LED Package Code}-{CCT Code}-{Fixture Output Code}-{Lens Code}-{Mounting Code}-{Finish Code}-{Length in inches}
		"""
		parts = ["ILL"]

		# Profile Series from Fixture Template's default_profile_family
		profile_family = ""
		if self.fixture_template:
			profile_family = frappe.db.get_value(
				"ilL-Fixture-Template", self.fixture_template, "default_profile_family"
			) or ""
		parts.append(profile_family)

		# LED Package Code - get from tape_offering -> led_package (the doc name IS the code)
		led_package_code = ""
		if self.tape_offering:
			led_package_code = frappe.db.get_value(
				"ilL-Rel-Tape Offering", self.tape_offering, "led_package"
			) or ""
		parts.append(led_package_code)

		# CCT Code from tape_offering -> cct -> code
		cct_code = ""
		if self.tape_offering:
			cct_name = frappe.db.get_value(
				"ilL-Rel-Tape Offering", self.tape_offering, "cct"
			)
			if cct_name:
				cct_code = frappe.db.get_value("ilL-Attribute-CCT", cct_name, "code") or ""
		parts.append(cct_code)

		# Fixture Output Code = Output Level sku_code based on (tape output level * lens transmission %)
		fixture_output_code = self._get_fixture_output_code()
		parts.append(fixture_output_code)

		# Lens Code from lens_appearance
		lens_code = ""
		if self.lens_appearance:
			lens_code = frappe.db.get_value(
				"ilL-Attribute-Lens Appearance", self.lens_appearance, "code"
			) or ""
		parts.append(lens_code)

		# Mounting Code from mounting_method
		mounting_code = ""
		if self.mounting_method:
			mounting_code = frappe.db.get_value(
				"ilL-Attribute-Mounting Method", self.mounting_method, "code"
			) or ""
		parts.append(mounting_code)

		# Finish Code from finish
		finish_code = ""
		if self.finish:
			finish_code = frappe.db.get_value(
				"ilL-Attribute-Finish", self.finish, "code"
			) or ""
		parts.append(finish_code)

		# Requested Length in inches (convert from mm)
		length_inches = ""
		if self.requested_overall_length_mm:
			length_inches = str(round(self.requested_overall_length_mm / 25.4, 2))
		parts.append(length_inches)

		self.name = "-".join(parts)

	def _get_fixture_output_code(self) -> str:
		"""
		Calculate fixture output code based on tape output level value * lens transmission %.
		Returns the sku_code of the matching fixture-level output level.
		"""
		if not self.tape_offering or not self.lens_appearance:
			return ""

		# Get tape output level value
		output_level_name = frappe.db.get_value(
			"ilL-Rel-Tape Offering", self.tape_offering, "output_level"
		)
		if not output_level_name:
			return ""

		tape_output_value = frappe.db.get_value(
			"ilL-Attribute-Output Level", output_level_name, "value"
		) or 0

		# Get lens transmission %
		lens_transmission = frappe.db.get_value(
			"ilL-Attribute-Lens Appearance", self.lens_appearance, "transmission"
		) or 100

		# Calculate fixture output = tape output * (transmission / 100)
		fixture_output_value = int(round(tape_output_value * (lens_transmission / 100)))

		# Find the closest fixture-level output level by value
		fixture_output_levels = frappe.get_all(
			"ilL-Attribute-Output Level",
			filters={"is_fixture_level": 1},
			fields=["name", "value", "sku_code"],
			order_by="value asc"
		)

		if not fixture_output_levels:
			return ""

		# Find closest match
		closest = min(fixture_output_levels, key=lambda x: abs((x.value or 0) - fixture_output_value))
		return closest.sku_code or ""
