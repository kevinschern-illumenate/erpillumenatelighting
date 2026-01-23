# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLChildDriverInputProtocol(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		is_default: DF.Check
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		protocol: DF.Link | None
	# end: auto-generated types

	pass
