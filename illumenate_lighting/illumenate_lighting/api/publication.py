"""Revision-fenced product publication. Remote writes are claimed by n8n.

Every call is one Frappe transaction. No network call or internal commit occurs
while holding row locks. A job freezes the export and its brand configuration.
"""

import json
import secrets
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json, fingerprint
from illumenate_lighting.illumenate_lighting.api.product_readiness import content_record, evaluate
from illumenate_lighting.illumenate_lighting.api.publication_contract import callback_disposition, retry_at
from illumenate_lighting.illumenate_lighting.api.webflow_brand import get_default_brand, resolve_brand
from illumenate_lighting.illumenate_lighting.portal.staff import require, require_catalog_reader

PRODUCT = "ilL-Webflow-Product"
STATE = "ilL-Product-Publication"
JOB = "ilL-Publish-Job"


def _save(doc):
	doc.flags.publication_write = True
	return doc.save(ignore_permissions=True) if not doc.is_new() else doc.insert(ignore_permissions=True)


def _locked(product, brand):
	frappe.db.sql("select name from `tabilL-Webflow-Product` where name=%s for update", product)
	doc = frappe.get_doc(PRODUCT, product)
	config = resolve_brand(brand, allow_inactive=True)
	brand = config["brand_code"]
	key = fingerprint([product, brand])
	name = frappe.db.get_value(STATE, {"scope_key": key}, "name")
	if name:
		frappe.db.sql("select name from `tabilL-Product-Publication` where name=%s for update", name)
		state = frappe.get_doc(STATE, name)
	else:
		remote_id = frappe.db.get_value(
			"ilL-Child-Webflow-Sync-State",
			{"parent": product, "parenttype": PRODUCT, "brand": brand},
			"webflow_item_id",
		)
		if not remote_id and brand == get_default_brand():
			remote_id = doc.webflow_item_id
		state = _save(
			frappe.get_doc(
				{
					"doctype": STATE,
					"scope_key": key,
					"product": product,
					"brand": brand,
					"state": "NEEDS_REVIEW",
					"remote_item_id": remote_id,
				}
			)
		)
	return doc, state, config


def _targeted(doc, brand):
	rows = doc.get("target_brands") or []
	return any(row.brand == brand and row.enabled for row in rows) if rows else brand == get_default_brand()


def _refresh(doc, state, config):
	active = bool(doc.is_active and config["is_active"] and _targeted(doc, state.brand))
	readiness = evaluate(doc, "cms")
	brand_projection = {
		key: config.get(key)
		for key in (
			"brand_code",
			"webflow_site_id",
			"collections",
			"erpnext_base_url",
			"include_configurator_payload",
			"sync_enabled",
		)
	}
	if not config.get("collections", {}).get("Products"):
		readiness["issues"].append(
			{"record": state.brand, "field": "collections", "message": "Set the products collection ID"}
		)
	if not config.get("sync_enabled"):
		readiness["issues"].append(
			{"record": state.brand, "field": "sync_enabled", "message": "Enable brand synchronization"}
		)
	readiness["ready"] = not readiness["issues"]
	payload = {
		"schema_version": 1,
		"projection_version": 1,
		"product_slug": doc.product_slug,
		"brand": brand_projection,
		"active": active,
		"product": None,
	}
	if active:
		from illumenate_lighting.illumenate_lighting.api.webflow_export import get_webflow_products

		products = get_webflow_products(brand=state.brand, product_slug=doc.name, limit=1)["products"]
		if not products:
			frappe.throw(_("Product is not available for this brand"))
		payload["product"] = content_record(json.loads(frappe.as_json(products[0])))
		# Category references must belong to this brand, never the default brand.
		if doc.product_category:
			category_id = frappe.db.get_value(
				"ilL-Child-Webflow-Sync-State",
				{
					"parenttype": "ilL-Webflow-Category",
					"parent": doc.product_category,
					"brand": state.brand,
					"sync_status": "Synced",
				},
				"webflow_item_id",
			)
			if not category_id:
				readiness["ready"] = False
				readiness["issues"].append(
					{
						"record": doc.product_category,
						"field": "sync_targets",
						"message": "Stage category in this brand first",
					}
				)
			payload["product"]["category_webflow_item_id"] = category_id
			payload["product"]["category_details"] = {"webflow_item_id": category_id}
	state.current_hash = fingerprint({"payload": payload, "dependencies": readiness["dependencies"]})
	state.readiness_json = canonical_json({key: readiness[key] for key in ("ready", "issues")})
	state.dependencies_json = canonical_json(readiness["dependencies"])
	if state.approved_hash != state.current_hash:
		state.state = "NEEDS_REVIEW"
	_save(state)
	return payload, readiness


