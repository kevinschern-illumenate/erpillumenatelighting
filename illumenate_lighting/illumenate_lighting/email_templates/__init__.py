"""Customer and supplier email templates.

- ``context.ill_email_context``: the values every template prints (Jinja method).
- ``library``: the shipped Email Templates, Helpdesk saved replies and Notifications.
- ``seed``: creates the missing ones on migrate; staff edits are never overwritten.
- ``auto_send``: order confirmation and shipment emails sent after submit, when enabled.
"""
