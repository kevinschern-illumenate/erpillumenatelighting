# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ilLCADImport(Document):
	"""A drawing package imported into a schedule (draw-to-quote plan 2.2). Service-owned: the portal
	drawing import writes it, and only its ``status`` changes later (a newer import supersedes it)."""

	def validate(self):
		if not self.flags.cad_import_service_write:
			frappe.throw("Drawing imports are written by the drawing import only")

	def on_trash(self):
		if not self.flags.cad_import_service_write:
			frappe.throw("Drawing imports are kept as the schedule's drawing history")
