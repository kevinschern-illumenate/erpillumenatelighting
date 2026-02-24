# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document

MM_PER_INCH = 25.4


def _format_dimension(mm):
	"""Format a single dimension as xx.xx" (xx.xxmm)."""
	inches = mm / MM_PER_INCH
	return f'{inches:.2f}" ({mm:.2f}mm)'


class ilLSpecProfile(Document):
	def before_save(self):
		"""Calculate combined dimensions before saving."""
		self._calculate_dimensions()
	
	def _calculate_dimensions(self):
		"""Combine width and height into a dimensions string."""
		width = self.width_mm or 0
		height = self.height_mm or 0
		
		if width and height:
			self.dimensions = f"{_format_dimension(width)} x {_format_dimension(height)}"
		elif width:
			self.dimensions = f"{_format_dimension(width)} (W)"
		elif height:
			self.dimensions = f"{_format_dimension(height)} (H)"
		else:
			self.dimensions = ""
