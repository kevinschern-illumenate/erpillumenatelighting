# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ilLChildWebflowAttributeLink(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		attribute_doctype: DF.Data
		attribute_name: DF.DynamicLink
		attribute_type: DF.Data
		display_label: DF.Data | None
		display_order: DF.Int
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		webflow_item_id: DF.Data | None
	# end: auto-generated types

	def before_save(self):
		"""Auto-populate display label and webflow_item_id if not set."""
		if not self.display_label and self.attribute_name:
			self.display_label = self.attribute_name
		
		# Try to fetch the webflow_item_id from the linked attribute
		if self.attribute_doctype and self.attribute_name and not self.webflow_item_id:
			try:
				webflow_id = frappe.db.get_value(
					self.attribute_doctype,
					self.attribute_name,
					"webflow_item_id"
				)
				if webflow_id:
					self.webflow_item_id = webflow_id
			except Exception:
				pass  # Field may not exist on all attribute doctypes yet
