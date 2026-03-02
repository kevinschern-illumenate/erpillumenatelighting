# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ilLExtrusionKitTemplate(Document):
	def validate(self):
		"""Validate kit template data."""
		self._validate_allowed_options()
		self._validate_quantities()

	def _validate_allowed_options(self):
		"""Ensure at least one option per required type is present."""
		if not self.allowed_options:
			return

		option_types_present = {row.option_type for row in self.allowed_options if row.is_active}

		# Warn if critical option types are missing
		recommended = {"Finish", "Lens Appearance", "Endcap Style", "Endcap Color"}
		missing = recommended - option_types_present
		if missing:
			frappe.msgprint(
				_("Recommended option types not yet configured: {0}").format(
					", ".join(sorted(missing))
				),
				indicator="orange",
				title=_("Kit Template Setup"),
			)

	def _validate_quantities(self):
		"""Validate component quantities are sensible."""
		if self.profile_stock_length_mm and self.profile_stock_length_mm <= 0:
			frappe.throw(_("Profile stock length must be positive"))
		if self.lens_stock_length_mm and self.lens_stock_length_mm <= 0:
			frappe.throw(_("Lens stock length must be positive"))
		if (self.solid_endcap_qty or 0) < 0:
			frappe.throw(_("Solid endcap quantity cannot be negative"))
		if (self.feed_through_endcap_qty or 0) < 0:
			frappe.throw(_("Feed-through endcap quantity cannot be negative"))
		if (self.mounting_accessory_qty or 0) < 0:
			frappe.throw(_("Mounting accessory quantity cannot be negative"))

	def get_allowed_values(self, option_type: str) -> list[str]:
		"""Return active allowed values for a given option type."""
		values = []
		for row in self.allowed_options:
			if row.option_type == option_type and row.is_active:
				field_map = {
					"Finish": "finish",
					"Lens Appearance": "lens_appearance",
					"Mounting Method": "mounting_method",
					"Endcap Style": "endcap_style",
					"Endcap Color": "endcap_color",
				}
				field = field_map.get(option_type)
				if field and getattr(row, field, None):
					values.append(getattr(row, field))
		return values

	def get_default_value(self, option_type: str) -> str | None:
		"""Return the default value for a given option type, if set."""
		for row in self.allowed_options:
			if row.option_type == option_type and row.is_active and row.is_default:
				field_map = {
					"Finish": "finish",
					"Lens Appearance": "lens_appearance",
					"Mounting Method": "mounting_method",
					"Endcap Style": "endcap_style",
					"Endcap Color": "endcap_color",
				}
				field = field_map.get(option_type)
				if field:
					return getattr(row, field, None)
		return None
