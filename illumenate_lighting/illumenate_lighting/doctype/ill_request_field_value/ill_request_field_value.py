# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLRequestFieldValue(Document):
	def get_value(self):
		"""Get the appropriate value based on what's stored."""
		if self.value_text:
			return self.value_text
		if self.value_long_text:
			return self.value_long_text
		if self.value_int is not None:
			return self.value_int
		if self.value_float is not None:
			return self.value_float
		if self.value_date:
			return self.value_date
		if self.value_check:
			return self.value_check
		if self.value_link_name:
			return self.value_link_name
		if self.value_json:
			import json
			try:
				return json.loads(self.value_json)
			except Exception:
				return self.value_json
		return None
