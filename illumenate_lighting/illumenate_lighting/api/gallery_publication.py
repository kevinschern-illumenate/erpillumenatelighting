"""Revision-fenced gallery publication (docs/WEBFLOW_GALLERY_SYNC.md sections 5.2, 6, 6a, 7).

A parallel copy of the product flow in ``api/publication.py``, which is not touched. Remote writes
are claimed by n8n. Every call is one Frappe transaction; no network call or internal commit occurs
while holding row locks. A job freezes the payload and its brand configuration.
"""

import json
import re
import secrets
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from illumenate_lighting.illumenate_lighting import webflow_notify
from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json, fingerprint
from illumenate_lighting.illumenate_lighting.api.gallery_products import product_item_id
from illumenate_lighting.illumenate_lighting.api.gallery_projection import build_payload
from illumenate_lighting.illumenate_lighting.api.gallery_readiness import evaluate
from illumenate_lighting.illumenate_lighting.api.publication_contract import (
	RETRY_MINUTES,
	callback_disposition,
	failure_reason,
	next_retry,
)
from illumenate_lighting.illumenate_lighting.api.webflow_brand import get_default_brand, resolve_brand
from illumenate_lighting.illumenate_lighting.portal.staff import require, require_catalog_reader

GALLERY = "ilL-Webflow-Gallery"
STATE = "ilL-Gallery-Publication"
JOB = "ilL-Gallery-Publish-Job"
PRODUCT = "ilL-Webflow-Product"
SYNC_STATE = "ilL-Child-Webflow-Sync-State"
SERIES = "ilL-Attribute-Series"
LEASE_MINUTES = 5


def _save(doc):
	doc.flags.publication_write = True
	return doc.save(ignore_permissions=True) if not doc.is_new() else doc.insert(ignore_permissions=True)


def _locked(gallery, brand):
	frappe.db.sql("select name from `tabilL-Webflow-Gallery` where name=%s for update", gallery)
	doc = frappe.get_doc(GALLERY, gallery)
	config = resolve_brand(brand, allow_inactive=True)
	brand = config["brand_code"]
	key = fingerprint([gallery, brand])
	name = frappe.db.get_value(STATE, {"scope_key": key}, "name")
	if name:
		frappe.db.sql("select name from `tabilL-Gallery-Publication` where name=%s for update", name)
		state = frappe.get_doc(STATE, name)
	else:
		# An imported gallery (spec section 9a) already knows its Webflow item.
		remote_id = frappe.db.get_value(
			SYNC_STATE, {"parent": gallery, "parenttype": GALLERY, "brand": brand}, "webflow_item_id"
		)
		state = _save(
			frappe.get_doc(
				{
					"doctype": STATE,
					"scope_key": key,
					"gallery": gallery,
					"brand": brand,
					"state": "NEEDS_REVIEW",
					"remote_item_id": remote_id,
				}
			)
		)
	return doc, state, config


def _targeted(gallery, brand):
	"""Target brand rows when there are any, else the default brand only."""
	rows = gallery.get("target_brands") or []
	if rows:
		return any(row.get("brand") == brand and row.get("enabled") for row in rows)
	return brand == get_default_brand()


def _product_refs(gallery, brand):
	"""{product: {"name", "webflow_item_id"}}; the item ID comes from ``product_item_id`` (spec 6a)."""
	refs = {}
	default_brand = get_default_brand()
	for row in gallery.get("products_used") or []:
		product = row.get("product")
		if not product or product in refs:
			continue
		item_id = product_item_id(product, brand, default_brand)
		name = frappe.db.get_value(PRODUCT, product, "product_name")
		refs[product] = {"name": name or product, "webflow_item_id": item_id or None}
	return refs


