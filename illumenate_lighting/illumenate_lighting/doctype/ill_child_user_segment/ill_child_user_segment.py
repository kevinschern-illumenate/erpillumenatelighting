# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ilLChildUserSegment(Document):
	"""
	Child table for storing user-defined segment configurations.

	Each row represents one segment in a multi-segment fixture configuration.
	The first segment starts with a leader cable, and subsequent segments
	inherit their start from the prior segment's end (jumper cable).
	"""

	pass
