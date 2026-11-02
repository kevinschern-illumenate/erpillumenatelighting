"""Webflow state worked out from the template and the product (plan 4.3, 4.8, D36, D48).

``is_discontinued`` is a read-only check on the Webflow Product, stored on every product save.
A template save saves its linked product (``template_listing.push_to_product``), so a template
status change refreshes it without anyone opening the product.
"""

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_schema import WEBFLOW_PRODUCT_LINKS

PRODUCT = "ilL-Webflow-Product"
PUBLICATION = "ilL-Product-Publication"
DISCONTINUED_STAGE = "Discontinued"
# Template statuses whose page stays up, marked discontinued, once it was published (rows 12, 14).
STAYS_UP_DISCONTINUED = ("Discontinued", "Internal Only")


def discontinued(webflow_status, template_status, published):
	"""Pure (plan 4.3 rows 10, 12, 14). Archived and anything hidden are never discontinued."""
	if template_status == "Archived" or webflow_status == "Archived":
		return False
	if template_status in STAYS_UP_DISCONTINUED:
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
