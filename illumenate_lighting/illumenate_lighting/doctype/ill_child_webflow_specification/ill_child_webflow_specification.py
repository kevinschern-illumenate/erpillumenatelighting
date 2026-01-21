# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLChildWebflowSpecification(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		display_order: DF.Int
		is_calculated: DF.Check
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		show_on_card: DF.Check
		spec_group: DF.Literal["Electrical", "Physical", "Performance", "Optical", "Control", "Environmental"]
		spec_label: DF.Data
		spec_unit: DF.Data | None
		spec_value: DF.Data
	# end: auto-generated types

	pass
