# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ilLPortalRoutingSettings(Document):
	def validate(self):
		seen = set()
		for row in self.routes or []:
			if row.queue in seen:
				frappe.throw(_("Add one row per queue; {0} appears twice.").format(row.queue))
			seen.add(row.queue)
			if (row.sla_hours or 0) < 0:
				frappe.throw(_("SLA hours cannot be negative."))
			if row.default_assignee and frappe.db.get_value("User", row.default_assignee, "user_type") != "System User":
				frappe.throw(_("{0} is not a staff account.").format(row.default_assignee))
