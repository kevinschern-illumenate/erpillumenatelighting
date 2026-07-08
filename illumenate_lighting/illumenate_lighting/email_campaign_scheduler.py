import frappe
from frappe.utils import now_datetime
import requests


def _get_webhook_url():
    return frappe.conf.get("n8n_campaign_webhook_url")


def run_scheduled_campaigns():
    webhook_url = _get_webhook_url()
    if not webhook_url:
        frappe.log_error("Missing n8n_campaign_webhook_url in site config", "Campaign Scheduler")
        return

    campaigns = frappe.get_all(
        "Postmark Campaign",
        filters={
            "status": "Scheduled",
            "scheduled_time": ["<=", now_datetime()],
        },
        fields=[
            "name",
            "template_alias",
            "email_group",
            "campaign_name",
            "subject",
            "html_body",
            "text_body",
            "test_recipient",
            "is_test_run",
            "postmark_tag",
        ],
        order_by="scheduled_time asc",
        limit=50,
    )

    for c in campaigns:
        frappe.db.sql(
            """
            UPDATE `tabPostmark Campaign`
            SET status='Processing', modified=NOW()
            WHERE name=%s AND status='Scheduled'
            """,
            (c.name,),
        )

        if frappe.db.rowcount == 0:
            continue

        frappe.db.commit()

        payload = {
            "campaign_docname": c.name,
            "template_alias": c.template_alias,
            "email_group": c.email_group,
            "campaign_name": c.campaign_name,
            "subject": c.subject,
            "html_body": c.html_body,
            "text_body": c.text_body,
            "test_recipient": c.test_recipient,
            "is_test_run": c.is_test_run or 0,
            "postmark_tag": c.postmark_tag,
        }

        try:
            r = requests.post(webhook_url, json=payload, timeout=20)
            r.raise_for_status()

            frappe.db.set_value("Postmark Campaign", c.name, "status", "Sent to n8n")
            frappe.db.commit()

        except Exception as e:
            # If the webhook fails, stamp it as Failed and write the reason
            frappe.db.set_value("Postmark Campaign", c.name, {
                "status": "Failed",
                "failure_reason": str(e)[:140] # Grabs the clean, short error message
            })
            frappe.db.commit()
            frappe.log_error(frappe.get_traceback(), f"Campaign webhook failed: {c.name}")
