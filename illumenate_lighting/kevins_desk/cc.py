"""Call the Command Center gateway (Server Script API ``ill_cc_gateway``) from app code.

The desk reads pipeline data through the same gateway the Command Center page uses, so the doctypes,
columns, role checks and ERPNext permissions are the gateway's, not a second copy. The call runs in
process, as the current user (the desk owner on the page, or the user set by a scheduled job), via
Frappe's own ``call_whitelisted_function``. The gateway writes its answer to ``frappe.response``; this
adapter takes it from there and leaves the caller's response untouched.
"""

import frappe

GATEWAY = "ill_cc_gateway"


def gateway(action, **params):
	from frappe.utils.safe_exec import call_whitelisted_function

	response = frappe.local.response
	had, previous = "message" in response, response.get("message")
	response.pop("message", None)
	try:
		returned = call_whitelisted_function(GATEWAY, action=action, **params)
		message = response.pop("message", None)
		return message if message is not None else returned
	finally:
		if had:
			response["message"] = previous
