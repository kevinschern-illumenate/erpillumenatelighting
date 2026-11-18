"""Show the contact's Phone and Mobile No on the Delivery Note Address & Contact tab.

Sales Order carries contact_phone and contact_mobile; Delivery Note does not show
them. The fields use the same names as on Sales Order, so ERPNext's Sales Order →
Delivery Note mapping copies them and picking a Contact Person fills them in.
A field ERPNext already defines but hides is made visible instead of duplicated.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

FIELDS = [
	{
		"fieldname": "contact_phone",
		"fieldtype": "Data",
		"options": "Phone",
		"label": "Phone",
		"insert_after": "contact_display",
		"read_only": 1,
	},
	{
		"fieldname": "contact_mobile",
		"fieldtype": "Small Text",
		"label": "Mobile No",
		"insert_after": "contact_phone",
		"read_only": 1,
	},
]


def execute():
	meta = frappe.get_meta("Delivery Note", cached=False)
	missing = []
	for field in FIELDS:
		existing = meta.get_field(field["fieldname"])
		if not existing:
			missing.append(field)
		# Standard DocFields have no is_custom_field attribute (only Custom Fields set it).
		elif existing.hidden and not existing.get("is_custom_field"):
			make_property_setter("Delivery Note", field["fieldname"], "hidden", "0", "Check")
	if missing:
		create_custom_fields({"Delivery Note": missing}, update=False)

	# Fill drafts and submitted notes that predate the fields from their Sales Order.
	for fieldname in ("contact_phone", "contact_mobile"):
		frappe.db.sql(
			f"""
			update `tabDelivery Note` dn
			join (
				select dni.parent, max(so.{fieldname}) as value
				from `tabDelivery Note Item` dni
				join `tabSales Order` so on so.name = dni.against_sales_order
				group by dni.parent
			) src on src.parent = dn.name
			set dn.{fieldname} = src.value
			where ifnull(dn.{fieldname}, '') = '' and ifnull(src.value, '') != ''
			"""
		)
	frappe.db.commit()
