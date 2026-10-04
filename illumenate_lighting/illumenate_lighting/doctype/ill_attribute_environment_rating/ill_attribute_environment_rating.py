# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ilLAttributeEnvironmentRating(Document):
	def on_change(self):
		# LED Sheet templates and Part Number Builders keep a copy of the code that their
		# part numbers carry. on_change runs after the cache is cleared, so they read the new code.
		if not self.has_value_changed("code"):
			return
		from illumenate_lighting.illumenate_lighting.api.environment_codes import propagate

		failed = propagate(self.name)
		if failed:
			frappe.msgprint(
				_("Could not update the {0} code on: {1}. See the Error Log.").format(
					self.name, ", ".join(failed)
				),
				indicator="orange",
			)
