# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Draw-to-quote pilot metric: does what ships match what was ordered? (CAD toolkit plan 5.4)

One row per submitted Sales Order made from a schedule: its item lines against the Delivery Note lines
shipped against it, by item code and quantity. A line matches when the delivered quantity equals the
ordered quantity. "Only drawing imports" keeps orders whose schedule (any version) had a drawing
imported, so the toolkit's jobs can be compared with the rest. Measured from ERP data, no survey.
"""

import frappe
from frappe import _

SCHEDULE = "ilL-Project-Fixture-Schedule"
CAD_IMPORT = "ilL-CAD-Import"


def match(ordered, delivered):
	"""``ordered``/``delivered`` map item code → qty. Returns the line comparison for one order."""
	codes = set(ordered) | set(delivered)
	matched = sum(1 for code in ordered if abs((delivered.get(code) or 0) - ordered[code]) < 1e-9)
	short = sorted(code for code in ordered if (delivered.get(code) or 0) < ordered[code] - 1e-9)
	over = sorted(code for code in ordered if (delivered.get(code) or 0) > ordered[code] + 1e-9)
	extra = sorted(code for code in delivered if code not in ordered)
	return {
		"ordered_lines": len(ordered),
		"delivered_lines": len(delivered),
		"matched_lines": matched,
		"match_pct": round(100.0 * matched / len(codes), 1) if codes else None,
		"short": ", ".join(short),
		"over": ", ".join(over),
		"extra": ", ".join(extra),
	}


def _sum(rows, key):
	totals = {}
	for row in rows:
		totals.setdefault(row[key], {})
		totals[row[key]][row["item_code"]] = totals[row[key]].get(row["item_code"], 0) + float(
			row["qty"] or 0
		)
	return totals


def _cad_roots():
	"""Root schedules (version chains) that had a drawing imported."""
	if not frappe.db.exists("DocType", CAD_IMPORT):
		return set()
	schedules = set(frappe.get_all(CAD_IMPORT, pluck="schedule"))
	if not schedules:
		return set()
	rows = frappe.get_all(
		SCHEDULE, filters={"name": ["in", list(schedules)]}, fields=["name", "version_parent"]
	)
	return {row.version_parent or row.name for row in rows}


def execute(filters=None):
	from frappe.utils import add_days, getdate, nowdate

	filters = frappe._dict(filters or {})
	to_date = getdate(filters.get("to_date") or nowdate())
	from_date = getdate(filters.get("from_date") or add_days(to_date, -90))
	if not frappe.get_meta("Sales Order").has_field("ill_fixture_schedule"):
		return get_columns(), []
	conditions = {
		"docstatus": 1,
		"ill_fixture_schedule": ["is", "set"],
		"transaction_date": ["between", [from_date, to_date]],
	}
	if filters.get("customer"):
		conditions["customer"] = filters.customer
	orders = frappe.get_all(
		"Sales Order",
		filters=conditions,
		fields=["name", "customer", "transaction_date", "ill_fixture_schedule", "per_delivered"],
		order_by="transaction_date desc",
	)
	schedules = {row.ill_fixture_schedule for row in orders}
	roots = {}
	if schedules:
		roots = {
			row.name: row.version_parent or row.name
			for row in frappe.get_all(
				SCHEDULE, filters={"name": ["in", list(schedules)]}, fields=["name", "version_parent"]
			)
		}
	cad = _cad_roots()
	only_cad = str(filters.get("only_cad", 1)) in ("1", "True", "true")
	orders = [row for row in orders if not only_cad or roots.get(row.ill_fixture_schedule) in cad]
	if not orders:
		return get_columns(), []
	names = [row.name for row in orders]
	ordered = _sum(
		frappe.get_all(
			"Sales Order Item", filters={"parent": ["in", names]}, fields=["parent", "item_code", "qty"]
		),
		"parent",
	)
	delivered = _sum(
		frappe.get_all(
			"Delivery Note Item",
			filters={"against_sales_order": ["in", names], "docstatus": 1},
			fields=["against_sales_order", "item_code", "qty"],
		),
		"against_sales_order",
	)
	rows = []
	for order in orders:
		row = {
			"sales_order": order.name,
			"customer": order.customer,
			"transaction_date": order.transaction_date,
			"schedule": order.ill_fixture_schedule,
			"drawing_import": roots.get(order.ill_fixture_schedule) in cad,
			"per_delivered": order.per_delivered,
			**match(ordered.get(order.name, {}), delivered.get(order.name, {})),
		}
		rows.append(row)
	return get_columns(), rows, None, None, summary(rows)


def summary(rows):
	shipped = [row for row in rows if row["delivered_lines"]]
	matched = sum(row["matched_lines"] for row in shipped)
	lines = sum(row["ordered_lines"] for row in shipped)
	return [
		{"label": _("Orders shipped"), "value": len(shipped), "datatype": "Int"},
		{
			"label": _("Lines matched"),
			"value": f"{round(100.0 * matched / lines, 1)}%" if lines else "-",
			"indicator": "Green" if lines and matched / lines >= 0.98 else "Orange",
			"datatype": "Data",
		},
	]


def get_columns():
	return [
		{
			"label": _("Sales Order"),
			"fieldname": "sales_order",
			"fieldtype": "Link",
			"options": "Sales Order",
			"width": 150,
		},
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 160,
		},
		{"label": _("Ordered"), "fieldname": "transaction_date", "fieldtype": "Date", "width": 100},
		{
			"label": _("Schedule"),
			"fieldname": "schedule",
			"fieldtype": "Link",
			"options": SCHEDULE,
			"width": 160,
		},
		{"label": _("Drawing"), "fieldname": "drawing_import", "fieldtype": "Check", "width": 80},
		{"label": _("% Delivered"), "fieldname": "per_delivered", "fieldtype": "Percent", "width": 100},
		{"label": _("Order lines"), "fieldname": "ordered_lines", "fieldtype": "Int", "width": 90},
		{"label": _("Shipped lines"), "fieldname": "delivered_lines", "fieldtype": "Int", "width": 100},
		{"label": _("Matched"), "fieldname": "matched_lines", "fieldtype": "Int", "width": 80},
		{"label": _("Match %"), "fieldname": "match_pct", "fieldtype": "Percent", "width": 90},
		{"label": _("Short"), "fieldname": "short", "fieldtype": "Data", "width": 180},
		{"label": _("Over"), "fieldname": "over", "fieldtype": "Data", "width": 140},
		{"label": _("Not ordered"), "fieldname": "extra", "fieldtype": "Data", "width": 160},
	]
