# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ilLRelTapeOffering(Document):
	def validate(self):
		self._validate_unique_matrix()

	def _validate_unique_matrix(self):
		"""Enforce one offering per (tape_spec, cct, output_level) matrix cell.

		The document name is ``format:{tape_spec}-{cct}-{output_level}``, so two
		offerings sharing those three values would collide on the primary key.
		Block the duplicate up front with a clear message instead of surfacing a
		raw database/naming error.
		"""
		if not (self.tape_spec and self.cct and self.output_level):
			return

		duplicate = frappe.db.exists(
			"ilL-Rel-Tape Offering",
			{
				"tape_spec": self.tape_spec,
				"cct": self.cct,
				"output_level": self.output_level,
				"name": ("!=", self.name),
			},
		)
		if duplicate:
			frappe.throw(
				_(
					"A tape offering already exists for tape spec {0}, CCT {1}, "
					"output level {2} ({3}). Each tape_spec × CCT × output_level "
					"combination must be unique."
				).format(self.tape_spec, self.cct, self.output_level, duplicate),
				title=_("Duplicate Tape Offering"),
			)
