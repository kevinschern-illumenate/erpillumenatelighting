# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.dealer_applications import page_state


def get_context(context):
	"""FLOW-5: guests and signed-in users without dealer access apply here, no sign-in needed."""
	context.claim_token = frappe.form_dict.get("claim")
	context.update(page_state())
	context.signed_in = frappe.session.user != "Guest"
	context.title = _("Dealer access")
	context.no_cache = 1
