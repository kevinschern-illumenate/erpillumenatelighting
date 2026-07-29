# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.doctype.ill_driver_template.ill_driver_template import (
	_normalise_axis_value,
)

#: Configurator axes on ilL-Child-Controller-Template-Variant, keyed by the
#: ``option_type`` used in ilL-Child-Controller-Allowed-Option.
CONTROLLER_VARIANT_AXES = {
	"Controller Type": "controller_type",
	"Channels": "channels",
	"Zones": "zones",
	"Input Protocol": "input_protocol",
	"Output Protocol": "output_protocol",
	"Wireless Protocol": "wireless_protocol",
	"Mounting Type": "mounting_type",
}

#: Option types stored as scalars rather than attribute links.
CONTROLLER_SCALAR_OPTION_TYPES = ("Channels", "Zones", "Wireless Protocol")


class ilLControllerTemplate(Document):
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
		"""Active variants must be distinguishable by their axis values."""
		seen: dict[tuple, int] = {}
		for row in self.variants or []:
			if not row.is_active:
				continue
			key = tuple(
				_normalise_axis_value(row.get(fieldname))
				for fieldname in CONTROLLER_VARIANT_AXES.values()
			)
			if key in seen:
				frappe.throw(
					f"Row {row.idx}: duplicate variant configuration, already defined in "
					f"row {seen[key]}. Active variants must differ by at least one axis."
				)
			seen[key] = row.idx

	def _validate_allowed_options(self):
		for row in self.allowed_options or []:
			if row.option_type in CONTROLLER_SCALAR_OPTION_TYPES:
				if not row.option_value:
					frappe.throw(
						f"Row {row.idx}: Option Value is required for '{row.option_type}' options"
					)
			elif not row.attribute_link:
				frappe.throw(
					f"Row {row.idx}: Attribute Link is required for '{row.option_type}' options"
				)
