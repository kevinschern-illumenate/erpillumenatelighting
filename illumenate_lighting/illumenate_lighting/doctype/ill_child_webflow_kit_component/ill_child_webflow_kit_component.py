# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLChildWebflowKitComponent(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		component_item: DF.Link
		component_spec_doctype: DF.Literal["", "ilL-Spec-Profile", "ilL-Spec-Lens", "ilL-Spec-Accessory"]
		component_spec_name: DF.DynamicLink | None
		component_type: DF.Literal["Profile", "Lens", "Endcap Set", "Mounting Kit", "Joiner", "Hardware"]
		notes: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		quantity: DF.Int
	# end: auto-generated types

	pass
