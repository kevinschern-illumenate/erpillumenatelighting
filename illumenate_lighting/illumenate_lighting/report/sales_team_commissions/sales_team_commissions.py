# Copyright (c) ilLumenate Lighting and contributors
# For license information, please see license.txt
"""Sales Team Commissions report.

Summarises Sales Invoice activity for the configured period, grouped by
Sales Person (from the invoice's Sales Team child table).

Default behaviour mirrors the most common use-case: show *Paid* invoices
from the previous calendar month so commissions can be reconciled.
The "Payment Status" filter can be toggled to ``Due`` (Unpaid /
Overdue / Partly Paid) or ``All`` to inspect the other slices.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt


PAID_STATUSES = ("Paid", "Credit Note Issued")
DUE_STATUSES = ("Unpaid", "Overdue", "Partly Paid")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	rows = get_data(filters)

	group_by = filters.get("group_by_sales_person", 1)
	if group_by:
		rows, chart = build_grouped_output(rows)
	else:
		chart = build_chart(rows)

	report_summary = build_summary(rows)
	return columns, rows, None, chart, report_summary


def get_columns():
	return [
		{
			"label": _("Sales Person"),
			"fieldname": "sales_person",
			"fieldtype": "Link",
			"options": "Sales Person",
			"width": 220,
		},
		{
			"label": _("Invoice"),
			"fieldname": "invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 170,
		},
		{
			"label": _("Posting Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 200,
		},
		{
			"label": _("Status"),
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Allocated %"),
			"fieldname": "allocated_percentage",
			"fieldtype": "Percent",
			"width": 110,
		},
		{
			"label": _("Invoice Net Total"),
			"fieldname": "net_total",
			"fieldtype": "Currency",
			"width": 140,
		},
		{
			"label": _("Invoice Grand Total"),
			"fieldname": "grand_total",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"label": _("Allocated Amount"),
			"fieldname": "allocated_amount",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"label": _("Commission Rate %"),
			"fieldname": "commission_rate",
			"fieldtype": "Percent",
			"width": 130,
		},
		{
			"label": _("Commission / Incentive"),
			"fieldname": "incentives",
			"fieldtype": "Currency",
			"width": 170,
		},
		{
			"label": _("Outstanding"),
			"fieldname": "outstanding_amount",
			"fieldtype": "Currency",
			"width": 130,
		},
	]


def get_data(filters):
	conditions = ["si.docstatus = 1"]
	values = {
		"from_date": filters.get("from_date"),
		"to_date": filters.get("to_date"),
	}

	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")
	if filters.get("company"):
		conditions.append("si.company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("customer"):
		conditions.append("si.customer = %(customer)s")
		values["customer"] = filters["customer"]
	if filters.get("sales_person"):
		conditions.append("st.sales_person = %(sales_person)s")
		values["sales_person"] = filters["sales_person"]

	payment_status = (filters.get("payment_status") or "Paid").strip()
	if payment_status == "Paid":
		placeholders = ", ".join([f"%(_ps_{i})s" for i in range(len(PAID_STATUSES))])
		conditions.append(f"si.status IN ({placeholders})")
		for i, value in enumerate(PAID_STATUSES):
			values[f"_ps_{i}"] = value
	elif payment_status == "Due":
		placeholders = ", ".join([f"%(_ds_{i})s" for i in range(len(DUE_STATUSES))])
		conditions.append(f"si.status IN ({placeholders})")
		for i, value in enumerate(DUE_STATUSES):
			values[f"_ds_{i}"] = value
	# "All" → no status filter

	where_clause = " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			st.sales_person          AS sales_person,
			si.name                  AS invoice,
			si.posting_date          AS posting_date,
			si.customer              AS customer,
			si.status                AS status,
			st.allocated_percentage  AS allocated_percentage,
			si.net_total             AS net_total,
			si.grand_total           AS grand_total,
			st.allocated_amount      AS allocated_amount,
			st.commission_rate       AS commission_rate,
			st.incentives            AS incentives,
			si.outstanding_amount    AS outstanding_amount
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Team` st
			ON st.parent = si.name
			AND st.parenttype = 'Sales Invoice'
		WHERE {where_clause}
		ORDER BY st.sales_person ASC, si.posting_date DESC, si.name DESC
		""",
		values,
		as_dict=True,
	)
	return rows


