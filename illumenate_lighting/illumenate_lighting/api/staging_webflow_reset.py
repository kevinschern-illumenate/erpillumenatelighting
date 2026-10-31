# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""One-time staging safety reset for Webflow product item IDs (plan 4.11 item 2, task Z4).

The staging site is a copy of production data, so it carries the Webflow item
IDs of live production items. Webflow has no staging site: a staging sync that
reuses one of those IDs would PATCH or publish the real item. This script
clears every stored product item ID and the publication state built on it, so
staging creates its own ``[staging]`` items instead.

Scope: ``ilL-Webflow-Product`` only. Category and other reference records keep
their IDs on purpose (plan 4.11 item 5: references may point at real records).

It refuses to run unless site config ``webflow_environment`` is ``staging``.
Dry run is the default. Run it on the staging site only::

    bench --site <staging-site> execute \\
        illumenate_lighting.illumenate_lighting.api.staging_webflow_reset.clear_production_webflow_ids

    bench --site <staging-site> execute \\
        illumenate_lighting.illumenate_lighting.api.staging_webflow_reset.clear_production_webflow_ids \\
        --kwargs "{'dry_run': False}"
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api import n8n_config

PRODUCT = "ilL-Webflow-Product"
PUBLICATION = "ilL-Product-Publication"
SYNC_STATE = "ilL-Child-Webflow-Sync-State"
JOB = "ilL-Publish-Job"
OPEN_JOB_STATES = ("QUEUED", "RUNNING", "FAILED")

PUBLICATION_RESET = {
	"remote_item_id": None,
	"staged_hash": None,
	"staged_on": None,
	"live_hash": None,
	"published_on": None,
	"state": "NEEDS_REVIEW",
}
SYNC_STATE_RESET = {
	"webflow_item_id": None,
	"sync_status": "Never Synced",
	"last_synced_at": None,
	"sync_error_message": None,
}
PRODUCT_RESET = {
	"webflow_item_id": None,
	"sync_status": "Never Synced",
	"last_synced_at": None,
	"sync_error_message": None,
}


def _require_staging():
	if not n8n_config.is_staging():
		frappe.throw(
			_("This reset only runs on a staging site. Site config {0} must be 'staging'.").format(
				n8n_config.ENVIRONMENT_KEY
			)
		)


def _has_value(row, fields):
	return any(row.get(field) for field in fields)


@frappe.whitelist(methods=["POST"])
def clear_production_webflow_ids(dry_run=True):
	"""Clear copied production Webflow item IDs on staging. Returns a report.

	``dry_run`` (default True) only reports what would change.
	"""
	frappe.only_for("System Manager")
	_require_staging()
	dry_run = frappe.parse_json(dry_run) if isinstance(dry_run, str) else bool(dry_run)

	publications = [
		row
		for row in frappe.get_all(
			PUBLICATION,
			fields=["name", "product", "brand", "state", *PUBLICATION_RESET],
			limit_page_length=0,
		)
		if _has_value(row, ("remote_item_id", "staged_hash", "live_hash", "published_on"))
	]
	sync_rows = frappe.get_all(
		SYNC_STATE,
		filters={"parenttype": PRODUCT, "webflow_item_id": ["is", "set"]},
		fields=["name", "parent", "brand", "webflow_item_id"],
		limit_page_length=0,
	)
	products = frappe.get_all(
		PRODUCT,
		filters={"webflow_item_id": ["is", "set"]},
		fields=["name", "webflow_item_id"],
		limit_page_length=0,
	)
	open_jobs = frappe.get_all(
		JOB,
		filters={"state": ["in", OPEN_JOB_STATES]},
		fields=["name", "product", "brand", "operation", "state"],
		limit_page_length=0,
	)

	report = {
		"dry_run": dry_run,
		"publications": [
			{"name": r.name, "product": r.product, "brand": r.brand, "remote_item_id": r.remote_item_id}
			for r in publications
		],
		"sync_targets": [
			{"product": r.parent, "brand": r.brand, "webflow_item_id": r.webflow_item_id} for r in sync_rows
		],
		"products": [{"product": r.name, "webflow_item_id": r.webflow_item_id} for r in products],
		"open_jobs_superseded": [
			{"name": r.name, "product": r.product, "brand": r.brand, "operation": r.operation}
			for r in open_jobs
		],
	}
	report["counts"] = {key: len(value) for key, value in report.items() if isinstance(value, list)}
	if dry_run:
		return report

	for row in publications:
		frappe.db.set_value(PUBLICATION, row.name, PUBLICATION_RESET, update_modified=False)
	for row in sync_rows:
		frappe.db.set_value(SYNC_STATE, row.name, SYNC_STATE_RESET, update_modified=False)
	for row in products:
		frappe.db.set_value(PRODUCT, row.name, PRODUCT_RESET, update_modified=False)
	for row in open_jobs:
		# A queued job was built from the copied state; it must never be sent.
		frappe.db.set_value(
			JOB,
			row.name,
			{
				"state": "SUPERSEDED",
				"lease_token": None,
				"last_error": "Superseded by the staging Webflow ID reset (plan 4.11).",
			},
			update_modified=False,
		)
	frappe.db.commit()
	frappe.logger("webflow").info({"event": "staging_webflow_reset", "counts": report["counts"]})
	return report
