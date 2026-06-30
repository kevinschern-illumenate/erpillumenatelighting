# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLSpecLEDSheet(Document):
	def before_save(self):
		width = float(self.sheet_width_ft or 0)
		height = float(self.sheet_height_ft or 0)
		area = width * height
		self.sheet_area_sqft = area
		self.total_sheet_watts = float(self.watts_per_sqft or 0) * area
		self.total_sheet_lumens = float(self.lumens_per_sqft or 0) * area
