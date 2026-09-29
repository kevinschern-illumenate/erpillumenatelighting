# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Feed directions and leader lengths offered for a product."""

from frappe.model.document import Document


class ilLChildFeedOption(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		code: DF.Data
		display_order: DF.Int
		feed_direction: DF.Link
		is_active: DF.Check
		is_default: DF.Check
		kind: DF.Literal["Direction", "Length"]
		label: DF.Data
		length_ft: DF.Float
		position: DF.Literal["Start", "End"]
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	pass
