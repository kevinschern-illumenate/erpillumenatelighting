# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLChildTapeNeonSegment(Document):
	"""Child table for neon segments within a configured tape/neon product.

	Each row represents one neon segment with its own IP rating, feed directions,
	cable lengths, and computed lengths. LED Tape fixtures have a single segment;
	LED Neon can have multiple segments connected by jumper cables.
	"""
	pass