def build_grouped_output(rows):
	"""Insert subtotal/group-header rows for each Sales Person."""
	groups = defaultdict(list)
	for row in rows:
		groups[row.get("sales_person") or _("(No Sales Person)")].append(row)

	output = []
	chart_labels = []
	chart_alloc = []
	chart_comm = []

	for sales_person in sorted(groups.keys()):
		group_rows = groups[sales_person]
		alloc_total = sum(flt(r.get("allocated_amount")) for r in group_rows)
		incentive_total = sum(flt(r.get("incentives")) for r in group_rows)
		grand_total = sum(flt(r.get("grand_total")) for r in group_rows)
		outstanding_total = sum(flt(r.get("outstanding_amount")) for r in group_rows)

		output.append(
			{
				"sales_person": sales_person,
				"invoice": _("{0} invoice(s)").format(len(group_rows)),
				"grand_total": grand_total,
				"allocated_amount": alloc_total,
				"incentives": incentive_total,
				"outstanding_amount": outstanding_total,
				"_is_group_header": 1,
			}
		)
		output.extend(group_rows)

		chart_labels.append(sales_person)
		chart_alloc.append(alloc_total)
		chart_comm.append(incentive_total)

	chart = None
	if chart_labels:
		chart = {
			"data": {
				"labels": chart_labels,
				"datasets": [
					{"name": _("Allocated Amount"), "values": chart_alloc},
					{"name": _("Commission / Incentive"), "values": chart_comm},
				],
			},
			"type": "bar",
			"colors": ["#5e64ff", "#ffa00a"],
			"barOptions": {"stacked": 0},
		}
	return output, chart


def build_chart(rows):
	if not rows:
		return None
	by_person = defaultdict(lambda: {"alloc": 0.0, "comm": 0.0})
	for row in rows:
		key = row.get("sales_person") or _("(No Sales Person)")
		by_person[key]["alloc"] += flt(row.get("allocated_amount"))
		by_person[key]["comm"] += flt(row.get("incentives"))
	labels = list(by_person.keys())
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Allocated Amount"), "values": [by_person[k]["alloc"] for k in labels]},
				{"name": _("Commission / Incentive"), "values": [by_person[k]["comm"] for k in labels]},
			],
		},
		"type": "bar",
		"colors": ["#5e64ff", "#ffa00a"],
	}


def build_summary(rows):
	detail_rows = [r for r in rows if not r.get("_is_group_header")]
	total_alloc = sum(flt(r.get("allocated_amount")) for r in detail_rows)
	total_comm = sum(flt(r.get("incentives")) for r in detail_rows)
	total_grand = sum(flt(r.get("grand_total")) for r in detail_rows)
	total_outstanding = sum(flt(r.get("outstanding_amount")) for r in detail_rows)
	invoice_count = len({r.get("invoice") for r in detail_rows if r.get("invoice")})

	currency = frappe.defaults.get_global_default("currency")
	return [
		{
			"label": _("Invoices"),
			"value": invoice_count,
			"indicator": "blue",
			"datatype": "Int",
		},
		{
			"label": _("Total Invoice Amount"),
			"value": total_grand,
			"indicator": "blue",
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"label": _("Total Allocated"),
			"value": total_alloc,
			"indicator": "green",
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"label": _("Total Commission / Incentive"),
			"value": total_comm,
			"indicator": "orange",
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"label": _("Total Outstanding"),
			"value": total_outstanding,
			"indicator": "red" if total_outstanding else "grey",
			"datatype": "Currency",
			"currency": currency,
		},
	]
