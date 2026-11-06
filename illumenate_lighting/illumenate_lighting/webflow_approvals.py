"""Owner approvals before a Webflow restore or archive (plan 4.19 Q5, Q6).

Two changes wait for approval before anything goes to Webflow:

- **Restore:** a Webflow Product's Webflow Status goes from Archived to Webflow Draft, Published or Discontinued.
- **Archive:** a product whose page was ever published (a Product Publication with
  ``published_on``, any brand) gets the Webflow Status Archived, or its linked template gets
  the Product Status Archived. A product never published archives at once.

The change is saved; an ``ilL-Webflow-Approval`` row (one Pending per product; a newer change
replaces it) holds it. While it is Pending nothing for that product goes to Webflow (the sync
buttons, publication requests and the worker's claim refuse). Approve sends the change through
the normal sync path as the approving user. Reject leaves Webflow alone and puts the status back.

Created by the ``on_update`` doc_events in hooks.py: ``on_product_update`` (ilL-Webflow-Product)
and ``on_template_update`` (the six template doctypes).
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from illumenate_lighting.illumenate_lighting.web_listing_schema import WEBFLOW_PRODUCT_LINKS

APPROVAL = "ilL-Webflow-Approval"
PRODUCT = "ilL-Webflow-Product"
PUBLICATION = "ilL-Product-Publication"
ARCHIVED = "Archived"
RESTORE_TO = ("Webflow Draft", "Published", "Discontinued")  # Discontinued puts the page back up (owner, 2026-11-06)
RESTORE, ARCHIVE = "Restore", "Archive"
PENDING, APPROVED, REJECTED = "Pending", "Approved", "Rejected"
# Set on a document saved by an approval decision, so the write-back asks for no new approval.
FLAG = "webflow_approval_write"
PENDING_FIELDS = [
	"name",
	"product",
	"action",
	"from_status",
	"to_status",
	"summary",
	"template_doctype",
	"template_name",
	"requested_by",
]


# --- Rules (pure) -------------------------------------------------------------------------


def status_action(from_status, to_status, ever_published):
	"""Pure: the approval a Webflow Status change needs (Restore, Archive) or None."""
	if from_status == to_status:
		return None
	if from_status == ARCHIVED and to_status in RESTORE_TO:
		return RESTORE
	if to_status == ARCHIVED:
		return ARCHIVE if ever_published else None
	return None


def template_action(from_status, to_status, ever_published):
	"""Pure: the approval a template Product Status change needs (Archive) or None."""
	if from_status != to_status and to_status == ARCHIVED and ever_published:
		return ARCHIVE
	return None


def is_ever_published(publications):
	"""Pure: whether any publication row (any brand) has a ``published_on``."""
	return any(row.get("published_on") for row in publications or [])


def source_of(approval):
	return "template" if approval and approval.get("template_doctype") else "product"


def plan(pending, source, from_status, to_status, ever_published):
	"""Pure: what a status change does to the product's approvals.

	``pending`` is the product's Pending approval (or None); ``source`` is "product" (Webflow
	Status) or "template" (template Product Status). A change from the same source as the
	pending approval is measured from that approval's starting status, so changing back
	cancels it. Returns ("upsert", {action, from_status, to_status}), ("delete", None) or
	("keep", None).
	"""
	rule = status_action if source == "product" else template_action
	same = bool(pending) and source_of(pending) == source
	start = pending.get("from_status") if same else from_status
	action = rule(start, to_status, ever_published)
	if action:
		return "upsert", {"action": action, "from_status": start, "to_status": to_status}
	return ("delete", None) if same else ("keep", None)


def site_label(brand):
	"""Pure: a brand's Webflow Public Site URL without the scheme, else its label or code."""
	url = (brand.get("webflow_site_url") or "").strip()
	if url:
		return url.split("://", 1)[-1].rstrip("/")
	return brand.get("brand_label") or brand.get("brand_code") or ""


