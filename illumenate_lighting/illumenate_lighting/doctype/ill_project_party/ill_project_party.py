# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.portal import project_parties


class ilLProjectParty(Document):
	"""A dealer's end client, architect, lighting designer or contractor (DESK-9)."""

	def validate(self):
		self.party_name = project_parties.clean_name(self.party_name)
		if not self.party_name:
			frappe.throw(_("Name is required."))
		duplicate = frappe.db.get_value(
			"ilL-Project-Party",
			{
				"owner_customer": self.owner_customer,
				"role": self.role,
				"party_name": self.party_name,
				"name": ["!=", self.name or ""],
			},
			"name",
		)
		if duplicate:
			frappe.throw(
				_("{0} already has a {1} named {2} ({3}).").format(
					self.owner_customer, _(self.role), self.party_name, duplicate
				),
				frappe.DuplicateEntryError,
			)
		previous = None if self.is_new() else self.get_doc_before_save()
		if previous and previous.owner_customer != self.owner_customer:
			frappe.throw(_("A party stays with the dealer company that created it."))
