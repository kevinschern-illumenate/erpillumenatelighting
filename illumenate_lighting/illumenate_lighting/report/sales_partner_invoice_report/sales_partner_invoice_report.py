import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "label": _("Invoice ID"),
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 180,
        },
        {
            "label": _("Sales Partner"),
            "fieldname": "sales_partner",
            "fieldtype": "Link",
            "options": "Sales Partner",
            "width": 200,
        },
        {
            "label": _("Customer Name"),
            "fieldname": "customer_name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": _("Net Total"),
            "fieldname": "net_total",
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "label": _("Grand Total"),
            "fieldname": "grand_total",
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "label": _("Posting Date"),
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": _("Payment Due Date"),
            "fieldname": "due_date",
            "fieldtype": "Date",
            "width": 140,
        },
        {
            "label": _("Status"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 120,
        },
    ]


def get_data(filters):
    conditions = []
    values = {}

    if filters.get("from_date"):
        conditions.append("posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("sales_partner"):
        conditions.append("sales_partner = %(sales_partner)s")
        values["sales_partner"] = filters["sales_partner"]

    if filters.get("company"):
        conditions.append("company = %(company)s")
        values["company"] = filters["company"]

    status = (filters.get("status") or "").strip()
    if status:
        conditions.append("status = %(status)s")
        values["status"] = status

    # When a specific status is selected, include cancelled/draft invoices if asked.
    if status in ("Draft", "Cancelled"):
        where_clause = "1=1"
    else:
        where_clause = "docstatus = 1"
    if conditions:
        where_clause += " AND " + " AND ".join(conditions)

    return frappe.db.sql(
        """
        SELECT
            name,
            sales_partner,
            customer_name,
            net_total,
            grand_total,
            posting_date,
            due_date,
            status
        FROM
            `tabSales Invoice`
        WHERE
            {where_clause}
        ORDER BY
            posting_date DESC, name DESC
        """.format(where_clause=where_clause),
        values,
        as_dict=True,
    )
