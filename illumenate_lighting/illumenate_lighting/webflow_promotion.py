# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Tools for moving the Webflow sync to main (plan Phase 5, 10.4).

- ``backfill_published_on``: products that are public on Webflow today get their publication's
  ``published_on``, so the rules that depend on "was ever published" (the template status table,
  approvals, Webflow Draft staged or published hidden) are right from the first push. On
  staging the Webflow ID remap did this.
- ``auto_push_preview``: before site config ``webflow_auto_push`` is switched on, every product
  a save would push to Webflow, with the status Webflow would get and why.

Both are System Manager only and change nothing unless ``apply`` is set (the preview never does).
Run from the System Console, for example::

    from illumenate_lighting.illumenate_lighting import webflow_promotion as p

    p.backfill_published_on()  # dry run
    p.backfill_published_on(apply=True)
    p.auto_push_preview()
"""

import frappe
from frappe.utils import cint, now_datetime

PRODUCT = "ilL-Webflow-Product"
PUBLICATION = "ilL-Product-Publication"
SYNC_STATE = "ilL-Child-Webflow-Sync-State"
PUBLIC_STAGES = ("Published", "Discontinued")


# --- published_on backfill ---------------------------------------------------------------


def backfill_rows(products, sync_rows, publications, default_brand):
	"""Pure: what the backfill does for each public product and brand.

	``products``: dicts with name, webflow_status, webflow_item_id, last_synced_at and
	brands (the enabled target brands, empty for none). ``sync_rows``: {(product, brand):
	{webflow_item_id, last_synced_at}}. ``publications``: {(product, brand): {name,
	published_on}}. A product is public when its Webflow Status is Published or Discontinued
	and it has a Webflow item for the brand. Returns one row per product and brand:
	{product, brand, item, published_on, action} with action "set", "create", "already" or
	"skip" (and a reason).
	"""
	out = []
	for product in products:
		brands = product.get("brands") or ([default_brand] if default_brand else [])
		for brand in brands:
			row = {"product": product["name"], "brand": brand}
			if product.get("webflow_status") not in PUBLIC_STAGES:
				continue
			sync = sync_rows.get((product["name"], brand)) or {}
			item = sync.get("webflow_item_id") or (
				product.get("webflow_item_id") if brand == default_brand else None
			)
			publication = publications.get((product["name"], brand))
			if not item:
				out.append({**row, "action": "skip", "reason": "no Webflow item for this brand"})
				continue
			if publication and publication.get("published_on"):
				out.append(
					{**row, "item": item, "published_on": publication["published_on"], "action": "already"}
				)
				continue
			when = sync.get("last_synced_at") or product.get("last_synced_at")
			out.append(
				{
					**row,
					"item": item,
					"published_on": str(when) if when else None,
					"action": "set" if publication else "create",
				}
			)
	return out


@frappe.whitelist(methods=["POST"])
def backfill_published_on(apply=False):
	"""Set ``published_on`` for products that are public on Webflow today. Dry run by default.

	The date is the brand's last sync, else the product's, else now. A product without a
	publication record for the brand gets one (as the first sync would create it).
	"""
	frappe.only_for("System Manager")
	from illumenate_lighting.illumenate_lighting.api.webflow_brand import get_default_brand

	apply = cint(apply)
	default_brand = get_default_brand()
	products = frappe.get_all(
		PRODUCT,
		filters={"webflow_status": ["in", list(PUBLIC_STAGES)]},
		fields=["name", "webflow_status", "webflow_item_id", "last_synced_at"],
	)
	names = [row.name for row in products]
	brands = {}
	for row in frappe.get_all(
		"ilL-Child-Webflow-Brand-Target",
		filters={"parenttype": PRODUCT, "parent": ["in", names or [""]], "enabled": 1},
		fields=["parent", "brand"],
	):
		brands.setdefault(row.parent, []).append(row.brand)
	for product in products:
		product["brands"] = brands.get(product.name, [])
	sync_rows = {
		(row.parent, row.brand): row
		for row in frappe.get_all(
			SYNC_STATE,
			filters={"parenttype": PRODUCT, "parent": ["in", names or [""]]},
			fields=["parent", "brand", "webflow_item_id", "last_synced_at"],
		)
	}
	publications = {
		(row.product, row.brand): row
		for row in frappe.get_all(
			PUBLICATION,
			filters={"product": ["in", names or [""]]},
			fields=["name", "product", "brand", "published_on"],
		)
	}
	rows = backfill_rows(products, sync_rows, publications, default_brand)
	if apply:
		from illumenate_lighting.illumenate_lighting.api import publication

		for row in rows:
			if row["action"] not in ("set", "create"):
				continue
			when = row.get("published_on") or now_datetime()
			if row["action"] == "create":
				# The same record the first sync would create, with the item's ID.
				_doc, state, _config = publication._locked(row["product"], row["brand"])
				name = state.name
			else:
				name = publications[(row["product"], row["brand"])].name
			frappe.db.set_value(PUBLICATION, name, "published_on", when, update_modified=False)
			row["published_on"] = str(when)
		frappe.db.commit()
	counts = {}
	for row in rows:
		counts[row["action"]] = counts.get(row["action"], 0) + 1
	return {"applied": bool(apply), "counts": counts, "rows": rows}


# --- What turning on automatic pushes would send ------------------------------------------


@frappe.whitelist()
def auto_push_preview():
	"""Every product a save would push once ``webflow_auto_push`` is on (read only).

	A save queues a push for each enabled target brand where the product has a Webflow item,
	unless its Webflow Status is Archived. Each row shows the Webflow Status, the template's
	Product Status, the status Webflow would get (plan 4.3) and whether the product is ready.
	Products that would not push are listed with the reason.
	"""
	frappe.only_for("System Manager")
	from illumenate_lighting.illumenate_lighting import webflow_auto_push as auto
	from illumenate_lighting.illumenate_lighting import webflow_state
	from illumenate_lighting.illumenate_lighting.api.product_readiness import evaluate

	default_brand = auto._default_brand()
	pushes, quiet = [], []
	for name in frappe.get_all(PRODUCT, pluck="name", order_by="name asc"):
		doc = frappe.get_doc(PRODUCT, name)
		rows = [
			{"brand": row.get("brand"), "enabled": row.get("enabled")}
			for row in doc.get("target_brands") or []
		]
		targets = auto.target_brands(rows, None if rows else default_brand)
		synced = auto.synced_brands(name, doc.get("webflow_item_id"))
		brands = auto.queue_brands(doc.get("webflow_status"), targets, synced, {})
		if not brands:
			reason = (
				"Archived"
				if doc.get("webflow_status") == auto.ARCHIVED
				else "never synced (pushes only from a button)"
			)
			quiet.append({"product": name, "reason": reason})
			continue
		template_status = webflow_state.template_status(doc)
		status, rule = webflow_state.effective_status(
			template_status, doc.get("webflow_status"), webflow_state.ever_published(name)
		)
		try:
			issues = evaluate(doc, "cms").get("issues") or []
		except Exception as error:
			issues = [{"message": f"readiness check failed: {error}"}]
		pushes.append(
			{
				"product": name,
				"brands": brands,
				"webflow_status": doc.get("webflow_status"),
				"template_status": template_status,
				"webflow_gets": status if status is not None else "nothing (not pushed)",
				"why": rule,
				"ready": not issues,
				"issues": [issue.get("message") for issue in issues][:5],
			}
		)
	return {
		"switch_on": auto.enabled(),
		"would_push": len(pushes),
		"not_ready": sum(1 for row in pushes if not row["ready"]),
		"pushes": pushes,
		"quiet": quiet,
	}


# --- The users the sync runs as (Phase 7, plan 4.12) ---------------------------------------


def expected_access(kind):
	"""Pure: what each integration user needs, as (roles, [(doctype, permission)]).

	- ``n8n``: the n8n "Authorization" credential's user. It reads templates and the product
	  (Get Spec Sheet Data), writes the template's Spec Sheet field (Update Template Spec Sheet),
	  uploads the PDF (``upload_spec_pdf``) and answers the publication jobs
	  (``mark_webflow_synced``, role ilL Integration).
	- ``publication``: the worker that claims jobs and sends them to n8n (ilL Integration).
	- ``webflow_auto_push``: requests the automatic pushes (ilL Catalog Publisher).
	"""
	from illumenate_lighting.illumenate_lighting.web_listing_schema import TEMPLATE_DOCTYPES

	if kind == "n8n":
		perms = [(doctype, "read") for doctype in TEMPLATE_DOCTYPES]
		perms += [(doctype, "write") for doctype in TEMPLATE_DOCTYPES]
		perms += [(PRODUCT, "read"), ("File", "create")]
		return ("ilL Integration",), perms
	if kind == "publication":
		return ("ilL Integration",), [(PRODUCT, "read")]
	if kind == "webflow_auto_push":
		return ("ilL Catalog Publisher",), [(PRODUCT, "read")]
	return (), []


def access_problems(user_type, enabled, roles, permitted, kind):
	"""Pure: what is missing for one user. ``permitted`` is {(doctype, permission): bool}."""
	needed_roles, needed_perms = expected_access(kind)
	problems = []
	if not enabled:
		problems.append("user is disabled")
	if user_type != "System User":
		problems.append(f"user type is {user_type or 'not set'}, needs System User")
	has_admin = "System Manager" in roles
	problems += [f"missing role {role}" for role in needed_roles if role not in roles and not has_admin]
	problems += [
		f"cannot {perm} {doctype}" for doctype, perm in needed_perms if not permitted.get((doctype, perm))
	]
	return problems


@frappe.whitelist()
def check_integration_users(n8n_user=None):
	"""Read only: the users the Webflow sync runs as, their roles and what is missing.

	``n8n_user`` is the user behind the n8n "Authorization" credential (its API key). When not
	given, every enabled user with the ilL Integration role and an API key is checked as one.
	"""
	frappe.only_for("System Manager")
	from illumenate_lighting.illumenate_lighting.portal.service_users import service_user

	users = [
		(service_user("publication"), "publication"),
		(service_user("webflow_auto_push"), "webflow_auto_push"),
	]
	if n8n_user:
		users.append((n8n_user, "n8n"))
	else:
		holders = frappe.get_all(
			"Has Role", filters={"role": "ilL Integration", "parenttype": "User"}, pluck="parent"
		)
		for name in sorted(set(holders)):
			if name not in dict(users) and frappe.db.get_value("User", name, "api_key"):
				users.append((name, "n8n"))
	report = []
	for name, kind in users:
		row = frappe.db.get_value("User", name, ["name", "enabled", "user_type"], as_dict=True)
		if not row:
			report.append({"user": name, "kind": kind, "problems": ["user does not exist"]})
			continue
		roles = frappe.get_roles(name)
		_roles, perms = expected_access(kind)
		permitted = {
			(doctype, perm): bool(frappe.has_permission(doctype, perm, user=name)) for doctype, perm in perms
		}
		report.append(
			{
				"user": name,
				"kind": kind,
				"roles": sorted(role for role in roles if role not in ("All", "Guest")),
				"problems": access_problems(row.user_type, row.enabled, roles, permitted, kind),
			}
		)
	return {"ok": not any(row["problems"] for row in report), "users": report}
