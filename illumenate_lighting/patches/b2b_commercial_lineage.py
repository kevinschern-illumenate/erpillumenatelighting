"""Add downstream configured lineage; do not rewrite historical transactions."""


def execute():
	import frappe
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	from illumenate_lighting.patches.add_quote_order_configurator_fields import _configured_product_fields

	fields = _configured_product_fields("ill_fixture_type")
	fields[0]["options"] = "\nLinear Fixture\nLED Tape\nLED Neon\nLED Sheet"
	fields.extend(
		[
			{
				"fieldname": "ill_configured_led_sheet",
				"fieldtype": "Link",
				"label": "Configured LED Sheet",
				"options": "ilL-Configured-LED-Sheet",
				"read_only": 1,
			},
			{
				"fieldname": "ill_configured_group",
				"fieldtype": "Link",
				"label": "Configured Group",
				"options": "ilL-Configured-Group",
				"read_only": 1,
			},
			{
				"fieldname": "ill_fixture_schedule",
				"fieldtype": "Link",
				"label": "Fixture Schedule",
				"options": "ilL-Project-Fixture-Schedule",
				"read_only": 1,
			},
			{
				"fieldname": "ill_schedule_line_id",
				"fieldtype": "Data",
				"label": "Schedule Line ID",
				"read_only": 1,
			},
			{
				"fieldname": "ill_section_label",
				"fieldtype": "Data",
				"label": "Section / Room",
				"read_only": 1,
			},
			{"fieldname": "ill_fixture_type", "fieldtype": "Data", "label": "Fixture Type", "read_only": 1},
			{
				"fieldname": "ill_configurator_request",
				"fieldtype": "Long Text",
				"label": "Engineering Request",
				"read_only": 1,
				"hidden": 1,
			},
		]
	)
	create_custom_fields(
		{doctype: fields for doctype in ("Delivery Note Item", "Sales Invoice Item")}, update=True
	)
	# Older sites may already own this field. Preserve their type and settings.
	create_custom_fields(
		{
			doctype: [
				{"fieldname": "additional_notes", "fieldtype": "Small Text", "label": "Additional Notes"}
			]
			for doctype in ("Quotation Item", "Sales Order Item", "Delivery Note Item", "Sales Invoice Item")
			if not frappe.get_meta(doctype).has_field("additional_notes")
		}
	)
	if not frappe.db.exists("Print Format", "ilL Delivery Note"):
		from pathlib import Path

		frappe.get_doc(
			{
				"doctype": "Print Format",
				"name": "ilL Delivery Note",
				"doc_type": "Delivery Note",
				"module": "ilLumenate Lighting",
				"standard": "No",
				"custom_format": 1,
				"print_format_type": "Jinja",
				"html": Path(
					frappe.get_app_path(
						"illumenate_lighting", "templates", "print_formats", "delivery_note.html"
					)
				).read_text(encoding="utf-8"),
			}
		).insert(ignore_permissions=True)