def describe(action, product, to_status, sites, template=None):
	"""Pure: what approving would do, e.g. "Restore kit-ra01 to Published on example.webflow.io"."""
	where = _(" on {0}").format(", ".join(sites)) if sites else ""
	if action == RESTORE:
		return _("Restore {0} to {1}{2}").format(product, to_status, where)
	if template:
		return _("Archive {0}{1} (template {2} set to Archived)").format(product, where, template)
	return _("Archive {0}{1}").format(product, where)


# --- Reads ----------------------------------------------------------------------------------


def ever_published(product):
	"""Whether the product's page was ever published, for any brand."""
	return is_ever_published(
		frappe.get_all(
			PUBLICATION,
			filters={"product": product, "published_on": ["is", "set"]},
			fields=["published_on"],
			limit=1,
		)
	)


def pending(product):
	"""The product's Pending approval as a dict, or None."""
	if not product:
		return None
	return frappe.db.get_value(APPROVAL, {"product": product, "state": PENDING}, PENDING_FIELDS, as_dict=True)


def hold_message(row):
	return _(
		"Nothing was sent to Webflow: approval {0} is waiting for {1} ({2}). "
		"Approve or reject it on the Webflow Product first."
	).format(row.get("name"), row.get("product"), row.get("summary") or row.get("action"))


def assert_no_pending(product):
	"""Refuse a push while the product has a Pending approval."""
	row = pending(product)
	if row:
		frappe.throw(hold_message(row))


def _sites(product):
	from illumenate_lighting.illumenate_lighting.api.webflow_brand import get_default_brand, resolve_brand

	rows = frappe.get_all(
		"ilL-Child-Webflow-Brand-Target",
		filters={"parent": product, "parenttype": PRODUCT},
		fields=["brand", "enabled"],
	)
	# The sync's target brands: the enabled rows, or the default brand when there are none.
	codes = [row.get("brand") for row in rows if row.get("enabled")] if rows else [get_default_brand()]
	labels = []
	for code in codes:
		if not code:
			continue
		try:
			label = site_label(resolve_brand(code, allow_inactive=True))
		except Exception:
			label = code
		if label not in labels:
			labels.append(label)
	return labels


# --- Recording a change --------------------------------------------------------------------


def record_change(product, source, from_status, to_status, template=None):
	"""Create, update or cancel the product's Pending approval for one status change."""
	current = pending(product)
	what, values = plan(current, source, from_status, to_status, ever_published(product))
	if what == "keep":
		return None
	if what == "delete":
		frappe.delete_doc(APPROVAL, current.name, ignore_permissions=True, force=True)
		return None
	template_doctype, template_name = template or (None, None)
	values.update(
		{
			"product": product,
			"template_doctype": template_doctype,
			"template_name": template_name,
			"summary": describe(
				values["action"], product, values["to_status"], _sites(product), template_name
			),
			"requested_by": frappe.session.user,
		}
	)
	if current:
		doc = frappe.get_doc(APPROVAL, current.name)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": APPROVAL, "state": PENDING, **values}).insert(
			ignore_permissions=True
		)
	from illumenate_lighting.illumenate_lighting import webflow_notify

	webflow_notify.approval_requested(doc)
	frappe.msgprint(
		_("Waiting for approval: {0}. Nothing goes to Webflow for this product until it is approved.").format(
			doc.summary
		),
		indicator="orange",
		alert=True,
	)
	return doc


def on_product_update(doc, method=None):
	"""doc_events ilL-Webflow-Product on_update: a Webflow Status change."""
	if doc.flags.get(FLAG):
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	old, new = before.get("webflow_status"), doc.get("webflow_status")
	if old != new:
		record_change(doc.name, "product", old, new)


