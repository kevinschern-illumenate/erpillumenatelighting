"""Add group references without rewriting any historical configured records."""


def execute():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			doctype: [
				{
					"fieldname": "ill_configured_group",
					"fieldtype": "Link",
					"options": "ilL-Configured-Group",
					"label": "Configured Group",
					"read_only": 1,
				}
			]
			for doctype in ("Quotation Item", "Sales Order Item", "Work Order")
		},
		update=True,
	)
