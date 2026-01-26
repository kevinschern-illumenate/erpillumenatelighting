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
		last_synced_at: DF.Datetime | None
		parent_category: DF.Link | None
		sync_status: DF.Literal["Pending", "Synced", "Error", "Never Synced"]
		webflow_item_id: DF.Data | None
	# end: auto-generated types

	pass
