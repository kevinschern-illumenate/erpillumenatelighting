"""Trace a retried Desk build to the existing unsaved or persisted ERP row."""


def execute():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			doctype: [
				{
					"fieldname": "ill_configurator_request",
					"fieldtype": "Code",
					"label": "Engineering Request",
					"hidden": 1,
					"read_only": 1,
				},
				{
					"fieldname": "ill_configuration_save_key",
					"fieldtype": "Data",
					"label": "Configuration Save Key",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
				},
			]
			for doctype in ("Quotation Item", "Sales Order Item")
		},
		update=True,
	)
