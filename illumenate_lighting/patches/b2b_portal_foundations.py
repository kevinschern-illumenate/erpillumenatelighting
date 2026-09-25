"""Additive portal foundations; never rewrite commercial history or User types."""

import frappe


def execute():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Item": [
				{
					"fieldname": "ill_cable_assembly_length_mm",
					"fieldtype": "Float",
					"label": "Fixed Cable Assembly Length (mm)",
					"description": "Approved physical length for count-based cable Items. Bulk cable uses its length stock UOM instead.",
				}
			],
			"Quotation": [
				{
					"fieldname": "ill_quote_request",
					"fieldtype": "Link",
					"options": "ilL-Quote-Request",
					"label": "Portal Quote Request",
					"insert_after": "ill_fixture_schedule",
				}
			],
			"Sales Order": [
				{
					"fieldname": "ill_quote_offer",
					"fieldtype": "Link",
					"options": "ilL-Quote-Offer",
					"label": "Accepted Portal Offer",
					"read_only": 1,
				},
				{
					"fieldname": "ill_requested_delivery_date",
					"fieldtype": "Date",
					"label": "Buyer Requested Delivery Date",
					"read_only": 1,
				},
			],
			"Issue": [
				{
					"fieldname": "ill_portal_request_key",
					"fieldtype": "Data",
					"label": "Portal Request Key",
					"unique": 1,
					"read_only": 1,
					"hidden": 1,
				},
				{
					"fieldname": "ill_portal_request_hash",
					"fieldtype": "Data",
					"label": "Portal Request Hash",
					"read_only": 1,
					"hidden": 1,
				},
				{
					"fieldname": "ill_portal_order",
					"fieldtype": "Link",
					"options": "Sales Order",
					"label": "Related Portal Order",
					"read_only": 1,
				},
			],
		},
		update=True,
	)
	for role in (
		"ilL Sales Review",
		"ilL Order Approver",
		"ilL Engineering",
		"ilL Catalog Publisher",
		"ilL Integration",
	):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)
	if frappe.db.exists("Role", "Dealer"):
		frappe.db.set_value("Role", "Dealer", "desk_access", 0)
		frappe.clear_cache()
	from illumenate_lighting.portal_staff_permissions import apply_staff_permissions

	apply_staff_permissions()
	frappe.db.add_index("ilL-Quote-Request", ["customer", "state", "creation"], "ill_quote_queue")
	frappe.db.add_index("ilL-Quote-Request", ["schedule", "request_hash"], "ill_quote_scope")

	frappe.db.add_index("ilL-Publish-Job", ["brand", "state", "creation"], "ill_publication_queue")
	frappe.db.add_index("ilL-Product-Publication", ["product", "brand"], "ill_publication_scope")
