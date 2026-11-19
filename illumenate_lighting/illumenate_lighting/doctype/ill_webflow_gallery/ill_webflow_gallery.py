# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.api.gallery_rules import validate_gallery

# Frappe's table_exists takes the doctype name and adds the "tab" prefix itself.
PUBLICATION = "ilL-Gallery-Publication"


class ilLWebflowGallery(Document):
	def validate(self):
		data = self.as_dict()
		data["_old_slug"] = self.get_doc_before_save().slug if self.get_doc_before_save() else None
		errors = validate_gallery(
			data, slug_locked=self._slug_locked(), slug_taken=self._slug_taken()
		)
		if errors:
			frappe.throw("<br>".join(_(message) for message in errors))

	def _slug_taken(self) -> bool:
		if not self.slug:
			return False
		return bool(
			frappe.db.exists("ilL-Webflow-Gallery", {"slug": self.slug, "name": ["!=", self.name]})
		)

	def _slug_locked(self) -> bool:
		"""A slug is locked once any publication of this gallery has been staged."""
		if self.is_new() or not frappe.db.table_exists(PUBLICATION):
			return False
		old = self.get_doc_before_save()
		if not old:
			return False
		return bool(
			frappe.db.exists(
				PUBLICATION,
				{"gallery": old.name, "staged_hash": ["is", "set"]},
			)
		)
