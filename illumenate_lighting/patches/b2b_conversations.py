"""Additive conversation routing metadata."""

import frappe


def execute():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	fields = {}
	for doctype in ("Issue", "ilL-Document-Request"):
		fields[doctype] = [
			{
				"fieldname": "ill_next_action_by",
				"fieldtype": "Select",
				"label": "Next Action By",
				"options": "Staff\nCustomer\nNone",
				"default": "Staff",
				"read_only": 1,
			}
		]
	fields["Issue"].extend(
		[
			{
				"fieldname": "ill_support_owner",
				"fieldtype": "Link",
				"options": "User",
				"label": "Portal Support Owner",
			},
			{"fieldname": "ill_support_due", "fieldtype": "Datetime", "label": "Portal Response Due"},
		]
	)
	fields["ilL-Document-Request"].extend(
		[
			{
				"fieldname": "ill_observed_build_hash",
				"fieldtype": "Data",
				"label": "Observed Build",
				"hidden": 1,
				"read_only": 1,
			},
			{
				"fieldname": "ill_review_state",
				"fieldtype": "Select",
				"label": "Drawing Review",
				"read_only": 1,
				"options": "Awaiting drawing\nAwaiting approval\nChanges requested\nApproved\nReapproval required",
			},
			{
				"fieldname": "ill_impact_task",
				"fieldtype": "Link",
				"options": "Task",
				"label": "Engineering Review Task",
				"read_only": 1,
			},
		]
	)
	fields["Task"] = [
		{
			"fieldname": "ill_drawing_impact_key",
			"fieldtype": "Data",
			"label": "Drawing Impact Key",
			"unique": 1,
			"hidden": 1,
			"read_only": 1,
		},
		{
			"fieldname": "ill_drawing_request",
			"fieldtype": "Link",
			"options": "ilL-Document-Request",
			"label": "Drawing Request",
			"read_only": 1,
		},
	]
	create_custom_fields(fields, update=True)
	frappe.db.add_index(
		"ilL-Portal-Message",
		["reference_type", "reference_name", "visibility", "creation"],
		"ill_conversation",
	)
	frappe.db.add_index("Issue", ["raised_by", "status", "creation"], "ill_support_list")
	frappe.db.add_index("ilL-Portal-Delivery", ["state", "modified"], "ill_delivery_queue")
	from illumenate_lighting.portal_staff_permissions import apply_service_permissions

	apply_service_permissions()
