"""Automatic pushes to Webflow, retries and the off switch (plan 4.19 Q2-Q4, sync rebuild step 3).

**When.** Saving a Webflow Product (a linked template's save saves its product too) queues an
automatic push for every enabled target brand where the product already has a Webflow item
(publication ``remote_item_id`` or sync-state ``webflow_item_id``). The push is due 2 minutes
after the last save; each save moves it, so a burst of saves sends the final version once.
Never-synced products, Archived products and a product with a pending approval get none (the
approval's Approve sends it). One ``ilL-Webflow-Auto-Push`` row per product and brand (unique
``scope_key``) holds the waiting push; it is deleted once the push is requested.

**What.** The minute tick (``tick``, scheduler cron ``* * * * *``) sends due rows through the
same code as the Sync to Webflow button (``webflow_export_v2.stage_brands``: save, inspect,
STAGE request, ``ilL-Publish-Job``, n8n W2). It runs as the ``webflow_auto_push`` service user
(``portal/service_users.py``, role ilL Catalog Publisher), because ``publication.request``
requires the catalog capability and the publication worker only holds the integration one.
The person who saved is kept on the row and named in failure notifications.

**Failures.** A product that is not ready, or a push that cannot be requested, notifies at once
(``webflow_notify.auto_push_failed``) and drops the row; the next save queues it again. Once a
job exists, failures are the job's (``publication._fail``): temporary ones (429, timeouts,
connection errors, 5xx) retry after 1, 5 and 15 minutes, claimed by this tick, and notify only
when the third retry fails; permanent ones notify at once. A newer save supersedes a waiting
retry at claim time, and its own push sends the latest version.

**Off switch.** Site config ``webflow_auto_push`` (1, true, yes; off when unset). Off: the
buttons work, saves still queue rows, and the rows are held until it is turned on. Retries of
pushes already sent keep running: a running push is never cancelled.
"""

import hashlib
from datetime import timedelta

import frappe
from frappe import _

DOCTYPE = "ilL-Webflow-Auto-Push"
PRODUCT = "ilL-Webflow-Product"
PUBLICATION = "ilL-Product-Publication"
SYNC_STATE = "ilL-Child-Webflow-Sync-State"
BRAND_TARGET = "ilL-Child-Webflow-Brand-Target"
JOB = "ilL-Publish-Job"
SWITCH_KEY = "webflow_auto_push"
SERVICE_USER = "webflow_auto_push"
ARCHIVED = "Archived"
DEBOUNCE = timedelta(minutes=2)
# Set on a product saved by a push itself (the button, the tick): it queues no new push.
SKIP_FLAG = "webflow_auto_push_skip"
TRUTHY = ("1", "true", "yes", "on")
# Pushes requested per tick; the rest wait for the next minute.
PUSHES_PER_TICK = 10
FIELDS = ["name", "product", "brand", "due_at", "saved_by", "replaces_job"]
DROP, WAIT, HOLD, APPROVAL, PUSH = "drop", "wait", "held", "approval", "push"


# --- Rules (pure) -------------------------------------------------------------------------


def parse_switch(value):
	"""Pure: whether the site config value turns automatic pushes on (default off)."""
	if isinstance(value, bool):
		return value
	if isinstance(value, (int, float)):
		return value == 1
	return str(value or "").strip().strip("\"'").lower() in TRUTHY


def scope_key(product, brand):
	"""Pure: the unique key of a product and brand's waiting push."""
	return hashlib.sha1(f"{product}\0{brand}".encode()).hexdigest()


def target_brands(rows, default_brand):
	"""Pure: the enabled target brands, or the default brand when the table is empty."""
	if rows:
		return [row.get("brand") for row in rows if row.get("enabled") and row.get("brand")]
	return [default_brand] if default_brand else []


def queue_brands(status, targets, synced, retrying):
	"""Pure: the brands a save queues. ``retrying`` maps a brand to its failed job waiting
	for a retry; a save replaces that retry even before the first sync succeeded."""
	if status == ARCHIVED:
		return []
	return [brand for brand in targets if brand in synced or brand in retrying]


def due_at(saved_at):
	"""Pure: when a push saved at ``saved_at`` is due."""
	return saved_at + DEBOUNCE


def decide(*, exists, status, targeted, synced, replaces_job, due, switch_on, approval_pending):
	"""Pure: what the tick does with one waiting row.

	``drop`` (never push: gone, Archived, no longer targeted or never synced), ``wait`` (not
	due), ``held`` (the switch is off), ``approval`` (waits for the approval) or ``push``.
	"""
	if not exists or status == ARCHIVED or not targeted or not (synced or replaces_job):
		return DROP
	if not due:
		return WAIT
	if not switch_on:
		return HOLD
	if approval_pending:
		return APPROVAL
	return PUSH


def readiness_reason(issues):
	"""Pure: readiness issues as one line for a notification."""
	parts = []
	for issue in issues or []:
		text = issue.get("message") or _("Unknown issue")
		where = ", ".join(str(value) for value in (issue.get("record"), issue.get("field")) if value)
		parts.append(f"{text} ({where})" if where else text)
	return _("Not ready: {0}").format("; ".join(parts) or _("readiness check failed"))


