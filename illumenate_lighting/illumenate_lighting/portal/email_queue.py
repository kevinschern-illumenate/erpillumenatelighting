"""Limit portal emails at native send time; unrelated email keeps native behavior."""

import frappe
from frappe.email.doctype.email_queue.email_queue import EmailQueue


class PortalEmailQueue(EmailQueue):
	def before_insert(self):
		parent = getattr(super(), "before_insert", None)
		if parent:
			parent()
		# Supplier email leaves from the purchasing mailbox, whatever account queued it.
		try:
			from illumenate_lighting.illumenate_lighting.email_templates.purchasing_mail import (
				use_purchasing_account,
			)

			use_purchasing_account(self)
		except Exception:
			# Never block an email over which account sends it.
			frappe.log_error(
				title="Could not send from the purchasing mailbox", message=frappe.get_traceback()
			)
		# Automatic email goes out as "ilLumenate Lighting"; a person's email keeps their name.
		from illumenate_lighting.illumenate_lighting.email_templates.brand import rebrand_sender

		try:
			rebrand_sender(self)
		except Exception:
			# Never block an email over its display name.
			frappe.log_error(title="Could not set the ilLumenate sender name", message=frappe.get_traceback())

	def send(self, *args, **kwargs):
		from illumenate_lighting.illumenate_lighting.portal.outbox import before_send

		if before_send(self):
			return super().send(*args, **kwargs)
