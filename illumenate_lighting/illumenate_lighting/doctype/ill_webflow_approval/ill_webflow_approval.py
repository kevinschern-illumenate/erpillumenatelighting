# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""An owner approval for a Webflow restore or archive (plan 4.19).

Rows are written by ``webflow_approvals`` (status change hooks, Approve and Reject); every
field is read-only on the form. Approve and Reject are on the Webflow Product's banner.
"""

from frappe.model.document import Document


class ilLWebflowApproval(Document):
	pass