# --- Reads ----------------------------------------------------------------------------------


def enabled():
	return parse_switch(frappe.conf.get(SWITCH_KEY))


def _default_brand():
	from illumenate_lighting.illumenate_lighting.api.webflow_brand import get_default_brand

	return get_default_brand()


def _targets(product):
	rows = frappe.get_all(
		BRAND_TARGET, filters={"parent": product, "parenttype": PRODUCT}, fields=["brand", "enabled"]
	)
	return target_brands(rows, _default_brand())


def synced_brands(product, legacy_item_id=None):
	"""Brands where the product has a Webflow item (publication or sync state; for the default
	brand also the legacy ``webflow_item_id``, as ``publication._locked`` reads it)."""
	brands = set()
	for row in frappe.get_all(
		PUBLICATION, filters={"product": product, "remote_item_id": ["is", "set"]}, fields=["brand"]
	):
		brands.add(row.get("brand"))
	for row in frappe.get_all(
		SYNC_STATE,
		filters={"parent": product, "parenttype": PRODUCT, "webflow_item_id": ["is", "set"]},
		fields=["brand"],
	):
		brands.add(row.get("brand"))
	if legacy_item_id:
		brands.add(_default_brand())
	brands.discard(None)
	return brands


def retrying_jobs(product):
	"""Brand -> the product's failed job that waits for a retry."""
	rows = frappe.get_all(
		JOB,
		filters={"product": product, "state": "FAILED", "next_attempt_on": ["is", "set"]},
		fields=["name", "brand"],
		order_by="creation desc",
	)
	jobs = {}
	for row in rows:
		jobs.setdefault(row.get("brand"), row.get("name"))
	return jobs


# --- Queue ----------------------------------------------------------------------------------


def _now():
	return frappe.utils.now_datetime()


def upsert(product, brand, due, saved_by, replaces_job=None):
	"""Create or move the product and brand's waiting push (one row per scope key)."""
	key = scope_key(product, brand)
	values = {"due_at": due, "saved_by": saved_by, "replaces_job": replaces_job}
	name = frappe.db.get_value(DOCTYPE, {"scope_key": key}, "name")
	if name:
		frappe.db.set_value(DOCTYPE, name, values)
		return name
	frappe.db.savepoint("webflow_auto_push_insert")
	try:
		doc = frappe.get_doc(
			{"doctype": DOCTYPE, "product": product, "brand": brand, "scope_key": key, **values}
		).insert(ignore_permissions=True)
		return doc.name
	except frappe.DuplicateEntryError:
		# Inserted by a concurrent save: move that row instead.
		frappe.db.rollback(save_point="webflow_auto_push_insert")
		name = frappe.db.get_value(DOCTYPE, {"scope_key": key}, "name")
		frappe.db.set_value(DOCTYPE, name, values)
		return name


def clear(product, brand=None):
	"""Drop the product's waiting pushes (one brand, or all)."""
	filters = {"product": product}
	if brand:
		filters["brand"] = brand
	frappe.db.delete(DOCTYPE, filters)


def on_product_update(doc, method=None):
	"""doc_events ilL-Webflow-Product on_update: queue (or move) the automatic push.

	No network call here: the tick sends it.
	"""
	from illumenate_lighting.illumenate_lighting import webflow_approvals

	flags = doc.flags or {}
	if flags.get(SKIP_FLAG) or flags.get("_skip_webflow_sync") or flags.get(webflow_approvals.FLAG):
		return
	if doc.get("webflow_status") == ARCHIVED:
		clear(doc.name)
		return
	rows = [
		{"brand": row.get("brand"), "enabled": row.get("enabled")} for row in doc.get("target_brands") or []
	]
	targets = target_brands(rows, None if rows else _default_brand())
	retrying = retrying_jobs(doc.name)
	synced = synced_brands(doc.name, doc.get("webflow_item_id"))
	brands = queue_brands(doc.get("webflow_status"), targets, synced, retrying)
	if not brands:
		return
	due = due_at(_now())
	for brand in brands:
		upsert(doc.name, brand, due, frappe.session.user, retrying.get(brand))


# --- Tick -------------------------------------------------------------------------------------


def tick():
	"""scheduler_events cron every minute: due retries, then due automatic pushes (switch on)."""
	run_retries()
	if enabled():
		run_due()


def run_retries():
	"""Expired leases become "timeout" failures; brands with a due retry are claimed and sent."""
	from illumenate_lighting.illumenate_lighting.api import n8n_config, publication
	from illumenate_lighting.illumenate_lighting.api.webflow_export_v2 import claim_and_dispatch
	from illumenate_lighting.illumenate_lighting.portal.service_users import run_as

	try:
		with run_as("publication"):
			publication.expire_leases()
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Webflow retries: expiring leases failed")
	brands = [brand for brand in publication.retry_brands() if brand]
	if not brands:
		return []
	try:
		webhook_url = n8n_config.sync_webhook_url()
		n8n_config.auth_headers()
	except Exception:
		frappe.log_error(title="Webflow retries: n8n is not configured")
		return []
	sent = []
	for brand in brands:
		try:
			sent.extend(claim_and_dispatch(brand, webhook_url))
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Webflow retries failed for {brand}")
	return sent


