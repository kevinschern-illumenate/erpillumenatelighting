# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLWebflowCategory(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		category_image: DF.AttachImage | None
		category_name: DF.Data
		category_slug: DF.Data
		description: DF.SmallText | None
		display_order: DF.Int
		is_active: DF.Check
		parent_category: DF.Link | None
	# end: auto-generated types

	pass