def _receipt(state):
	return {
		key: state.get(key)
		for key in (
			"name",
			"product",
			"brand",
			"state",
			"current_hash",
			"approved_hash",
			"staged_hash",
			"live_hash",
			"remote_item_id",
			"last_error",
		)
	}


@frappe.whitelist(methods=["POST"])
def inspect(product, brand):
	require_catalog_reader()
	doc, state, config = _locked(product, brand)
	_, readiness = _refresh(doc, state, config)
	return {**_receipt(state), "readiness": readiness}


@frappe.whitelist(methods=["POST"])
def request(product, brand, operation, expected_hash):
	require("catalog")
	if operation not in ("STAGE", "PUBLISH", "RETIRE"):
		frappe.throw(_("Choose a supported publication action"))
	doc, state, config = _locked(product, brand)
	payload, readiness = _refresh(doc, state, config)
	if state.current_hash != expected_hash:
		frappe.throw(_("Product or dependencies changed; inspect the current revision first"))
	if operation == "RETIRE":
		if payload["active"] or not config.get("sync_enabled"):
			frappe.throw(
				_("Deactivate the product or brand target before retirement, and enable synchronization")
			)
	else:
		if not payload["active"] or not readiness["ready"]:
			frappe.throw(_("Resolve product readiness issues before publication"))
		if operation == "PUBLISH" and (
			state.staged_hash != expected_hash
			or state.approved_hash != expected_hash
			or not state.remote_item_id
		):
			frappe.throw(_("Stage this approved revision before publishing"))
	state.approved_hash, state.approved_by, state.approved_on = (
		expected_hash,
		frappe.session.user,
		now_datetime(),
	)
	key = fingerprint([state.name, operation, expected_hash])
	existing = frappe.db.get_value(JOB, {"request_key": key}, "name")
	if existing:
		_save(state)
		return {"job": existing, **_receipt(state)}
	job = _save(
		frappe.get_doc(
			{
				"doctype": JOB,
				"product": doc.name,
				"brand": state.brand,
				"publication": state.name,
				"operation": operation,
				"revision_hash": expected_hash,
				"payload_json": canonical_json(payload),
				"payload_hash": fingerprint(payload),
				"request_key": key,
				"requested_by": frappe.session.user,
				"state": "QUEUED",
			}
		)
	)
	state.state = "QUEUED"
	_save(state)
	return {"job": job.name, **_receipt(state)}


def _job_locked(name):
	row = frappe.db.get_value(JOB, name, ["product", "brand"], as_dict=True)
	if not row:
		frappe.throw(_("Publication job unavailable"))
	doc, state, config = _locked(row.product, row.brand)
	frappe.db.sql("select name from `tabilL-Publish-Job` where name=%s for update", name)
	return frappe.get_doc(JOB, name), doc, state, config


