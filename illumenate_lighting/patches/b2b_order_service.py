"""Add distinct requested/confirmed dates and shipping context; never backfill promises."""


def execute():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Sales Order": [
				{
					"fieldname": "ill_confirmed_delivery_date",
					"fieldtype": "Date",
					"label": "Staff Confirmed Delivery Date",
				},
				{
					"fieldname": "ill_delivery_confirmed_by",
					"fieldtype": "Link",
					"options": "User",
					"label": "Delivery Confirmed By",
					"read_only": 1,
				},
				{
					"fieldname": "ill_delivery_confirmed_on",
					"fieldtype": "Datetime",
					"label": "Delivery Confirmed On",
					"read_only": 1,
				},
				{
					"fieldname": "ill_receiving_instructions",
					"fieldtype": "Small Text",
					"label": "Receiving Instructions",
				},
				{
					"fieldname": "ill_shipping_instructions",
					"fieldtype": "Small Text",
					"label": "Shipping Instructions",
				},
			]
		},
		update=True,
	)
