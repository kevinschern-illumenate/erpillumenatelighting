# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

# Created on the site in the UI, moved into the app so the template and product
# tables that use it deploy with the code (plan 4.9). Field definitions match the
# site export of 2026-10-31.

from frappe.model.document import Document


class ilLChildCompPower(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		input_protocol: DF.Data | None
		location_rating: DF.Data | None
		max_wattage: DF.Data | None
		output_count: DF.Data | None
		output_voltage: DF.Data | None
		part_number: DF.Data | None
		voltagefrequency: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	pass
