# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""A document logo for one product line."""

from frappe.model.document import Document


class ilLChildBrandLogo(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		is_placeholder: DF.Check
		logo: DF.Attach
		placeholder_note: DF.Data
		spec_line: DF.Literal["SW", "DW", "TW", "FS", "CC", "PS", "OTHER"]
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	pass
