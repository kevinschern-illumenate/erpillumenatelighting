# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""A waiting automatic push of a Webflow Product to one brand (plan 4.19, sync rebuild step 3).

Rows are written and removed by ``webflow_auto_push`` (product saves and the minute tick); every
field is read-only on the form.
"""

from frappe.model.document import Document


class ilLWebflowAutoPush(Document):
	pass
