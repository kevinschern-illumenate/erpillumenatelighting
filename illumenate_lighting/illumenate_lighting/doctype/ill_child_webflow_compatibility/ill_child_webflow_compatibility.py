# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLChildWebflowCompatibility(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		notes: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		related_product: DF.Link
		relationship_type: DF.Literal["Works With", "Requires", "Recommended With", "Replaces", "Alternative To"]
	# end: auto-generated types

	pass
