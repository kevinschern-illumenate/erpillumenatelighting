# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ilLWebflowBrand(Document):
	def validate(self):
		# Enforce at most one is_default=1 row
		if self.is_default:
			others = frappe.get_all(
				"ilL-Webflow-Brand",
				filters={"is_default": 1, "name": ["!=", self.name]},
				pluck="name",
			)
			for other in others:
				frappe.db.set_value(
					"ilL-Webflow-Brand", other, "is_default", 0, update_modified=False
				)

	def on_update(self):
		# Invalidate the brand cache so changes take effect immediately
		try:
			from illumenate_lighting.illumenate_lighting.api import webflow_brand
			webflow_brand.clear_brand_cache()
		except Exception:
			# Cache module may not be loaded yet (during migrations)
			pass
