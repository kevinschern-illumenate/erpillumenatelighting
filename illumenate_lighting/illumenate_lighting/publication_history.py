# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Publication History (plan 4.14, D12, Phase 6): a read-only view of a product's pushes.

For the Webflow Product, and for a template through its linked product: one summary per brand
(ilL-Product-Publication) and one timeline (owner, 2026-11-08) of the latest pushes
(ilL-Publish-Job, with the statuses at the time) and of the status changes on the template's
Product Status and the product's Webflow Status (from the change log, Version). No new table.
"""

import json

import frappe
from frappe import _

PRODUCT = "ilL-Webflow-Product"
PUBLICATION = "ilL-Product-Publication"
JOB = "ilL-Publish-Job"
LIMIT = 25

# Every push is a Sync today; the others are named in the result.
OPERATIONS = {"PUBLISH": "published", "RETIRE": "removed from Webflow"}
STATES = {
	"QUEUED": "Waiting",
	"RUNNING": "Running",
	"COMPLETE": "Done",
	"FAILED": "Failed",
	"SUPERSEDED": "Replaced by a newer save",
}


def status_text(template_status, webflow_status, effective_status):
	"""Pure: "Active + Live · Published", plus "sent as X" when the template overrode it."""
	parts = [value for value in (template_status, webflow_status) if value]
	text = " · ".join(parts)
	if effective_status and effective_status != webflow_status:
		text += f" (sent as {effective_status})"
	return text


def job_row(job):
	"""Pure: one timeline row from an ilL-Publish-Job (a dict)."""
	state = job.get("state")
	failed_retrying = state == "FAILED" and job.get("next_attempt_on")
	result = "Failed, retrying" if failed_retrying else STATES.get(state, state or "")
	operation = OPERATIONS.get(job.get("operation"))
	if operation:
		result = f"{result} ({operation})"
	return {
		"kind": "push",
		"job": job.get("name"),
		"when": str(job.get("creation") or ""),
		"status": status_text(
			job.get("template_status"), job.get("webflow_status"), job.get("effective_status")
		),
		"result": result,
		"ok": state == "COMPLETE",
		"by": job.get("started_by") or job.get("requested_by"),
		"completed_on": str(job.get("completed_on") or ""),
		"error": job.get("last_error") if state != "COMPLETE" else None,
	}


STATUS_FIELDS = {"product_status": "Template", "webflow_status": "Webflow Status"}


def status_changes(version_data, field_labels=STATUS_FIELDS):
	"""Pure: [(label, old, new)] for the status fields a Version's ``data`` changed."""
	try:
		data = json.loads(version_data) if isinstance(version_data, str) else (version_data or {})
	except ValueError:
		return []
	out = []
	for change in data.get("changed") or []:
		if len(change) == 3 and change[0] in field_labels and change[1] != change[2]:
			out.append((field_labels[change[0]], change[1] or "not set", change[2] or "not set"))
	return out


def change_rows(versions, field):
	"""Pure: timeline rows from Version records (dicts with data, owner, creation)."""
	rows = []
	for version in versions:
		for label, old, new in status_changes(version.get("data"), {field: STATUS_FIELDS[field]}):
			rows.append(
				{
					"kind": "status",
					"when": str(version.get("creation") or ""),
					"status": f"{label}: {old} → {new}",
					"result": "Status changed",
					"ok": None,
					"by": version.get("owner"),
					"completed_on": "",
					"error": None,
				}
			)
	return rows


def _versions(doctype, name, field):
	return frappe.get_all(
		"Version",
		filters={"ref_doctype": doctype, "docname": name, "data": ["like", f'%"{field}"%']},
		fields=["data", "owner", "creation"],
		order_by="creation desc",
		limit=LIMIT,
	)


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
		return {"product": None, "brands": [], "rows": []}
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
			"operation",
			"state",
			"requested_by",
			"started_by",
			"template_status",
			"webflow_status",
			"effective_status",
			"creation",
			"completed_on",
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
		"rows": timeline(product, jobs),
		"limit": LIMIT,
	}


def timeline(product, jobs):
	"""Pushes and status changes, newest first."""
	from illumenate_lighting.illumenate_lighting.web_listing_schema import WEBFLOW_PRODUCT_LINKS

	rows = [job_row(job) for job in jobs]
	rows += change_rows(_versions(PRODUCT, product, "webflow_status"), "webflow_status")
	values = frappe.db.get_value(PRODUCT, product, list(WEBFLOW_PRODUCT_LINKS.values()), as_dict=True) or {}
	for doctype, field in WEBFLOW_PRODUCT_LINKS.items():
		if values.get(field):
			rows += change_rows(_versions(doctype, values[field], "product_status"), "product_status")
	rows.sort(key=lambda row: row["when"], reverse=True)
	return rows
