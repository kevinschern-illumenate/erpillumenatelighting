"""Add group references without rewriting any historical configured records."""

# Work Order opens on a tab, so the field needs an anchor inside it. Without one it
# lands above the first tab and Frappe draws an extra "Details" tab to hold it.
_INSERT_AFTER = {"Quotation Item": None, "Sales Order Item": None, "Work Order": "sales_order"}


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
					**({"insert_after": anchor} if anchor else {}),
				}
			]
			for doctype, anchor in _INSERT_AFTER.items()
		},
		update=True,
	)
