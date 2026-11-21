# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLConfigurationPreset(Document):
	def validate(self):
		# Desk edits get the same drawing-code rules as the portal (draw-to-quote WP 1.2).
		from illumenate_lighting.illumenate_lighting.portal import presets

		self.cad_code = presets.normalize_cad_code(self.get("cad_code"))
		presets._require_unique_code(self.cad_code, self.get("customer"), self.get("user"), self.name)
