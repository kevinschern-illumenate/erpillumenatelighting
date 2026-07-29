# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

#: Configurator axes on ilL-Child-Driver-Template-Variant, keyed by the
#: ``option_type`` used in ilL-Child-Driver-Allowed-Option.
DRIVER_VARIANT_AXES = {
	"Wattage": "wattage",
	"Voltage Output": "voltage_output",
	"Input Protocol": "input_protocol",
	"Output Protocol": "output_protocol",
}


class ilLDriverTemplate(Document):
	def validate(self):
		self._validate_single_default()
		self._validate_unique_variant_axes()
		self._validate_allowed_options()

	def _validate_single_default(self):
		defaults = [r for r in (self.variants or []) if r.is_default]
		if len(defaults) > 1:
			frappe.throw(
				"Only one variant may be marked as default (rows "
				+ ", ".join(str(r.idx) for r in defaults)
				+ ")"
			)

	def _validate_unique_variant_axes(self):
		"""Active variants must be distinguishable by their axis values.

		The configurator resolves a selection to exactly one variant, so two
		active rows sharing the same axis tuple would be ambiguous.
		"""
		seen: dict[tuple, int] = {}
		for row in self.variants or []:
			if not row.is_active:
				continue
			key = tuple(
				_normalise_axis_value(row.get(fieldname))
				for fieldname in DRIVER_VARIANT_AXES.values()
			)
			if key in seen:
				frappe.throw(
					f"Row {row.idx}: duplicate variant configuration, already defined in "
					f"row {seen[key]}. Active variants must differ by at least one axis."
				)
			seen[key] = row.idx

	def _validate_allowed_options(self):
		for row in self.allowed_options or []:
			if row.option_type == "Wattage":
				if not row.option_value:
					frappe.throw(f"Row {row.idx}: Option Value is required for Wattage options")
			elif not row.attribute_link:
				frappe.throw(
					f"Row {row.idx}: Attribute Link is required for '{row.option_type}' options"
				)


def _normalise_axis_value(value) -> str:
	"""Render an axis value as a comparable string ("" when unset).

	Numbers are compared numerically so that a stored Float of ``60.0`` and a
	selection posted as ``"60"`` or ``"60.0"`` all collapse to ``"60"``.
	"""
	if value in (None, ""):
		return ""
	if isinstance(value, (int, float)):
		return f"{float(value):g}"
	text = str(value).strip()
	try:
		return f"{float(text):g}"
	except ValueError:
		return text
