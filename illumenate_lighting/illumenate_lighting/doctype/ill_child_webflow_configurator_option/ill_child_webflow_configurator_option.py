# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLChildWebflowConfiguratorOption(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		allowed_values_json: DF.JSON | None
		depends_on_step: DF.Int
		is_required: DF.Check
		option_description: DF.SmallText | None
		option_label: DF.Data | None
		option_step: DF.Int
		option_type: DF.Literal["LED Package", "CCT", "Output Level", "Lens Appearance", "Finish", "Mounting Method", "Environment Rating", "Power Feed Type", "Endcap Style", "Endcap Color"]
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	pass
