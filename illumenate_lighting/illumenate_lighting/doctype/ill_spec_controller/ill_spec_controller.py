# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLSpecController(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_controller_protocol.ill_child_controller_protocol import ilLChildControllerProtocol
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_wireless_protocol.ill_child_wireless_protocol import ilLChildWirelessProtocol
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_compatible_driver.ill_child_compatible_driver import ilLChildCompatibleDriver

		channels: DF.Int
		compatible_drivers: DF.Table[ilLChildCompatibleDriver]
		controller_name: DF.Data | None
		controller_type: DF.Literal["DMX Controller", "Wireless Receiver", "Wall Dimmer", "Scene Controller", "Sensor", "Gateway", "Repeater"]
		depth_mm: DF.Float
		height_mm: DF.Float
		input_protocols: DF.Table[ilLChildControllerProtocol]
		input_voltage_max: DF.Int
		input_voltage_min: DF.Int
		input_voltage_type: DF.Literal["VAC", "VDC"]
		is_active: DF.Check
		item: DF.Link
		max_load_amps: DF.Float
		max_load_watts: DF.Float
		mounting_type: DF.Literal["Wall Mount", "In-Wall", "Surface", "DIN Rail", "Portable"]
		notes: DF.SmallText | None
		output_protocols: DF.Table[ilLChildControllerProtocol]
		standby_power_watts: DF.Float
		weight_grams: DF.Float
		width_mm: DF.Float
		wireless_protocols: DF.Table[ilLChildWirelessProtocol]
		zones: DF.Int
	# end: auto-generated types

	pass
