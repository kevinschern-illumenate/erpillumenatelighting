# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Stage, Waiting On, Stage Detail and Stage Override on Sales Orders and Quotations.

Stage Override replaces the Sales Order's Production Status Override: its values
(Paint, Held, Waiting for parts) are stages of the same name, so they are copied
across before the old field is removed. Then every document gets its stage
(api/order_stage.py); a failure there is logged and the cron sweep fills it in.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from illumenate_lighting.illumenate_lighting.api import order_stage

OLD_OVERRIDE = "ill_production_status_override"
# A cancelled document, a completed order and a won quote ignore the override.
NOT_OVERRIDABLE = {"Completed", "Cancelled", "Won"}


def _after(doctype, preferred):
	meta = frappe.get_meta(doctype)
	return preferred if meta.has_field(preferred) else meta.fields[-1].fieldname


def _fields(doctype, after):
	stages = [s for s, _w, _c in order_stage.STAGES[doctype]]
	return [
		{
			"fieldname": order_stage.STAGE,
			"fieldtype": "Select",
			"label": "Stage",
			"options": "\n" + "\n".join(stages),
			"insert_after": after,
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
			"in_list_view": 1,
			"in_standard_filter": 1,
			"search_index": 1,
			"print_hide": 1,
			"description": "Worked out from work orders, stock, purchases and deliveries. Set Stage Override to change it.",
		},
		{
			"fieldname": order_stage.WAITING,
			"fieldtype": "Select",
			"label": "Waiting On",
			"options": "\n".join(order_stage.WAITING_OPTIONS),
			"insert_after": order_stage.STAGE,
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
			"in_standard_filter": 1,
			"print_hide": 1,
		},
		{
			"fieldname": order_stage.NOTE,
			"fieldtype": "Data",
			"label": "Stage Detail",
			"insert_after": order_stage.WAITING,
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
			"print_hide": 1,
		},
		{
			"fieldname": order_stage.OVERRIDE,
			"fieldtype": "Select",
			"label": "Stage Override",
			"options": "\n" + "\n".join(s for s in stages if s not in NOT_OVERRIDABLE),
			"insert_after": order_stage.NOTE,
			"allow_on_submit": 1,
			"no_copy": 1,
			"print_hide": 1,
			"description": "Leave blank to let the stage follow the order. Wins until cleared.",
		},
	]


def execute():
	quote_fields = _fields("Quotation", _after("Quotation", "valid_till"))
	quote_fields.append(
		{
			"fieldname": order_stage.SENT_ON,
			"fieldtype": "Date",
			"label": "Quote Sent On",
			"insert_after": order_stage.OVERRIDE,
			"read_only": 1,
			"hidden": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
			"print_hide": 1,
		}
	)
	create_custom_fields(
		{
			"Sales Order": _fields("Sales Order", _after("Sales Order", "delivery_date")),
			"Quotation": quote_fields,
		},
		update=True,
	)
	move_old_override()
	try:
		order_stage.refresh_all()
	except Exception:
		frappe.log_error(title="Order stage backfill failed", message=frappe.get_traceback())


def move_old_override():
	if not frappe.db.has_column("Sales Order", OLD_OVERRIDE):
		return
	frappe.db.sql(
		f"""update `tabSales Order` set `{order_stage.OVERRIDE}` = `{OLD_OVERRIDE}`
		where ifnull(`{OLD_OVERRIDE}`, '') != '' and ifnull(`{order_stage.OVERRIDE}`, '') = ''"""
	)
	name = frappe.db.get_value("Custom Field", {"dt": "Sales Order", "fieldname": OLD_OVERRIDE})
	if name:
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
