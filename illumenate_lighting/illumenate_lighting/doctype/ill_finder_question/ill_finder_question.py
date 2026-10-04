# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.portal.product_finder.content import (
	QUESTION,
	default_comparison,
	validate_question,
)
from illumenate_lighting.illumenate_lighting.portal.product_finder.definition import content_changed


class ilLFinderQuestion(Document):
	def before_validate(self):
		self.question_key = (self.question_key or "").strip()
		if not self.families:
			self.append("families", {"family": "Any"})
		if self.question_type == "Family chooser":
			self.facet, self.match_mode, self.comparison = "family", "Hard", "Any of"
		if self.facet and not self.comparison:
			self.comparison = default_comparison(self.facet)

	def validate(self):
		others = frappe.get_all(
			QUESTION,
			filters={"name": ["!=", self.name or ""]},
			fields=["name", "sequence", "is_active", "question_type"],
		)
		errors = validate_question(self.as_dict(), others)
		if errors:
			frappe.throw(
				"<br>".join(frappe.utils.escape_html(error) for error in errors), title=_("Fix this question")
			)

	def on_update(self):
		content_changed()

	def on_trash(self):
		content_changed()
