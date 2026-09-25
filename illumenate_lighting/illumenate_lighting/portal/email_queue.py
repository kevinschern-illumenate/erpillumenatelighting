"""Limit portal emails at native send time; unrelated email keeps native behavior."""

from frappe.email.doctype.email_queue.email_queue import EmailQueue


class PortalEmailQueue(EmailQueue):
	def send(self, *args, **kwargs):
		from illumenate_lighting.illumenate_lighting.portal.outbox import before_send

		if before_send(self):
			return super().send(*args, **kwargs)
