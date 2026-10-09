# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.web_listing import validate_web_listing


class ilLLEDSheetTemplate(Document):
	def validate(self):
		validate_web_listing(self)
		from illumenate_lighting.illumenate_lighting.api.environment_codes import sync_sheet_template

		# Environment codes come from the rating (Dry 20 / Damp 54 / Wet 67), not per template.
		sync_sheet_template(self)
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
