# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from illumenate_lighting.illumenate_lighting.portal.product_finder.definition import current_version


class ilLProductFinderSettings(Document):
	def validate(self):
		if not 1 <= cint(self.results_limit) <= 500:
			frappe.throw(_("Maximum Results must be between 1 and 500."))
		if cint(self.session_expiry_days) < 1:
			frappe.throw(_("Portal Session Expiry must be at least one day."))
		if self.verification_text and "{reasons}" not in self.verification_text:
			frappe.throw(_("Warning Text must include {reasons}, where the items to verify are listed."))
		if cint(self.public_enabled) and not self.public_brands:
			frappe.throw(_("Choose at least one brand for the public quiz."))

	def before_save(self):
		# Banner and warning copy are part of the content the portal caches. Read the stored
		# version: a question may have bumped it since this form was opened.
		self.definition_version = current_version() + 1
