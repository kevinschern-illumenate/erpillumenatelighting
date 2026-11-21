"""Configured-build fields for Purchase Order, Request for Quotation, Material Request and Work Order.

The desk "Configure & Add Fixture" dialog now runs on these documents too
(document-only: no fixture schedule). Their rows carry the same build links
as Quotation / Sales Order rows so a configured line can be traced to its
configured record, Item and BOM, and reopened with "Reconfigure Row".
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

PRODUCT_TYPE_OPTIONS = "\nLinear Fixture\nLED Tape\nCOB Tape\nLED Neon\nLED Sheet"


def _row_fields(with_section_label: bool) -> list[dict]:
	fields = []
	anchor = "item_code"
	if with_section_label:
		fields.append(
			{"fieldname": "ill_section_label", "fieldtype": "Data", "label": "Section / Room", "insert_after": anchor}
		)
	anchor = "ill_section_label"
	specs = [
		("ill_fixture_type", "Data", "Fixture Type", None, 0),
		("ill_product_type", "Select", "Configured Product Type", PRODUCT_TYPE_OPTIONS, 1),
		("ill_configured_group", "Link", "Configured Group", "ilL-Configured-Group", 1),
		("ill_configured_fixture", "Link", "Configured Fixture", "ilL-Configured-Fixture", 1),
		("ill_configured_tape_neon", "Link", "Configured Tape/Neon", "ilL-Configured-Tape-Neon", 1),
		("ill_configured_led_sheet", "Link", "Configured LED Sheet", "ilL-Configured-LED-Sheet", 1),
		("ill_configured_product_doctype", "Link", "Configured Product DocType", "DocType", 1),
		("ill_configured_product", "Dynamic Link", "Configured Product", "ill_configured_product_doctype", 1),
		("ill_configured_item", "Link", "Configured Item", "Item", 1),
		("ill_bom", "Link", "Configured BOM", "BOM", 1),
		("ill_template_code", "Data", "Template Code", None, 1),
		("ill_is_power_supply_line", "Check", "Power Supply Line", None, 1),
		("ill_power_supply_for", "Data", "Power Supply For", None, 1),
		("ill_configuration_json", "Long Text", "Configuration JSON", None, 1),
	]
	for fieldname, fieldtype, label, options, read_only in specs:
		field = {
			"fieldname": fieldname,
			"fieldtype": fieldtype,
			"label": label,
			"insert_after": anchor,
			"read_only": read_only,
			"no_copy": 0,
		}
		if options:
			field["options"] = options
		fields.append(field)
		anchor = fieldname
	fields += [
		{
			"fieldname": "ill_configurator_request",
			"fieldtype": "Code",
			"label": "Engineering Request",
			"insert_after": anchor,
			"hidden": 1,
			"read_only": 1,
		},
		{
			"fieldname": "ill_configuration_save_key",
			"fieldtype": "Data",
			"label": "Configuration Save Key",
			"insert_after": "ill_configurator_request",
			"hidden": 1,
			"read_only": 1,
			"no_copy": 1,
		},
	]
	return fields


def _work_order_fields() -> list[dict]:
	# ill_configured_fixture already exists on Work Order (ilLumenate QC section).
	return [
		{
			"fieldname": "ill_product_type",
			"fieldtype": "Select",
			"label": "Configured Product Type",
			"options": PRODUCT_TYPE_OPTIONS,
			"insert_after": "ill_configured_fixture",
			"read_only": 1,
		},
		{
			"fieldname": "ill_configured_tape_neon",
			"fieldtype": "Link",
			"label": "Configured Tape/Neon",
			"options": "ilL-Configured-Tape-Neon",
			"insert_after": "ill_product_type",
			"read_only": 1,
		},
		{
			"fieldname": "ill_configured_led_sheet",
			"fieldtype": "Link",
			"label": "Configured LED Sheet",
			"options": "ilL-Configured-LED-Sheet",
			"insert_after": "ill_configured_tape_neon",
			"read_only": 1,
		},
		{
			"fieldname": "ill_configured_product_doctype",
			"fieldtype": "Link",
			"label": "Configured Product DocType",
			"options": "DocType",
			"insert_after": "ill_configured_led_sheet",
			"read_only": 1,
		},
		{
			"fieldname": "ill_configured_product",
			"fieldtype": "Dynamic Link",
			"label": "Configured Product",
			"options": "ill_configured_product_doctype",
			"insert_after": "ill_configured_product_doctype",
			"read_only": 1,
		},
		{
			"fieldname": "ill_configurator_request",
			"fieldtype": "Code",
			"label": "Engineering Request",
			"insert_after": "ill_configured_product",
			"hidden": 1,
			"read_only": 1,
		},
	]


def execute():
	create_custom_fields(
		{
			# Purchase Order Item already has ill_section_label (fixtures).
			"Purchase Order Item": _row_fields(with_section_label=False),
			"Request for Quotation Item": _row_fields(with_section_label=True),
			"Material Request Item": _row_fields(with_section_label=True),
			"Work Order": _work_order_fields(),
		},
		update=True,
	)
