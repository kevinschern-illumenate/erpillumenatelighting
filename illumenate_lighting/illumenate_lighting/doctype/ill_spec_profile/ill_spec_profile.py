# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLSpecProfile(Document):
	def before_save(self):
		"""Calculate combined dimensions before saving."""
		self._calculate_dimensions()
	
	def _calculate_dimensions(self):
		"""Combine width and height into a dimensions string."""
		width = self.width_mm or 0
		height = self.height_mm or 0
		
		if width and height:
			# Format as "W x H mm" (e.g., "25.4 x 15.2 mm")
			self.dimensions = f"{width:g} x {height:g} mm"
		elif width:
			self.dimensions = f"{width:g} mm (W)"
		elif height:
			self.dimensions = f"{height:g} mm (H)"
		else:
			self.dimensions = ""
