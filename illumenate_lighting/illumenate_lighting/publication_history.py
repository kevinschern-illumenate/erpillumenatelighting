# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Publication History (plan 4.14, D12, Phase 6): a read-only view of a product's pushes.

For the Webflow Product, and for a template through its linked product: one summary per brand
(ilL-Product-Publication) and the latest pushes (ilL-Publish-Job). No new table.
"""

import frappe
from frappe import _

PRODUCT = "ilL-Webflow-Product"
PUBLICATION = "ilL-Product-Publication"
JOB = "ilL-Publish-Job"
LIMIT = 25

OPERATIONS = {"STAGE": "Sync", "PUBLISH": "Publish", "RETIRE": "Remove from Webflow"}
STATES = {
	"QUEUED": "Waiting",
	"RUNNING": "Running",
	"COMPLETE": "Done",
	"FAILED": "Failed",
	"SUPERSEDED": "Replaced by a newer save",
}


def job_row(job):
	"""Pure: one history row from an ilL-Publish-Job (a dict)."""
	state = job.get("state")
	failed_retrying = state == "FAILED" and job.get("next_attempt_on")
	return {
		"job": job.get("name"),
		"brand": job.get("brand"),
		"what": OPERATIONS.get(job.get("operation"), job.get("operation") or ""),
		"result": "Failed, retrying" if failed_retrying else STATES.get(state, state or ""),
		"ok": state == "COMPLETE",
		"by": job.get("started_by") or job.get("requested_by"),
		"requested_on": str(job.get("creation") or ""),
		"completed_on": str(job.get("completed_on") or ""),
		"attempts": job.get("attempts") or 0,
		"error": job.get("last_error") if state != "COMPLETE" else None,
	}


def _product_of(product=None, template_doctype=None, template_name=None):
	if product:
		return product
	if template_doctype and template_name:
		frappe.has_permission(template_doctype, "read", doc=template_name, throw=True)
		return frappe.db.get_value(template_doctype, template_name, "webflow_product")
	return None


@frappe.whitelist()
def get_history(product=None, template_doctype=None, template_name=None):
	"""The product's publication summary per brand and its latest pushes (read permission)."""
	product = _product_of(product, template_doctype, template_name)
	if not product or not frappe.db.exists(PRODUCT, product):
		return {"product": None, "brands": [], "jobs": []}
	if not frappe.has_permission(PRODUCT, "read", doc=product):
		frappe.throw(_("You can't read this product."), frappe.PermissionError)
	brands = frappe.get_all(
		PUBLICATION,
		filters={"product": product},
		fields=[
			"brand",
			"state",
			"staged_on",
			"published_on",
			"remote_item_id",
			"last_error",
			"review_reason",
		],
		order_by="brand asc",
	)
	jobs = frappe.get_all(
		JOB,
		filters={"product": product},
		fields=[
			"name",
			"brand",
			"operation",
			"state",
			"requested_by",
			"started_by",
			"creation",
			"completed_on",
			"attempts",
			"last_error",
			"next_attempt_on",
		],
		order_by="creation desc",
		limit=LIMIT,
	)
	return {
		"product": product,
		"brands": [
			{
				"brand": row.brand,
				"state": row.state,
				"staged_on": str(row.staged_on or ""),
				"published_on": str(row.published_on or ""),
				"on_webflow": bool(row.remote_item_id),
				"error": row.last_error,
				"review_reason": row.review_reason,
			}
			for row in brands
		],
		"jobs": [job_row(job) for job in jobs],
		"limit": LIMIT,
	}
