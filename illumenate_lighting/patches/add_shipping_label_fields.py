"""EasyPost label fields on Shipment and Shipment Parcel (shipping plan, phase 2).

Every field is written by the Create Labels / Void Label buttons or by tracker events,
never by hand, so they are read-only, editable after submit and not copied on amend.
Shipment Parcel and Parcel Template get unit labels (in, lb) because the native fields
have no unit. Also creates the shipping integration user for signed tracker events.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from illumenate_lighting.illumenate_lighting.portal.service_users import ensure_service_user

WRITTEN = {"read_only": 1, "allow_on_submit": 1, "no_copy": 1}
UNIT_LABELS = {
	"length": "Length (in)",
	"width": "Width (in)",
	"height": "Height (in)",
	"weight": "Weight (lb)",
}


def execute():
	create_custom_fields(
		{
			"Shipment": [
				{
					"fieldname": "ill_label_status",
					"fieldtype": "Select",
					"label": "Label Status",
					"options": "Not bought\nBought\nVoided\nError",
					"default": "Not bought",
					"insert_after": "tracking_status_info",
					"in_standard_filter": 1,
					**WRITTEN,
				},
				{
					"fieldname": "ill_label_message",
					"fieldtype": "Small Text",
					"label": "Label Message",
					"insert_after": "ill_label_status",
					"depends_on": "eval:doc.ill_label_message",
					**WRITTEN,
				},
				{
					"fieldname": "ill_label_url",
					"fieldtype": "Data",
					"label": "Label PDF",
					"options": "URL",
					"insert_after": "ill_label_message",
					**WRITTEN,
				},
				{
					"fieldname": "ill_easypost_shipment_id",
					"fieldtype": "Data",
					"label": "EasyPost ID",
					"insert_after": "ill_label_url",
					"description": "EasyPost Order id. Needed to buy, void and re-print.",
					**WRITTEN,
				},
			],
			"Shipment Parcel": [
				{
					"fieldname": "ill_special_handling",
					"fieldtype": "Check",
					"label": "Special Handling",
					"insert_after": "count",
					"read_only": 1,
					"no_copy": 1,
					"description": "Over the additional handling or oversize thresholds in ilL-Shipping-Settings.",
				},
				{
					"fieldname": "ill_tracking_number",
					"fieldtype": "Data",
					"label": "Tracking Number",
					"insert_after": "ill_special_handling",
					"in_list_view": 1,
					**WRITTEN,
				},
				{
					"fieldname": "ill_tracking_status",
					"fieldtype": "Data",
					"label": "Tracking Status",
					"insert_after": "ill_tracking_number",
					**WRITTEN,
				},
				{
					"fieldname": "ill_label_url",
					"fieldtype": "Data",
					"label": "Label",
					"options": "URL",
					"insert_after": "ill_tracking_status",
					**WRITTEN,
				},
			],
		},
		update=True,
	)
	for doctype in ("Shipment Parcel", "Shipment Parcel Template"):
		for fieldname, label in UNIT_LABELS.items():
			make_property_setter(
				doctype, fieldname, "label", label, "Data", validate_fields_for_doctype=False
			)
	make_property_setter(
		"Shipment", "total_weight", "label", "Total Weight (lb)", "Data", validate_fields_for_doctype=False
	)
	ensure_service_user("shipping")
	frappe.db.commit()
