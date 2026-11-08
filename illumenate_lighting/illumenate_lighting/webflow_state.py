"""Webflow state worked out from the template and the product (plan 4.3, 4.8, D36, D48).

``is_discontinued`` is a read-only check on the Webflow Product, stored on every product save.
A template save saves its linked product (``template_listing.push_to_product``), so a template
status change refreshes it without anyone opening the product.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.web_listing_schema import WEBFLOW_PRODUCT_LINKS

PRODUCT = "ilL-Webflow-Product"
PUBLICATION = "ilL-Product-Publication"
DISCONTINUED_STAGE = "Discontinued"
# Template statuses whose page stays up, marked discontinued, once it was published (rows 12, 14).
STAYS_UP_DISCONTINUED = ("Discontinued", "Internal Only")
LIVE_STATUS = "Active + Live"
# Template statuses that hide a page that was published (rows 3, 16, D61). An Archived template
# hides the page; only the product's Webflow Status set to Archived archives it in Webflow,
# through the approval (owner, 2026-11-08).
HIDES_WHEN_PUBLISHED = ("Draft", "Active", "Archived")
PUBLIC_STAGES = ("Published", "Discontinued")
WEBFLOW_DRAFT = "Webflow Draft"
ARCHIVED = "Archived"


def discontinued(webflow_status, template_status, published):
	"""Pure (plan 4.3 rows 10, 12, 14; owner 2026-11-02 for an Archived stage).

	An Archived template is never discontinued (its page is hidden, row 16). A product whose
	Webflow Status is Archived is discontinued once it was published (owner, 2026-11-02).
	"""
	if template_status == "Archived":
		return False
	if template_status in STAYS_UP_DISCONTINUED or webflow_status == "Archived":
		return bool(published)
	return webflow_status == DISCONTINUED_STAGE


def published_before(product):
	"""Whether the product has been on Webflow: a publication date, or a Webflow item."""
	if product.get("webflow_item_id") or any(
		row.get("webflow_item_id") for row in product.get("sync_targets") or []
	):
		return True
	if product.is_new():
		return False
	return bool(frappe.db.exists(PUBLICATION, {"product": product.name, "published_on": ["is", "set"]}))


def template_status(product):
	for doctype, field in WEBFLOW_PRODUCT_LINKS.items():
		name = product.get(field)
		if name:
			return frappe.db.get_value(doctype, name, "product_status")
	return None


def set_is_discontinued(product):
	"""Call from the product's before_save."""
	product.is_discontinued = int(
		discontinued(product.get("webflow_status"), template_status(product), published_before(product))
	)


# --- What Webflow shows (owner, 2026-11-08: plan 4.3 table, option b) ---------------------


def effective_status(template_status, webflow_status, published):
	"""Pure: the Webflow Status a push uses, from the template's Product Status, the product's
	own Webflow Status and whether the page was ever published.

	The product's field is never changed by this; the template wins when it is not Active + Live.
	Returns (status, rule): ``status`` None means nothing goes to Webflow; ``rule`` names why the
	template changed it (None when the product's own status applies).
	"""
	if webflow_status == ARCHIVED:
		return ARCHIVED, None
	if not template_status or template_status == LIVE_STATUS:
		return webflow_status, None
	if not published:
		return None, "never_published"
	if template_status in STAYS_UP_DISCONTINUED:
		# A public page stays up as Discontinued (rows 12, 14); a hidden one stays hidden.
		if webflow_status in PUBLIC_STAGES:
			return DISCONTINUED_STAGE, "stays_up"
		return webflow_status, None
	if template_status in HIDES_WHEN_PUBLISHED:
		return WEBFLOW_DRAFT, "hidden"
	return None, "unknown_template_status"


def describe_effective(template_status, webflow_status, status, rule):
	"""Pure: the product form's line, or None when the product's own Webflow Status applies."""
	if rule is None:
		return None
	if rule == "never_published":
		return _("Nothing goes to Webflow: the template is {0} and this page was never published.").format(
			template_status
		)
	if rule == "unknown_template_status":
		return _("Nothing goes to Webflow: the template status {0} is not known.").format(template_status)
	return _("Shown on Webflow as {0}, because the template is {1} (Webflow Status here: {2}).").format(
		status, template_status, webflow_status or _("not set")
	)


def linked_product(template):
	"""The template's Webflow Product, when both sides point at each other."""
	product = template.get("webflow_product")
	if not product or not frappe.db.exists(PRODUCT, product):
		return None
	field = WEBFLOW_PRODUCT_LINKS.get(template.doctype)
	if not field or frappe.db.get_value(PRODUCT, product, field) != template.name:
		return None
	return product


def ever_published(product):
	return bool(frappe.db.exists(PUBLICATION, {"product": product, "published_on": ["is", "set"]}))


def on_template_update(template, method=None):
	"""Template on_update: a Product Status change on a page that was published.

	- Draft, Active (from Active + Live) or Archived: the page is hidden; the notification list
	  is told. Archiving it in Webflow is the product's Webflow Status, with its approval.
	- Back to Active + Live from Discontinued or Archived: the product's Webflow Status is reset to
	  Webflow Draft (D5); going public again needs a person to set it to Published.
	The push itself is the product's automatic push (the template save saves the product).
	"""
	before = template.get_doc_before_save()
	old, new = (before.get("product_status") if before else None), template.get("product_status")
	if not before or old == new:
		return
	product = linked_product(template)
	if not product or not ever_published(product):
		return
	stage = frappe.db.get_value(PRODUCT, product, "webflow_status")
	if new in HIDES_WHEN_PUBLISHED and old not in HIDES_WHEN_PUBLISHED and stage in PUBLIC_STAGES:
		from illumenate_lighting.illumenate_lighting import webflow_notify

		webflow_notify.notify(
			_("Webflow page will be hidden: {0}").format(product),
			_(
				"Template {0} was set to {1}, so the published page of {2} is hidden (Webflow Draft) at its "
				"next push. Set the template back to Active + Live to show it again, or set the product's "
				"Webflow Status to Archived to archive the page."
			).format(template.name, new, product),
			PRODUCT,
			product,
		)
	elif new == LIVE_STATUS and old in ("Discontinued", ARCHIVED) and stage in PUBLIC_STAGES:
		frappe.db.set_value(PRODUCT, product, "webflow_status", WEBFLOW_DRAFT)
		frappe.msgprint(
			_(
				"Webflow Status of {0} reset to Webflow Draft: the page stays hidden until it is set to "
				"Published."
			).format(product),
			indicator="orange",
			alert=True,
		)
