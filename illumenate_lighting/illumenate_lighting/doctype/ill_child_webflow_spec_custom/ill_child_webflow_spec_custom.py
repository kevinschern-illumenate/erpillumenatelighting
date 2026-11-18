# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

# Created on the site in the UI, moved into the app so the template and product
# tables that use it deploy with the code (plan 4.9). Field definitions match the
# site export of 2026-10-31.

from frappe.model.document import Document


class ilLChildWebflowSpecCustom(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		attribute_doctype: DF.Data | None
		attribute_options_json: DF.JSON | None
		display_order: DF.Int
		spec_label: DF.Data | None
		spec_value: DF.SmallText | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	pass
