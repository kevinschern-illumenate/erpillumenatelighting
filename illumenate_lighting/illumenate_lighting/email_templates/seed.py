# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Create the shipped Email Templates, Helpdesk saved replies and Notifications on a site.

Only missing records are created. Staff edit the wording on the site, so an existing
record is left alone unless ``overwrite`` is passed (bench console, to restore the
shipped text). Notifications are created disabled: each one is turned on after a test
send. Helpdesk and Frappe CRM are optional apps, so their records are skipped on a site
without them, as is a Notification whose date or value field is missing on the site.

	bench --site <site> execute illumenate_lighting.illumenate_lighting.email_templates.seed.ensure_all
	# restore one template's shipped wording:
	bench --site <site> execute illumenate_lighting.illumenate_lighting.email_templates.seed.restore \\
		--kwargs '{"names": ["ilL - Sales Order - Order confirmation"]}'
"""

import frappe

from illumenate_lighting.illumenate_lighting.email_templates.library import (
	NOTIFICATIONS,
	SAVED_REPLIES,
	TEMPLATES,
	template_name,
)

EMAIL_TEMPLATE = "Email Template"
SAVED_REPLY = "HD Saved Reply"
NOTIFICATION = "Notification"


def ensure_all(overwrite=False):
	"""Create every missing record. Returns {"templates": [...], "saved_replies": [...], "notifications": [...]}."""
	return {
		"templates": ensure_templates(overwrite=overwrite),
		"saved_replies": ensure_saved_replies(overwrite=overwrite),
		"notifications": ensure_notifications(),
	}


def restore(names):
	"""Put the shipped wording back on the named Email Templates / saved replies."""
	if isinstance(names, str):
		names = frappe.parse_json(names) if names.startswith("[") else [names]
	names = set(names)
	return {
		"templates": ensure_templates(overwrite=True, only=names),
		"saved_replies": ensure_saved_replies(overwrite=True, only=names),
	}


def _doctype_exists(doctype):
	return bool(doctype) and bool(frappe.db.exists("DocType", doctype))


def ensure_templates(overwrite=False, only=None):
	created = []
	meta = frappe.get_meta(EMAIL_TEMPLATE)
	for template in TEMPLATES:
		if only and template.name not in only:
			continue
		if template.doctype and not _doctype_exists(template.doctype):
			continue
		exists = frappe.db.exists(EMAIL_TEMPLATE, template.name)
		if exists and not overwrite:
			continue
		doc = frappe.get_doc(EMAIL_TEMPLATE, template.name) if exists else frappe.new_doc(EMAIL_TEMPLATE)
		if not exists:
			doc.name = template.name
		doc.subject = template.subject
		doc.use_html = 1
		doc.response_html = template.body()
		doc.response = ""
		if meta.has_field("reference_doctype"):
			doc.reference_doctype = template.doctype or None
		if meta.has_field("enabled"):
			# Frappe CRM only lists enabled templates.
			doc.enabled = 1
		doc.flags.ignore_permissions = True
		if exists:
			doc.save()
		else:
			doc.insert(set_name=template.name)
		created.append(template.name)
	return created


def ensure_saved_replies(overwrite=False, only=None):
	if not _doctype_exists(SAVED_REPLY):
		return []
	created = []
	for reply in SAVED_REPLIES:
		if only and reply.name not in only:
			continue
		exists = frappe.db.exists(SAVED_REPLY, reply.name)
		if exists and not overwrite:
			continue
		doc = frappe.get_doc(SAVED_REPLY, reply.name) if exists else frappe.new_doc(SAVED_REPLY)
		doc.title = reply.name
		doc.message = reply.body()
		if not exists:
			doc.scope = "Global"
		doc.flags.ignore_permissions = True
		doc.save() if exists else doc.insert()
		created.append(reply.name)
	return created


def ensure_notifications():
	"""Create each missing Notification, disabled, pointing at its Email Template."""
	created = []
	for rule in NOTIFICATIONS:
		if frappe.db.exists(NOTIFICATION, rule.name):
			continue
		if not _doctype_exists(rule.document_type):
			continue
		template = template_name(rule.template)
		if not frappe.db.exists(EMAIL_TEMPLATE, template):
			continue
		meta = frappe.get_meta(rule.document_type)
		watched = rule.date_changed or rule.value_changed
		if watched and not meta.has_field(watched):
			continue
		if not meta.has_field(rule.recipient_field):
			continue
		doc = frappe.new_doc(NOTIFICATION)
		doc.name = rule.name
		doc.update(
			{
				"enabled": 0,
				"channel": "Email",
				"document_type": rule.document_type,
				"event": rule.event,
				"condition_type": "Python",
				"condition": rule.condition,
				"email_template": template,
				"recipients": [{"receiver_by_document_field": rule.recipient_field}],
			}
		)
		if rule.event in ("Days After", "Days Before"):
			doc.date_changed = rule.date_changed
			doc.days_in_advance = rule.days_in_advance
		if rule.event == "Value Change":
			doc.value_changed = rule.value_changed
		if rule.attach_print and frappe.db.exists("Print Format", rule.attach_print):
			doc.attach_print = 1
			doc.print_format = rule.attach_print
		doc.flags.ignore_permissions = True
		doc.insert(set_name=rule.name)
		created.append(rule.name)
	return created
