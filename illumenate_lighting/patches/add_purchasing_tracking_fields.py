# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Purchasing tracking fields for the Command Center purchasing board.

Purchase Order: vendor status, sent / confirmed dates, vendor ack number, estimated
lead time, promised ship date, ETA (the date the board uses), freight mode and notes.
Purchase Order Item: line-level lead time and ETA overrides. All are editable after
submit, because they are tracked while the order is out. Supplier: default lead time,
freight mode, purchasing email and role (goods vendor, forwarder, broker...). Customs
Tariff Number: duty and additional tariff rates used to estimate landed cost.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FREIGHT_MODES = "\nOcean FCL\nOcean LCL\nAir\nCourier\nLTL\nFTL\nVendor delivers\nWill call"
VENDOR_STATUSES = "\nNot sent\nSent\nConfirmed\nIn production\nShipped\nDelivered\nIssue"


def _after(doctype, preferred):
	meta = frappe.get_meta(doctype)
	return preferred if meta.has_field(preferred) else meta.fields[-1].fieldname


def _tracked(field):
	"""Editable after submit, never copied to a duplicate or amendment."""
	field.update(allow_on_submit=1, no_copy=1)
	return field


def execute():
	po = [
		{
			"fieldname": "ill_purchasing_section",
			"fieldtype": "Section Break",
			"label": "Vendor Tracking",
			"collapsible": 1,
			"insert_after": _after("Purchase Order", "schedule_date"),
		},
		_tracked(
			{
				"fieldname": "ill_vendor_status",
				"fieldtype": "Select",
				"label": "Vendor Status",
				"options": VENDOR_STATUSES,
				"default": "Not sent",
				"in_standard_filter": 1,
				"insert_after": "ill_purchasing_section",
			}
		),
		_tracked(
			{
				"fieldname": "ill_sent_on",
				"fieldtype": "Date",
				"label": "Sent to Vendor On",
				"insert_after": "ill_vendor_status",
			}
		),
		_tracked(
			{
				"fieldname": "ill_vendor_confirmed_on",
				"fieldtype": "Date",
				"label": "Vendor Confirmed On",
				"insert_after": "ill_sent_on",
			}
		),
		_tracked(
			{
				"fieldname": "ill_vendor_order_no",
				"fieldtype": "Data",
				"label": "Vendor Order / Ack #",
				"insert_after": "ill_vendor_confirmed_on",
			}
		),
		{
			"fieldname": "ill_purchasing_cb",
			"fieldtype": "Column Break",
			"insert_after": "ill_vendor_order_no",
		},
		_tracked(
			{
				"fieldname": "ill_est_lead_time_days",
				"fieldtype": "Int",
				"label": "Estimated Lead Time (days)",
				"insert_after": "ill_purchasing_cb",
				"description": "Prefilled from the supplier quotation, supplier, item or item group default.",
			}
		),
		_tracked(
			{
				"fieldname": "ill_promised_ship_date",
				"fieldtype": "Date",
				"label": "Vendor Promised Ship Date",
				"insert_after": "ill_est_lead_time_days",
			}
		),
		_tracked(
			{
				"fieldname": "ill_eta",
				"fieldtype": "Date",
				"label": "Estimated Arrival",
				"insert_after": "ill_promised_ship_date",
				"description": "The date the purchasing and production boards use. Prefilled as order date + lead time.",
			}
		),
		_tracked(
			{
				"fieldname": "ill_freight_mode",
				"fieldtype": "Select",
				"label": "Freight Mode",
				"options": FREIGHT_MODES,
				"insert_after": "ill_eta",
			}
		),
		_tracked(
			{
				"fieldname": "ill_purchasing_notes",
				"fieldtype": "Small Text",
				"label": "Purchasing Notes",
				"insert_after": "ill_freight_mode",
			}
		),
	]
	po_item = [
		_tracked(
			{
				"fieldname": "ill_est_lead_time_days",
				"fieldtype": "Int",
				"label": "Estimated Lead Time (days)",
				"insert_after": _after("Purchase Order Item", "schedule_date"),
				"description": "Line override. Blank uses the order's lead time.",
			}
		),
		_tracked(
			{
				"fieldname": "ill_eta",
				"fieldtype": "Date",
				"label": "Line ETA",
				"insert_after": "ill_est_lead_time_days",
				"description": "Blank uses the order's Estimated Arrival.",
			}
		),
	]
	supplier = [
		{
			"fieldname": "ill_purchasing_section",
			"fieldtype": "Section Break",
			"label": "Purchasing Defaults",
			"collapsible": 1,
			"insert_after": _after("Supplier", "supplier_group"),
		},
		{
			"fieldname": "ill_supplier_role",
			"fieldtype": "Select",
			"label": "Supplier Role",
			"options": "\nGoods vendor\nFreight forwarder\nCustoms broker\nCarrier\nOther",
			"in_standard_filter": 1,
			"insert_after": "ill_purchasing_section",
		},
		{
			"fieldname": "ill_default_lead_time_days",
			"fieldtype": "Int",
			"label": "Default Lead Time (days)",
			"insert_after": "ill_supplier_role",
		},
		{
			"fieldname": "ill_purchasing_cb",
			"fieldtype": "Column Break",
			"insert_after": "ill_default_lead_time_days",
		},
		{
			"fieldname": "ill_default_freight_mode",
			"fieldtype": "Select",
			"label": "Default Freight Mode",
			"options": FREIGHT_MODES,
			"insert_after": "ill_purchasing_cb",
		},
		{
			"fieldname": "ill_purchasing_email",
			"fieldtype": "Data",
			"label": "Purchasing Email",
			"options": "Email",
			"insert_after": "ill_default_freight_mode",
			"description": "Where purchase orders and RFQs are sent.",
		},
	]
	tariff = [
		{
			"fieldname": "ill_duty_rate_pct",
			"fieldtype": "Percent",
			"label": "General (MFN) Duty Rate",
			"insert_after": _after("Customs Tariff Number", "description"),
			"description": "Estimate only; the broker's entry summary (7501) is the actual.",
		},
		{
			"fieldname": "ill_additional_tariff_pct",
			"fieldtype": "Percent",
			"label": "Additional Tariffs (Section 301 etc.)",
			"insert_after": "ill_duty_rate_pct",
		},
		{
			"fieldname": "ill_rates_checked_on",
			"fieldtype": "Date",
			"label": "Rates Checked On",
			"insert_after": "ill_additional_tariff_pct",
		},
		{
			"fieldname": "ill_rate_notes",
			"fieldtype": "Small Text",
			"label": "Rate Notes",
			"insert_after": "ill_rates_checked_on",
		},
	]
	fields = {"Purchase Order": po, "Purchase Order Item": po_item, "Supplier": supplier}
	if frappe.db.exists("DocType", "Customs Tariff Number"):
		fields["Customs Tariff Number"] = tariff
	create_custom_fields(fields, update=True)
