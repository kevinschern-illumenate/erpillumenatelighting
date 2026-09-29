# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Drawings and photos used on spec sheets."""

from frappe.model.document import Document


class ilLChildSpecAsset(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		asset_role: DF.Literal[
			"Hero",
			"Product Photo",
			"Cross Section",
			"Side View",
			"Dimension Drawing",
			"Feed Drawing",
			"Bend Drawing",
			"Accessory Drawing",
		]
		bend_axis: DF.Literal["", "Side", "Top"]
		display_order: DF.Int
		feed_direction: DF.Link
		file: DF.Attach
		is_placeholder: DF.Check
		placeholder_note: DF.Data
		sha256: DF.Data
		title: DF.Data
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	pass
