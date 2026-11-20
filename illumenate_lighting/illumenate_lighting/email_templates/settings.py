# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""ilL-Email-Settings with its defaults applied, so an unsaved or not-yet-migrated site still works."""

SETTINGS = "ilL-Email-Settings"

DEFAULTS = {
	"sales_contact_name": "ilLumenate Lighting Sales",
	"sales_contact_email": "sales@illumenate.lighting",
	"sales_contact_phone": "",
	"purchasing_contact_name": "ilLumenate Lighting Purchasing",
	"purchasing_contact_email": "purchasing@illumenate.lighting",
	"purchasing_contact_phone": "",
	# Purchasing mailbox (email_templates/purchasing_mail.py).
	"purchasing_email_account": "",
	"force_purchasing_sender": 1,
	"link_purchasing_replies": 1,
	"pickup_address": "",
	"pickup_hours": "",
	"auto_send_order_confirmation": 0,
	"auto_send_shipped": 0,
	"include_portal_recipients": 0,
	"email_account": "",
	"bcc_email": "",
	"attach_pdf": 1,
	"max_lines": 15,
	"rfq_reply_days": 7,
}

# Blank in the database means "use the default" for these; 0 is a real answer for the checks.
_BLANK_MEANS_DEFAULT = {
	"sales_contact_name",
	"sales_contact_email",
	"purchasing_contact_name",
	"purchasing_contact_email",
	"max_lines",
	"rfq_reply_days",
}


def get_settings():
	"""A dict of every DEFAULTS key. Never raises."""
	import frappe

	values = dict(DEFAULTS)
	try:
		if not frappe.db.exists("DocType", SETTINGS):
			return values
		saved = frappe.get_cached_doc(SETTINGS)
	except Exception:
		return values
	for key in DEFAULTS:
		value = saved.get(key)
		if value in (None, ""):
			continue
		if key in _BLANK_MEANS_DEFAULT and not value:
			continue
		values[key] = value
	return values
