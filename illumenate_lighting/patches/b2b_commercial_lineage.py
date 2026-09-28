"""Install configured lineage throughout the commercial document chain."""

LINE_DOCTYPES = ("Quotation Item", "Sales Order Item", "Delivery Note Item", "Sales Invoice Item")


def execute():
	import frappe
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	from illumenate_lighting.patches.add_configured_variant_fields import _quote_order_power_supply_fields
	from illumenate_lighting.patches.add_quote_order_configurator_fields import _configured_product_fields
	from illumenate_lighting.patches.consolidate_section_label_field import _fixture_schedule_field

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
	# Fresh installs mark historical patches complete without executing them.
	# Declare the whole row contract here, including the source quotation/order
	# rows: a nested legacy fixtures directory does not install these fields.
	# Add missing fields while preserving existing site field settings.
	create_custom_fields({doctype: fields for doctype in LINE_DOCTYPES}, update=False)
	create_custom_fields(
		{
			"Quotation": [_fixture_schedule_field("company")],
			"Sales Order": [_fixture_schedule_field("project")],
			"Quotation Item": _quote_order_power_supply_fields("ill_engine_version"),
			"Sales Order Item": _quote_order_power_supply_fields("ill_engine_version"),
		},
		update=False,
	)
	# Older patches offered only three families. Append missing choices rather
	# than discarding any additional choices maintained on the site.
	for doctype in LINE_DOCTYPES:
		field = frappe.get_meta(doctype).get_field("ill_product_type")
		if field.fieldtype == "Select":
			options = (field.options or "").split("\n")
			missing = [family for family in fields[0]["options"].split("\n") if family and family not in options]
			if missing:
				custom_field = frappe.get_doc("Custom Field", {"dt": doctype, "fieldname": "ill_product_type"})
				custom_field.options = "\n".join([*options, *missing])
				custom_field.save(ignore_permissions=True)
	# Older sites may already own this field. Preserve their type and settings.
	create_custom_fields(
		{
			doctype: [
				{"fieldname": "additional_notes", "fieldtype": "Small Text", "label": "Additional Notes"}
			]
			for doctype in LINE_DOCTYPES
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