@frappe.whitelist(methods=["POST"])
def claim(brand, limit=1):
	require("integration")
	limit = max(1, min(int(limit), 10))
	now = now_datetime()
	jobs = frappe.db.sql(
		"""select name from `tabilL-Publish-Job` where brand=%s and
		(state='QUEUED' or (state='FAILED' and next_attempt_on<=%s)
		or (state='RUNNING' and lease_expires<=%s)) order by creation asc limit 200""",
		(brand, now, now),
		as_dict=True,
	)
	claimed = []
	for row in jobs:
		job, doc, state, config = _job_locked(row.name)
		if job.state == "RUNNING" and job.lease_expires and get_datetime(job.lease_expires) > now:
			continue
		if job.state == "FAILED" and (not job.next_attempt_on or get_datetime(job.next_attempt_on) > now):
			continue
		if job.state not in ("QUEUED", "FAILED", "RUNNING"):
			continue
		_, readiness = _refresh(doc, state, config)
		if job.revision_hash != state.current_hash or state.approved_hash != state.current_hash:
			job.state = "SUPERSEDED"
			_save(job)
			continue
		if job.operation != "RETIRE" and not readiness["ready"]:
			continue
		busy = frappe.db.exists(
			JOB, {"publication": state.name, "name": ["!=", job.name], "state": "RUNNING"}
		)
		if busy:
			continue
		job.state, job.lease_token = "RUNNING", secrets.token_hex(24)
		job.lease_expires = now + timedelta(minutes=5)
		job.attempts = int(job.attempts or 0) + 1
		_save(job)
		claimed.append(
			{
				"job": job.name,
				"token": job.lease_token,
				"operation": job.operation,
				"revision_hash": job.revision_hash,
				"payload_hash": job.payload_hash,
				"remote_item_id": state.remote_item_id,
				"payload": json.loads(job.payload_json),
			}
		)
		if len(claimed) >= limit:
			break
	return {"jobs": claimed}


@frappe.whitelist(methods=["POST"])
def acknowledge(
	job,
	token,
	revision_hash,
	payload_hash,
	remote_item_id=None,
	outcome="success",
	error_code=None,
	retry_after=None,
):
	require("integration")
	job, doc, state, config = _job_locked(job)
	_refresh(doc, state, config)
	try:
		disposition = callback_disposition(
			job.as_dict(),
			token=token,
			revision_hash=revision_hash,
			payload_hash=payload_hash,
			current_hash=state.current_hash,
		)
	except ValueError as exc:
		frappe.throw(str(exc))
	if disposition == "duplicate":
		if (job.remote_item_id or "") != (remote_item_id or "") or outcome != "success":
			frappe.throw(_("Conflicting callback for completed job"))
		return {"job": job.name, "state": job.state, "duplicate": True}
	if outcome not in ("success", "error"):
		frappe.throw(_("Unsupported callback outcome"))
	if remote_item_id:
		import re

		if not re.fullmatch(r"[a-fA-F0-9]{24}", remote_item_id):
			frappe.throw(_("Invalid remote item ID"))
		if state.remote_item_id and state.remote_item_id != remote_item_id:
			frappe.throw(_("Remote identity conflict requires reconciliation"))
		state.remote_item_id = job.remote_item_id = remote_item_id
	if disposition == "superseded":
		job.state = "SUPERSEDED"
		state.last_error = "A remote operation completed for an older revision; stage the current revision."
	elif outcome == "error":
		job.state = state.state = "FAILED"
		# Do not persist remote response bodies or credentials in error fields.
		code = str(error_code or "transport")[:32]
		job.last_error = state.last_error = f"Publication failed ({code})"
		job.next_attempt_on = (
			retry_at(job.attempts, now_datetime(), retry_after)
			if code in ("transport", "429", "500", "502", "503", "504")
			else None
		)
	else:
		if job.operation != "RETIRE" and not state.remote_item_id:
			frappe.throw(_("Successful publication requires a remote item ID"))
		job.state, job.completed_on = "COMPLETE", now_datetime()
		job.result_json = canonical_json({"remote_item_id": state.remote_item_id, "operation": job.operation})
		job.last_error = state.last_error = None
		if job.operation == "STAGE":
			state.staged_hash, state.staged_on, state.state = revision_hash, now_datetime(), "STAGED"
		elif job.operation == "PUBLISH":
			state.live_hash, state.published_on, state.state = revision_hash, now_datetime(), "LIVE"
		else:
			state.live_hash, state.staged_hash, state.state = None, None, "RETIRED"
	_save(job)
	_save(state)
	return {"job": job.name, "state": job.state, "publication": _receipt(state)}