def on_template_update(doc, method=None):
	"""doc_events on_update of the six template doctypes: a Product Status change."""
	if doc.flags.get(FLAG):
		return
	product = doc.get("webflow_product")
	field = WEBFLOW_PRODUCT_LINKS.get(doc.doctype)
	if not product or not field:
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	old, new = before.get("product_status"), doc.get("product_status")
	if old == new or frappe.db.get_value(PRODUCT, product, field) != doc.name:
		return
	record_change(product, "template", old, new, (doc.doctype, doc.name))


# --- Decisions -----------------------------------------------------------------------------


def _decidable(name):
	"""Lock the approval and check the user may decide it."""
	if not frappe.db.exists(APPROVAL, name):
		frappe.throw(_("Webflow approval {0} does not exist.").format(name), frappe.DoesNotExistError)
	frappe.db.sql("select name from `tabilL-Webflow-Approval` where name=%s for update", name)
	doc = frappe.get_doc(APPROVAL, name)
	if "System Manager" not in frappe.get_roles() and not frappe.has_permission(
		PRODUCT, "write", doc=doc.product
	):
		frappe.throw(_("You can't decide approvals for this product."), frappe.PermissionError)
	return doc


def _decide(doc, state):
	doc.state, doc.decided_by, doc.decided_on = state, frappe.session.user, now_datetime()
	doc.save(ignore_permissions=True)


def _result(doc, **extra):
	return {"name": doc.name, "product": doc.product, "action": doc.action, "state": doc.state, **extra}


@frappe.whitelist(methods=["POST"])
def approve(name):
	"""Approve and send the change to Webflow through the normal sync, as this user. Idempotent."""
	doc = _decidable(name)
	if doc.state == APPROVED:
		return _result(doc, already=True)
	if doc.state == REJECTED:
		frappe.throw(_("Webflow approval {0} was already rejected.").format(name))
	_decide(doc, APPROVED)
	from illumenate_lighting.illumenate_lighting.api.webflow_export_v2 import trigger_sync_v2

	frappe.db.savepoint("webflow_approval_sync")
	try:
		sync = trigger_sync_v2(doc.product)
	except Exception as error:
		# The approval stands; the sync can be run again with the Sync to Webflow button.
		frappe.db.rollback(save_point="webflow_approval_sync")
		frappe.log_error(title=f"Webflow approval sync failed: {doc.product}")
		return _result(doc, sync=None, sync_error=str(error))
	return _result(doc, sync=sync)


def _put_back(doc):
	"""Write the status from before the change back, unless it was changed again since."""
	if doc.template_doctype and doc.template_name:
		if not frappe.db.exists(doc.template_doctype, doc.template_name):
			return False
		target, field = frappe.get_doc(doc.template_doctype, doc.template_name), "product_status"
	else:
		if not frappe.db.exists(PRODUCT, doc.product):
			return False
		target, field = frappe.get_doc(PRODUCT, doc.product), "webflow_status"
	if target.get(field) != doc.to_status:
		return False
	target.set(field, doc.from_status)
	target.flags[FLAG] = True
	target.save(ignore_permissions=True)
	return True


@frappe.whitelist(methods=["POST"])
def reject(name):
	"""Reject: Webflow is left as it is and the status goes back. Idempotent."""
	doc = _decidable(name)
	if doc.state == REJECTED:
		return _result(doc, already=True)
	if doc.state == APPROVED:
		frappe.throw(_("Webflow approval {0} was already approved.").format(name))
	restored = _put_back(doc)
	_decide(doc, REJECTED)
	return _result(doc, restored=restored)


@frappe.whitelist()
def get_pending(product):
	"""The Webflow Product form's banner: the Pending approval, and whether this user may decide it."""
	if not frappe.has_permission(PRODUCT, "read", doc=product):
		frappe.throw(_("You can't read this product."), frappe.PermissionError)
	row = pending(product)
	if not row:
		return None
	can_decide = "System Manager" in frappe.get_roles() or bool(
		frappe.has_permission(PRODUCT, "write", doc=product)
	)
	return {**row, "can_decide": can_decide}
