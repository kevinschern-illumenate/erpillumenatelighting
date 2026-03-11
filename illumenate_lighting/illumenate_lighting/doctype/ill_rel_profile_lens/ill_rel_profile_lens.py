# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ilLRelProfileLens(Document):
	def validate(self):
		self._validate_no_duplicate_lenses()
		self._validate_single_default()

	def _validate_no_duplicate_lenses(self):
		"""Ensure no duplicate lens specs in the compatible lenses table."""
		seen = set()
		for row in self.compatible_lenses:
			if row.lens_spec in seen:
				frappe.throw(
					_(
						"Duplicate lens spec '{0}' in row {1}. Each lens may only appear once."
					).format(row.lens_spec, row.idx)
				)
			seen.add(row.lens_spec)

	def _validate_single_default(self):
		"""Warn if more than one lens is marked as default for same appearance."""
		defaults_by_appearance: dict[str, list] = {}
		for row in self.compatible_lenses:
			if row.is_default:
				appearance = row.lens_appearance or "Unknown"
				defaults_by_appearance.setdefault(appearance, []).append(row.idx)

		for appearance, rows in defaults_by_appearance.items():
			if len(rows) > 1:
				frappe.msgprint(
					_(
						"Multiple default lenses for appearance '{0}' (rows {1}). "
						"Only the first will be used as the preferred match."
					).format(appearance, ", ".join(str(r) for r in rows)),
					indicator="orange",
					alert=True,
				)
