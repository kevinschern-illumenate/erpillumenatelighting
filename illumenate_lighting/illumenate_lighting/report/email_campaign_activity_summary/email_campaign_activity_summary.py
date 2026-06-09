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
EMAIL_ACTIVITY_LOG_FIELD = "custom_email_activity_log"


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
            "label": _("Launch Date"),
            "fieldname": "launch_date",
            "fieldtype": "Date",
            "width": 140,
        },
        {
            "label": _("Delivery Count"),
            "fieldname": "delivery_count",
            "fieldtype": "Int",
            "width": 120,
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
        {
            "label": _("Click Rate (%)"),
            "fieldname": "click_rate",
            "fieldtype": "Percent",
            "width": 120,
        },
        {
            "label": _("CTR (%)"),
            "fieldname": "ctr",
            "fieldtype": "Percent",
            "width": 120,
        },
        {
            "label": _("Open Rate Variance"),
            "fieldname": "open_rate_variance",
            "fieldtype": "Percent",
            "width": 150,
        },
        {
            "label": _("Click Rate Variance"),
            "fieldname": "click_rate_variance",
            "fieldtype": "Percent",
            "width": 150,
        },
        {
            "label": _("CTR Variance"),
            "fieldname": "ctr_variance",
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
                "launch_date": None,
                "open_rate": 0,
                "click_rate": 0,
                "ctr": 0,
            },
        )
        template_summary[template][metric_field] += cint(row.get("activity_count"))
        
        # Track earliest activity date as launch date
        activity_date = row.get("activity_date")
        if activity_date:
            if template_summary[template]["launch_date"] is None:
                template_summary[template]["launch_date"] = activity_date
            else:
                template_summary[template]["launch_date"] = min(
                    template_summary[template]["launch_date"],
                    activity_date
                )

    # Get benchmarks
    benchmarks = get_benchmarks()

    data = []
    totals = {
        "delivery_count": 0,
        "open_count": 0,
        "click_count": 0,
    }
    
    for template in sorted(template_summary):
        summary = template_summary[template]
        delivered = summary["delivery_count"]
        opened = summary["open_count"]
        clicked = summary["click_count"]
        
        # Calculate rates
        summary["open_rate"] = round((opened / delivered) * 100, 2) if delivered > 0 else 0
        summary["click_rate"] = round((clicked / delivered) * 100, 2) if delivered > 0 else 0
        summary["ctr"] = round((clicked / opened) * 100, 2) if opened > 0 else 0
        
        # Calculate variance
        summary["open_rate_variance"] = round(summary["open_rate"] - benchmarks["open_rate"], 2)
        summary["click_rate_variance"] = round(summary["click_rate"] - benchmarks["click_rate"], 2)
        summary["ctr_variance"] = round(summary["ctr"] - benchmarks["ctr"], 2)
        
        # Track totals for average row
        totals["delivery_count"] += delivered
        totals["open_count"] += opened
        totals["click_count"] += clicked
        
        data.append(summary)

    # Add TOTAL/AVERAGE row
    if data:
        total_delivered = totals["delivery_count"]
        total_opened = totals["open_count"]
        total_clicked = totals["click_count"]
        
        avg_open_rate = round((total_opened / total_delivered) * 100, 2) if total_delivered > 0 else 0
        avg_click_rate = round((total_clicked / total_delivered) * 100, 2) if total_delivered > 0 else 0
        avg_ctr = round((total_clicked / total_opened) * 100, 2) if total_opened > 0 else 0
        
        average_row = {
            "email_template": "TOTAL/AVERAGE",
            "launch_date": None,
            "delivery_count": total_delivered,
            "open_count": total_opened,
            "click_count": total_clicked,
            "open_rate": avg_open_rate,
            "click_rate": avg_click_rate,
            "ctr": avg_ctr,
            "open_rate_variance": round(avg_open_rate - benchmarks["open_rate"], 2),
            "click_rate_variance": round(avg_click_rate - benchmarks["click_rate"], 2),
            "ctr_variance": round(avg_ctr - benchmarks["ctr"], 2),
        }
        data.append(average_row)

    return data


def get_benchmarks():
    """Get email campaign benchmarks from settings"""
    try:
        settings = frappe.get_doc("Email Campaign Benchmark Settings")
        return {
            "open_rate": settings.open_rate_benchmark or 0,
            "click_rate": settings.click_rate_benchmark or 0,
            "ctr": settings.ctr_benchmark or 0,
        }
    except frappe.DoesNotExistError:
        # Return default benchmarks if settings don't exist
        return {
            "open_rate": 20.0,
            "click_rate": 2.0,
            "ctr": 10.0,
        }


def get_activity_counts(filters):
    email_activity_doctype = get_email_activity_log_doctype()
    if not email_activity_doctype or not frappe.db.exists("DocType", email_activity_doctype):
        return []

    activity_log = frappe.qb.DocType(email_activity_doctype)
    crm_lead = frappe.qb.DocType(CRM_LEAD_DOCTYPE)
    
    query = (
        frappe.qb.from_(activity_log)
        .join(crm_lead).on(activity_log.parent == crm_lead.name)
        .select(
            activity_log.email_template,
            activity_log.activity_type,
            activity_log.activity_date,
            Count("*").as_("activity_count"),
        )
        .where(activity_log.parenttype == CRM_LEAD_DOCTYPE)
        .where(activity_log.parentfield == EMAIL_ACTIVITY_LOG_FIELD)
        .where(activity_log.activity_type.isnotnull())
        .where(~crm_lead.email.like("%@illumenate.lighting"))
        .groupby(activity_log.email_template, activity_log.activity_type, activity_log.activity_date)
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
