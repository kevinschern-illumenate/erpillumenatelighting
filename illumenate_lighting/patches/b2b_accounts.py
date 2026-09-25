"""Add account lifecycle metadata without changing existing memberships."""


def execute():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Contact": [
				{
					"fieldname": "ill_portal_contact_only",
					"fieldtype": "Check",
					"label": "Contact Only (No Portal Membership)",
					"default": "0",
					"read_only": 1,
				},
				{
					"fieldname": "ill_portal_archived",
					"fieldtype": "Check",
					"label": "Archived for Portal",
					"default": "0",
				},
			],
			"Customer": [
				{
					"fieldname": "ill_purchasing_contact",
					"fieldtype": "Link",
					"options": "Contact",
					"label": "Portal Purchasing Contact",
				}
			],
		},
		update=True,
	)