def _refresh(doc, state, config):
	gallery = doc.as_dict()
	refs = _product_refs(gallery, state.brand)
	active_series = set(frappe.get_all(SERIES, filters={"is_active": 1}, pluck="name"))
	readiness = evaluate(gallery, config=config, product_refs=refs, active_series=active_series)
	targeted = _targeted(gallery, state.brand)
	if not targeted:
		readiness["issues"].append(
			{
				"record": state.brand,
				"field": "target_brands",
				"message": "This gallery does not target the brand.",
			}
		)
	readiness["ready"] = not readiness["issues"]
	payload = build_payload(gallery, base_url=config.get("erpnext_base_url") or "", product_refs=refs)
	payload["active"] = bool(gallery.get("is_active") and targeted)
	payload["brand"] = {
		"brand_code": config.get("brand_code"),
		"webflow_site_id": config.get("webflow_site_id"),
		"galleries_collection_id": (config.get("collections") or {}).get("Galleries"),
		"erpnext_base_url": config.get("erpnext_base_url"),
	}
	# Spec 6a: the hash covers each product's Webflow item ID and name, so a product change
	# between request and claim supersedes the job.
	dependencies = {**readiness["dependencies"], "product_refs": refs}
	state.current_hash = fingerprint({"payload": payload, "dependencies": dependencies})
	state.readiness_json = canonical_json({key: readiness[key] for key in ("ready", "issues", "warnings")})
	state.dependencies_json = canonical_json(dependencies)
	if state.approved_hash != state.current_hash:
		state.state = "NEEDS_REVIEW"
	_save(state)
	return payload, readiness


def _receipt(state):
	return {
		key: state.get(key)
		for key in (
			"name",
			"gallery",
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
def inspect(gallery, brand):
	require_catalog_reader()
	doc, state, config = _locked(gallery, brand)
	_, readiness = _refresh(doc, state, config)
	return {**_receipt(state), "readiness": readiness}


@frappe.whitelist(methods=["POST"])
def request(gallery, brand, operation, expected_hash):
	require("catalog")
	if operation not in ("STAGE", "PUBLISH", "RETIRE"):
		frappe.throw(_("Choose a supported publication action"))
	doc, state, config = _locked(gallery, brand)
	payload, readiness = _refresh(doc, state, config)
	if state.current_hash != expected_hash:
		frappe.throw(_("Gallery or its products changed; inspect the current revision first"))
	if operation == "RETIRE":
		if payload["active"] or not config.get("sync_enabled"):
			frappe.throw(
				_("Deactivate the gallery or its brand target before retirement, and enable synchronization")
			)
	else:
		if not payload["active"] or not readiness["ready"]:
			frappe.throw(_("Resolve gallery readiness issues before publication"))
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
				"gallery": doc.name,
				"brand": state.brand,
				"publication": state.name,
				"operation": operation,
				"revision_hash": expected_hash,
				"payload_json": canonical_json(payload),
				"payload_hash": fingerprint(payload),
				"request_key": key,
				"requested_by": frappe.session.user,
				"started_by": frappe.session.user,
				"state": "QUEUED",
			}
		)
	)
	state.state = "QUEUED"
	_save(state)
	return {"job": job.name, **_receipt(state)}


def _job_locked(name):
	row = frappe.db.get_value(JOB, name, ["gallery", "brand"], as_dict=True)
	if not row:
		frappe.throw(_("Publication job unavailable"))
	doc, state, config = _locked(row.gallery, row.brand)
	frappe.db.sql("select name from `tabilL-Gallery-Publish-Job` where name=%s for update", name)
	return frappe.get_doc(JOB, name), doc, state, config


