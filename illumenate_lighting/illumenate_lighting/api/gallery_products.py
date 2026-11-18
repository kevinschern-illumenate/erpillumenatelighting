# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""A product's Webflow item ID in one brand, for galleries (docs/WEBFLOW_GALLERY_SYNC.md, section 6a).

Shared by the gallery publication service and the gallery import. Reads product records only.
"""

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint
from illumenate_lighting.illumenate_lighting.api.webflow_brand import get_default_brand

PRODUCT = "ilL-Webflow-Product"
PRODUCT_PUBLICATION = "ilL-Product-Publication"
SYNC_STATE = "ilL-Child-Webflow-Sync-State"


def product_item_id(product, brand, default_brand=None):
	"""Return the product's Webflow item ID in `brand`, or None.

	Order: (1) the product publication record's ``remote_item_id`` (scope key as in
	``api/publication.py``), (2) the product's sync-state row for the brand whatever its
	``sync_status`` (every product save sets it to Pending), (3) the product's own
	``webflow_item_id`` when `brand` is the default brand. `default_brand` saves a lookup in loops.
	"""
	if not product or not brand:
		return None
	key = fingerprint([product, brand])
	item_id = frappe.db.get_value(PRODUCT_PUBLICATION, {"scope_key": key}, "remote_item_id")
	if item_id:
		return item_id
	item_id = frappe.db.get_value(
		SYNC_STATE, {"parent": product, "parenttype": PRODUCT, "brand": brand}, "webflow_item_id"
	)
	if item_id:
		return item_id
	if brand == (default_brand or get_default_brand()):
		return frappe.db.get_value(PRODUCT, product, "webflow_item_id") or None
	return None
