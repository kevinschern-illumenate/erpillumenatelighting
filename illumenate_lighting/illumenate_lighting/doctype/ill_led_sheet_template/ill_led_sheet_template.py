# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ilLLEDSheetTemplate(Document):
	def validate(self):
		self._validate_allowed_specs()

	def _validate_allowed_specs(self):
		if not self.allowed_specs:
			return
		for row in self.allowed_specs:
			if not row.spec:
				continue
			spec_series = frappe.db.get_value("ilL-Spec-LED-Sheet", row.spec, "sku_series_code")
			if spec_series and self.sku_series_code and spec_series != self.sku_series_code:
				frappe.throw(
					f"Row {row.idx}: LED Sheet Spec '{row.spec}' has series '{spec_series}' "
					f"but this template uses '{self.sku_series_code}'"
				)