def run_due(now=None, limit=PUSHES_PER_TICK):
	"""Send the due automatic pushes, at most ``limit`` per tick; one transaction per row."""
	now = now or _now()
	names = frappe.get_all(
		DOCTYPE, filters={"due_at": ["<=", now]}, pluck="name", order_by="due_at asc", limit_page_length=200
	)
	outcomes, pushes = {}, 0
	for name in names:
		if pushes >= limit:
			break
		try:
			outcome = process(name, now)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Webflow automatic push failed: {name}")
			outcome = "error"
		outcomes[name] = outcome
		pushes += outcome in (PUSH, "failed")
	return outcomes


def _lock(name):
	"""Lock the product, then the row: the same order as a product save that moves the row."""
	product = frappe.db.get_value(DOCTYPE, name, "product")
	if not product:
		return None
	frappe.db.sql("select name from `tabilL-Webflow-Product` where name=%s for update", product)
	frappe.db.sql("select name from `tabilL-Webflow-Auto-Push` where name=%s for update", name)
	return frappe.db.get_value(DOCTYPE, name, FIELDS, as_dict=True)


def process(name, now=None):
	"""Decide and act on one waiting row. Returns the decision (or "failed")."""
	from illumenate_lighting.illumenate_lighting import webflow_approvals

	now = now or _now()
	row = _lock(name)
	if not row:
		return DROP
	product = frappe.db.get_value(PRODUCT, row.product, ["webflow_status", "webflow_item_id"], as_dict=True)
	exists = bool(product)
	product = product or {}
	action = decide(
		exists=exists,
		status=product.get("webflow_status"),
		targeted=exists and row.brand in _targets(row.product),
		synced=exists and row.brand in synced_brands(row.product, product.get("webflow_item_id")),
		replaces_job=row.get("replaces_job"),
		due=frappe.utils.get_datetime(row.due_at) <= frappe.utils.get_datetime(now),
		switch_on=enabled(),
		approval_pending=bool(webflow_approvals.pending(row.product)),
	)
	if action == DROP:
		frappe.db.delete(DOCTYPE, {"name": row.name})
	if action != PUSH:
		return action
	return push(row)


def push(row):
	"""Request the push as the button does, as the auto-push user. Never raises: a failure
	before a job exists notifies at once and drops the row (the next save queues it again)."""
	from illumenate_lighting.illumenate_lighting import webflow_notify
	from illumenate_lighting.illumenate_lighting.api.webflow_export_v2 import stage_brands
	from illumenate_lighting.illumenate_lighting.portal.service_users import run_as

	frappe.db.savepoint("webflow_auto_push")
	try:
		with run_as(SERVICE_USER):
			results = stage_brands(row.product, [row.brand])
	except Exception as error:
		frappe.db.rollback(save_point="webflow_auto_push")
		frappe.log_error(title=f"Webflow automatic push failed: {row.product} ({row.brand})")
		frappe.db.delete(DOCTYPE, {"name": row.name})
		webflow_notify.auto_push_failed(row.product, row.brand, _plain(error), row.get("saved_by"))
		return "failed"
	frappe.db.delete(DOCTYPE, {"name": row.name})
	for result in results:
		if result.get("issues") is not None:
			webflow_notify.auto_push_failed(
				row.product, row.brand, readiness_reason(result["issues"]), row.get("saved_by")
			)
			return "failed"
	return PUSH


def _plain(error):
	text = frappe.utils.strip_html(str(error)) if hasattr(frappe.utils, "strip_html") else str(error)
	return (text or error.__class__.__name__).strip()[:300]


# --- Form -------------------------------------------------------------------------------------


@frappe.whitelist()
def get_status(product):
	"""The Webflow Product form's line: waiting automatic pushes and failed jobs waiting for a retry."""
	from illumenate_lighting.illumenate_lighting import webflow_approvals

	if not frappe.has_permission(PRODUCT, "read", doc=product):
		frappe.throw(_("You can't read this product."), frappe.PermissionError)
	switch_on = enabled()
	approval = bool(webflow_approvals.pending(product))
	waiting = []
	for row in frappe.get_all(
		DOCTYPE, filters={"product": product}, fields=["brand", "due_at"], order_by="brand asc"
	):
		state = HOLD if not switch_on else APPROVAL if approval else WAIT
		waiting.append({"brand": row.get("brand"), "due_at": str(row.get("due_at") or ""), "state": state})
	retries = [
		{
			"brand": row.get("brand"),
			"next_attempt_on": str(row.get("next_attempt_on") or ""),
			"error": row.get("last_error"),
		}
		for row in frappe.get_all(
			JOB,
			filters={"product": product, "state": "FAILED", "next_attempt_on": ["is", "set"]},
			fields=["brand", "next_attempt_on", "last_error"],
			order_by="next_attempt_on asc",
		)
	]
	return {"enabled": switch_on, "waiting": waiting, "retries": retries}