@frappe.whitelist(methods=["POST"])
def claim(brand, limit=1):
	require("integration")
	limit = max(1, min(int(limit), 10))
	now = now_datetime()
	jobs = frappe.db.sql(
		"""select name from `tabilL-Gallery-Publish-Job` where brand=%s and
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
			if job.state == "FAILED" and job.next_attempt_on:
				# A retry cannot send a gallery that is no longer ready: stop and notify once.
				job.next_attempt_on = None
				job.last_error = state.last_error = "Publication failed (readiness: the gallery is not ready)"
				_save(job)
				_save(state)
				_notify_if_final(job)
			continue
		busy = frappe.db.exists(
			JOB, {"publication": state.name, "name": ["!=", job.name], "state": "RUNNING"}
		)
		if busy:
			continue
		job.state, job.lease_token = "RUNNING", secrets.token_hex(24)
		job.lease_expires = now + timedelta(minutes=LEASE_MINUTES)
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
		if not re.fullmatch(r"[a-fA-F0-9]{24}", remote_item_id):
			frappe.throw(_("Invalid remote item ID"))
		if state.remote_item_id and state.remote_item_id != remote_item_id:
			frappe.throw(_("Remote identity conflict requires reconciliation"))
		state.remote_item_id = job.remote_item_id = remote_item_id
	if disposition == "superseded":
		job.state = "SUPERSEDED"
		state.last_error = "A remote operation completed for an older revision; stage the current revision."
	elif outcome == "error":
		_fail(job, state, error_code, retry_after)
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
	_notify_if_final(job)
	return {"job": job.name, "state": job.state, "publication": _receipt(state)}


def _fail(job, state, error_code, retry_after=None):
	"""Record a failed attempt and schedule its retry (1, 5, 15 minutes, as for products).

	A temporary failure (rate limit, timeout, connection, 5xx) gets ``next_attempt_on`` until the
	three retries are used up; a permanent one gets none. n8n claims a due retry on its next poll.
	A newer revision supersedes it at claim time, so a retry never sends an old version.
	"""
	# Do not persist remote response bodies or credentials in error fields.
	code = str(error_code or "transport")[:32]
	job.state = state.state = "FAILED"
	job.next_attempt_on = next_retry(code, job.attempts, now_datetime(), retry_after)
	message = f"Publication failed ({code}: {failure_reason(code)})"
	if job.next_attempt_on:
		retry = min(max(1, int(job.attempts or 1)), len(RETRY_MINUTES))
		message += f"; retry {retry} of {len(RETRY_MINUTES)} at {str(job.next_attempt_on)[11:16]}"
	elif int(job.attempts or 1) > len(RETRY_MINUTES) and next_retry(code, 1, now_datetime()):
		message += f" after {len(RETRY_MINUTES)} retries"
	job.last_error = state.last_error = message


def _notify_if_final(job):
	"""Notify a failure once it is final (permanent, or retries used up); a success is a push."""
	gallery, brand = job.get("gallery"), job.get("brand")
	if job.state == "FAILED" and not job.next_attempt_on:
		webflow_notify.notify(
			_("Webflow gallery sync failed: {0} ({1}, job {2})").format(gallery, brand, job.get("name")),
			_("{0} of gallery {1} on {2} (attempt {3}): {4}").format(
				job.get("operation"),
				gallery,
				brand,
				job.get("attempts") or 1,
				job.get("last_error") or _("Publication failed"),
			),
			GALLERY,
			gallery,
			once=True,
		)
	elif job.state == "COMPLETE":
		titles = {
			"STAGE": _("Gallery {0} is staged on Webflow"),
			"PUBLISH": _("Gallery {0} is live on Webflow"),
			"RETIRE": _("Gallery {0} was removed from Webflow"),
		}
		webflow_notify.success_push(
			job.get("started_by") or job.get("requested_by"),
			titles.get(job.get("operation"), titles["STAGE"]).format(gallery),
			_("{0} ({1}) went through.").format(gallery, brand),
			GALLERY,
			gallery,
		)


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


def expire_leases(now=None):
	"""A claimed job whose lease ran out without an answer is a temporary failure ("timeout").

	Retried on the 1, 5, 15 minute schedule; notifies when the retries are used up. Run by the
	minute tick as the publication service user. Returns job names.
	"""
	require("integration")
	now = now or now_datetime()
	rows = frappe.get_all(
		JOB,
		filters={"state": "RUNNING", "lease_expires": ["<=", now]},
		pluck="name",
		order_by="lease_expires asc",
		limit_page_length=50,
	)
	expired = []
	for name in rows:
		job, _doc, state, _config = _job_locked(name)
		if job.state != "RUNNING" or not job.lease_expires or get_datetime(job.lease_expires) > now:
			continue
		job.lease_token = None
		_fail(job, state, "timeout")
		_save(job)
		_save(state)
		_notify_if_final(job)
		expired.append(job.name)
	return expired


def retry_brands(now=None):
	"""Brands with a failed gallery job whose retry is due."""
	now = now or now_datetime()
	return frappe.get_all(
		JOB,
		filters={"state": "FAILED", "next_attempt_on": ["<=", now]},
		pluck="brand",
		distinct=True,
	)


def invalidate_gallery(doc, method=None):
	"""doc_events on_update: a changed gallery is visible as unreviewed before the next claim."""
	if doc.flags.get("_skip_webflow_sync") or not frappe.db.table_exists(STATE):
		return
	frappe.db.sql(
		"""update `tabilL-Gallery-Publication` set state='NEEDS_REVIEW'
		where gallery=%s""",
		doc.name,
	)


def tick():
	"""scheduler_events cron every minute: expired gallery leases become "timeout" failures.

	Runs as the same publication service user as the product tick (``webflow_auto_push.tick``).
	Due retries need no push here: n8n claims them on its next poll.
	"""
	from illumenate_lighting.illumenate_lighting.portal.service_users import run_as

	try:
		with run_as("publication"):
			expire_leases()
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Webflow gallery retries: expiring leases failed")
