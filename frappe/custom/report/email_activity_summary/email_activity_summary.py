import frappe
from frappe import _
from frappe.utils import cint
from frappe.query_builder.functions import Count


ACTIVITY_TYPE_ALIASES = {
	"delivered": "delivered_count",
	"delivery": "delivered_count",
	"open": "opened_count",
	"opened": "opened_count",
	"click": "clicked_count",
	"clicked": "clicked_count",
	"bounce": "bounced_count",
	"bounced": "bounced_count",
	"unsubscribe": "unsubscribed_count",
	"unsubscribed": "unsubscribed_count",
}


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"label": _("Email Template"),
			"fieldname": "email_template",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("Delivered"),
			"fieldname": "delivered_count",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"label": _("Opened"),
			"fieldname": "opened_count",
			"fieldtype": "Int",
			"width": 100,
		},
		{
			"label": _("Open Rate"),
			"fieldname": "open_rate",
			"fieldtype": "Percent",
			"width": 110,
		},
		{
			"label": _("Clicked"),
			"fieldname": "clicked_count",
			"fieldtype": "Int",
			"width": 100,
		},
		{
			"label": _("Click-to-Open Rate"),
			"fieldname": "click_to_open_rate",
			"fieldtype": "Percent",
			"width": 150,
		},
		{
			"label": _("Bounced"),
			"fieldname": "bounced_count",
			"fieldtype": "Int",
			"width": 100,
		},
		{
			"label": _("Bounce Rate"),
			"fieldname": "bounce_rate",
			"fieldtype": "Percent",
			"width": 120,
		},
		{
			"label": _("Unsubscribed"),
			"fieldname": "unsubscribed_count",
			"fieldtype": "Int",
			"width": 130,
		},
	]


def get_data(filters):
	rows = get_activity_counts(filters)
	template_summary = {}

	for row in rows:
		template = (row.get("email_template") or _("Unknown")).strip() or _("Unknown")
		metric_field = get_metric_field(row.get("activity_type"))
		if not metric_field:
			continue

		template_summary.setdefault(
			template,
			{
				"email_template": template,
				"delivered_count": 0,
				"opened_count": 0,
				"clicked_count": 0,
				"bounced_count": 0,
				"unsubscribed_count": 0,
				"open_rate": 0,
				"click_to_open_rate": 0,
				"bounce_rate": 0,
			},
		)
		template_summary[template][metric_field] += cint(row.get("activity_count"))

	data = []
	for template in sorted(template_summary):
		summary = template_summary[template]
		delivered = summary["delivered_count"]
		opened = summary["opened_count"]
		clicked = summary["clicked_count"]
		bounced = summary["bounced_count"]

		summary["open_rate"] = round((opened / delivered) * 100, 2) if delivered else 0
		summary["click_to_open_rate"] = round((clicked / opened) * 100, 2) if opened else 0
		summary["bounce_rate"] = round((bounced / delivered) * 100, 2) if delivered else 0
		data.append(summary)

	return data


def get_activity_counts(filters):
	email_activity_doctype = get_email_activity_log_doctype()
	if not email_activity_doctype:
		return []
	if not frappe.db.exists("DocType", email_activity_doctype):
		return []

	activity_log = frappe.qb.DocType(email_activity_doctype)
	query = (
		frappe.qb.from_(activity_log)
		.select(
			activity_log.email_template,
			activity_log.activity_type,
			Count("*").as_("activity_count"),
		)
		.where(activity_log.parenttype == "CRM Lead")
		.where(activity_log.parentfield == "email_activity_log")
		.where(activity_log.activity_type.isnotnull())
		.groupby(activity_log.email_template, activity_log.activity_type)
	)

	if filters.get("from_date"):
		query = query.where(activity_log.activity_date >= filters["from_date"])
	if filters.get("to_date"):
		query = query.where(activity_log.activity_date <= filters["to_date"])

	return query.run(as_dict=True)


def get_email_activity_log_doctype():
	lead_meta = frappe.get_meta("CRM Lead")
	email_activity_field = lead_meta.get_field("email_activity_log")
	if email_activity_field and email_activity_field.options:
		return email_activity_field.options
	return None


def get_metric_field(activity_type):
	normalized_activity_type = (activity_type or "").strip().lower()
	return ACTIVITY_TYPE_ALIASES.get(normalized_activity_type)
