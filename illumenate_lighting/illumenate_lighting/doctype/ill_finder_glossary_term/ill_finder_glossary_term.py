# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.portal.product_finder.content import KEY
from illumenate_lighting.illumenate_lighting.portal.product_finder.definition import content_changed


class ilLFinderGlossaryTerm(Document):
	def validate(self):
		self.term_key = (self.term_key or "").strip()
		if not KEY.match(self.term_key):
			frappe.throw(
				_(
					"Term Key must start with a lowercase letter and use only lowercase letters, numbers and underscores."
				)
			)

	def on_update(self):
		content_changed()

	def on_trash(self):
		content_changed()
