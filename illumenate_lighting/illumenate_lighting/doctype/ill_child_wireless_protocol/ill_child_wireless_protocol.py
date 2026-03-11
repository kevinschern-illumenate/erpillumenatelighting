# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLChildWirelessProtocol(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		protocol: DF.Literal["Bluetooth", "Zigbee", "Z-Wave", "WiFi", "RF 433MHz", "RF 2.4GHz"]
	# end: auto-generated types

	pass
