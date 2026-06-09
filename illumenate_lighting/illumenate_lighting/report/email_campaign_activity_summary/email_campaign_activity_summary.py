import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import cint


ACTIVITY_TYPE_ALIASES = {
    "delivered": "delivery_count",
    "delivery": "delivery_count",
    "opened": "open_count",
    "open": "open_count",
    "clicked": "click_count",
    "click": "click_count",
}

CRM_LEAD_DOCTYPE = "CRM Lead"
EMAIL_ACTIVITY_LOG_FIELD = "email_activity_log"


def execute(filters=None):
    filters = filters or {}
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {
            "label": _("Email Template"),
            "fieldname": "email_template",
            "fieldtype": "Data",
            "width": 240,
        },
        {
            "label": _("Delivery Count"),
            "fieldname": "delivery_count",
            "fieldtype": "Int",
            "width": 140,
        },
        {
            "label": _("Open Count"),
            "fieldname": "open_count",
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "label": _("Click Count"),
            "fieldname": "click_count",
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "label": _("Open Rate (%)"),
            "fieldname": "open_rate",
            "fieldtype": "Percent",
            "width": 120,
        },
    ]


def get_data(filters):
    rows = get_activity_counts(filters)
    template_summary = {}

    for row in rows:
        template = (row.get("email_template") or "").strip() or _("Unknown")
        metric_field = ACTIVITY_TYPE_ALIASES.get((row.get("activity_type") or "").strip().lower())
        if not metric_field:
            continue

        template_summary.setdefault(
            template,
            {
                "email_template": template,
                "delivery_count": 0,
                "open_count": 0,
                "click_count": 0,
                "open_rate": 0,
            },
        )
        template_summary[template][metric_field] += cint(row.get("activity_count"))

    data = []
    for template in sorted(template_summary):
        summary = template_summary[template]
        delivered = summary["delivery_count"]
        opened = summary["open_count"]
        summary["open_rate"] = round((opened / delivered) * 100, 2) if delivered > 0 else 0
        data.append(summary)

    return data


def get_activity_counts(filters):
    email_activity_doctype = get_email_activity_log_doctype()
    if not email_activity_doctype or not frappe.db.exists("DocType", email_activity_doctype):
        return []

    activity_log = frappe.qb.DocType(email_activity_doctype)
    query = (
        frappe.qb.from_(activity_log)
        .select(
            activity_log.email_template,
            activity_log.activity_type,
            Count("*").as_("activity_count"),
        )
        .where(activity_log.parenttype == CRM_LEAD_DOCTYPE)
        .where(activity_log.parentfield == EMAIL_ACTIVITY_LOG_FIELD)
        .where(activity_log.activity_type.isnotnull())
        .groupby(activity_log.email_template, activity_log.activity_type)
    )

    if filters.get("from_date"):
        query = query.where(activity_log.activity_date >= filters["from_date"])
    if filters.get("to_date"):
        query = query.where(activity_log.activity_date <= filters["to_date"])

    return query.run(as_dict=True)


def get_email_activity_log_doctype():
    lead_meta = frappe.get_meta(CRM_LEAD_DOCTYPE)
    email_activity_field = lead_meta.get_field(EMAIL_ACTIVITY_LOG_FIELD)
    if email_activity_field and email_activity_field.options:
        return email_activity_field.options
    return None
