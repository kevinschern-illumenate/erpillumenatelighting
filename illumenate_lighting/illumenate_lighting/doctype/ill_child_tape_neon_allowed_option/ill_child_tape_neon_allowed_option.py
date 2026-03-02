# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLChildTapeNeonAllowedOption(Document):
	"""Child table for allowed configuration options on a Tape-Neon-Template.

	Polymorphic row: the option_type field determines which Link field is relevant.
	Covers all option types for both LED Tape and LED Neon products.
	"""
	pass