@frappe.whitelist(methods=["POST"])
def retry(job):
	require_catalog_reader()
	job, doc, state, config = _job_locked(job)
	_refresh(doc, state, config)
	if (
		job.state != "FAILED"
		or job.revision_hash != state.current_hash
		or state.approved_hash != state.current_hash
	):
		frappe.throw(_("Only a failed job for the current approved revision can be retried"))
	job.state, job.next_attempt_on = "QUEUED", None
	_save(job)
	return {"job": job.name, "state": job.state}


def invalidate_product(doc, method=None):
	"""A changed authoring record is visible as unreviewed before the next claim."""
	if doc.flags.get("_skip_webflow_sync") or not frappe.db.table_exists(STATE):
		return
	frappe.db.sql(
		"""update `tabilL-Product-Publication` set state='NEEDS_REVIEW'
		where product=%s""",
		doc.name,
	)


@frappe.whitelist(methods=["POST"])
def reconcile_local(after=None, limit=50):
	"""Refresh a bounded keyset page; this does not verify remote content."""
	require_catalog_reader()
	limit = max(1, min(int(limit), 100))
	filters = {"name": [">", after]} if after else {}
	rows = frappe.get_all(
		STATE,
		filters=filters,
		fields=["name", "product", "brand"],
		order_by="name asc",
		limit_page_length=limit + 1,
	)
	result = []
	for row in rows[:limit]:
		doc, state, config = _locked(row.product, row.brand)
		_refresh(doc, state, config)
		result.append(_receipt(state))
	return {"publications": result, "next_cursor": rows[limit - 1].name if len(rows) > limit else None}


def _completed_payload(state, operation, revision):
	if not revision:
		return None
	name = frappe.db.get_value(
		JOB,
		{"publication": state.name, "operation": operation, "revision_hash": revision, "state": "COMPLETE"},
		"name",
	)
	if not name:
		return None  # Legacy remote identity has no frozen content evidence.
	job = frappe.get_doc(JOB, name)
	payload = json.loads(job.payload_json)
	if fingerprint(payload) != job.payload_hash or payload["brand"]["brand_code"] != state.brand:
		frappe.throw("Publication evidence is inconsistent; investigate the completed job")
	return payload


@frappe.whitelist()
def reconciliation_batch(brand, after=None, limit=25):
	"""Read-only export of last acknowledged staged/live content, never today's draft.

	Remote reconciliation runs outside the database transaction. No token, key or
	remote response body is stored here; the CLI produces a field/hash-only report.
	"""
	require("integration")
	config = resolve_brand(brand, allow_inactive=True)
	limit = max(1, min(int(limit), 100))
	filters = {"brand": config["brand_code"]}
	if after:
		filters["name"] = [">", after]
	rows = frappe.get_all(
		STATE, filters=filters, fields=["name"], order_by="name asc", limit_page_length=limit + 1
	)
	result = []
	for row in rows[:limit]:
		state = frappe.get_doc(STATE, row.name)
		result.append(
			{
				**_receipt(state),
				"collection_id": config.get("collections", {}).get("Products"),
				"staged_payload": _completed_payload(state, "STAGE", state.staged_hash),
				"live_payload": _completed_payload(state, "PUBLISH", state.live_hash),
			}
		)
	return {"publications": result, "next_cursor": rows[limit - 1].name if len(rows) > limit else None}
