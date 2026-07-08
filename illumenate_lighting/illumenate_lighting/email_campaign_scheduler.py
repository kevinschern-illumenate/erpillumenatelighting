import frappe
from frappe.utils import now_datetime
import requests
import json

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
            "pstmrk_template_alias",
            "pstmrk_email_group",
            "pstmrk_campaign_name",
            "pstmrk_subject",
            "pstmrk_html_content",
            "pstmrk_text_content",
            "pstmrk_test_email",
            "status",
            "pstmrk_tag",
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

        if frappe.db.sql("SELECT ROW_COUNT()")[0][0] == 0:
            continue

        frappe.db.commit()

        payload = {
            "campaign_docname": c.name,
            "template_alias": c.pstmrk_template_alias,
            "email_group": c.pstmrk_email_group,
            "campaign_name": c.pstmrk_campaign_name,
            "subject": c.pstmrk_subject,
            "html_body": c.pstmrk_html_content,
            "text_body": c.pstmrk_text_content,
            "test_recipient": c.pstmrk_test_email,
            "is_test_run": 0,
            "postmark_tag": c.pstmrk_tag,
        }

        try:
            r = requests.post(webhook_url, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=20)
            r.raise_for_status()

            frappe.db.set_value("Postmark Campaign", c.name, "status", "Sent to n8n")
            frappe.db.commit()

        except Exception as e:
            frappe.db.set_value("Postmark Campaign", c.name, "status", "Failed")
            frappe.db.set_value("Postmark Campaign", c.name, "failure_reason", str(e)[:140])
            frappe.db.commit()
            frappe.log_error(frappe.get_traceback(), f"Campaign webhook failed: {c.name}")
