# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	TAPE_NEON_CATEGORIES,
	spec_categories_for,
)


class ilLTapeNeonTemplate(Document):
	"""Template/family for LED Tape, COB Tape and LED Neon products.

	Analogous to ilL-Fixture-Template but for tape and neon product categories.
	Links to tape specs (ilL-Spec-LED Tape) and defines allowed configuration
	options via child tables.
	"""

	def validate(self):
		self._validate_product_category()
		self._validate_allowed_specs()

	def _validate_product_category(self):
		if self.product_category not in TAPE_NEON_CATEGORIES:
			frappe.throw("Product Category must be 'LED Tape', 'COB Tape' or 'LED Neon'")

	def _validate_allowed_specs(self):
		"""Ensure linked tape specs match the template's product category.

		A COB Tape template also accepts specs still filed as LED Tape.
		"""
		if not self.allowed_tape_specs:
			return
		accepted = spec_categories_for(self.product_category)
		for row in self.allowed_tape_specs:
			if row.tape_spec:
				spec_category = frappe.db.get_value(
					"ilL-Spec-LED Tape", row.tape_spec, "product_category"
				)
				if spec_category and spec_category not in accepted:
					frappe.throw(
						f"Row {row.idx}: Tape Spec '{row.tape_spec}' has product category "
						f"'{spec_category}' but this template is for '{self.product_category}'"
					)
