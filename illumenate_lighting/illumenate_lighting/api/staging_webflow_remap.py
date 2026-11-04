# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Point staging at its own Webflow site (owner, 2026-11-04).

Staging has its own Webflow site now (``staging-illumenate.webflow.io``), a copy of the main
site. A copied site gives every CMS item a new ID, so the Webflow item IDs stored on staging
(products and categories, for one brand) are replaced by the new site's IDs, matched as below.

- Product: the Webflow item whose ``erp-sync-id`` is the product name, else whose slug is the
  product slug. The product's sync row for the brand, its publication record and (default brand)
  its own Webflow Item ID get the new ID. The publication's staged and live hashes are cleared so
  the next sync sends a full update, and Published On is the item's last publish date.
  A product with no match has its stored ID cleared, so its next sync creates a new item.
- Category: the Webflow item whose slug is the category slug, else whose name is the category
  name. The category's sync row for the brand gets the new ID as Synced, and (default brand)
  its own Webflow Item ID.

The one-off n8n workflow ``[STAGING] Webflow ID remap`` reads the new site's items and posts them
here. Staging only (site config ``webflow_environment`` is ``staging``); dry run by default.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api import n8n_config

PRODUCT = "ilL-Webflow-Product"
CATEGORY = "ilL-Webflow-Category"
PUBLICATION = "ilL-Product-Publication"
SYNC_STATE = "ilL-Child-Webflow-Sync-State"


def _text(value):
	return str(value or "").strip()


def _index(items, *keys):
	"""{key value: item} for each key, first item wins."""
	found = {key: {} for key in keys}
	for item in items:
		for key in keys:
			value = _text(item.get(key)).lower()
			if value:
				found[key].setdefault(value, item)
	return found


def match_products(products, items):
	"""Pair ERPNext products ({name, product_slug, current}) with Webflow items
	({id, erp_sync_id, slug, name, last_published}). Returns matched, unmatched and unused."""
	index = _index(items, "erp_sync_id", "slug")
	matched, unmatched, used = [], [], set()
	for product in products:
		item = index["erp_sync_id"].get(_text(product["name"]).lower()) or index["slug"].get(
			_text(product.get("product_slug")).lower()
		)
		if item:
			used.add(item["id"])
			matched.append({**product, "item": item})
		else:
			unmatched.append(product)
	unused = [item for item in items if item["id"] not in used]
	return matched, unmatched, unused


def match_categories(categories, items):
	"""Pair ERPNext categories ({name, category_slug, category_name}) with Webflow items."""
	index = _index(items, "slug", "name")
	matched, unmatched, used = [], [], set()
	for category in categories:
		item = index["slug"].get(_text(category.get("category_slug")).lower()) or index["name"].get(
			_text(category.get("category_name") or category["name"]).lower()
		)
		if item:
			used.add(item["id"])
			matched.append({**category, "item": item})
		else:
			unmatched.append(category)
	unused = [item for item in items if item["id"] not in used]
	return matched, unmatched, unused


def _items(value):
	value = frappe.parse_json(value) if isinstance(value, str) else value
	return [
		{
			"id": _text(item.get("id")),
			"erp_sync_id": _text(item.get("erp_sync_id")),
			"slug": _text(item.get("slug")),
			"name": _text(item.get("name")),
			"last_published": item.get("last_published") or None,
		}
		for item in (value or [])
		if _text(item.get("id"))
	]


def _datetime(value):
	if not value:
		return None
	from frappe.utils import get_datetime

	return get_datetime(str(value).replace("Z", "").replace("T", " ")[:19])


def _set_sync_row(doctype, name, brand, item_id, status):
	row = frappe.db.get_value(SYNC_STATE, {"parenttype": doctype, "parent": name, "brand": brand}, "name")
	values = {"webflow_item_id": item_id, "sync_status": status, "sync_error_message": None}
	if row:
		frappe.db.set_value(SYNC_STATE, row, values, update_modified=False)
		return
	if not item_id:
		return
	# A new child row inserted directly, so no save hooks (and no Webflow push) run.
	frappe.get_doc(
		{
			"doctype": SYNC_STATE,
			"parent": name,
			"parenttype": doctype,
			"parentfield": "sync_targets",
			"brand": brand,
			**values,
		}
	).db_insert()


@frappe.whitelist(methods=["POST"])
def remap_webflow_ids(products=None, categories=None, brand="illumenate", apply=False):
	"""Replace stored Webflow item IDs with the staging site's. Returns a report.

	``products`` and ``categories`` are the staging site's items as
	``[{id, erp_sync_id, slug, name, last_published}]``. ``apply`` (default False) writes.
	"""
	frappe.only_for("System Manager")
	if not n8n_config.is_staging():
		frappe.throw(
			_("This only runs on a staging site. Site config {0} must be 'staging'.").format(
				n8n_config.ENVIRONMENT_KEY
			)
		)
	apply = frappe.parse_json(apply) if isinstance(apply, str) else bool(apply)
	from illumenate_lighting.illumenate_lighting.api.webflow_brand import get_default_brand, resolve_brand

	brand = resolve_brand(brand, allow_inactive=True)["brand_code"]
	is_default = brand == get_default_brand()
	product_items, category_items = _items(products), _items(categories)
	if not product_items and not category_items:
		frappe.throw(_("No Webflow items were sent."))

	current = {
		row.parent: row.webflow_item_id
		for row in frappe.get_all(
			SYNC_STATE,
			filters={"parenttype": PRODUCT, "brand": brand},
			fields=["parent", "webflow_item_id"],
			limit_page_length=0,
		)
	}
	erp_products = [
		{
			"name": row.name,
			"product_slug": row.product_slug,
			"current": current.get(row.name) or row.webflow_item_id,
		}
		for row in frappe.get_all(
			PRODUCT, fields=["name", "product_slug", "webflow_item_id"], limit_page_length=0
		)
	]
	erp_categories = frappe.get_all(
		CATEGORY, fields=["name", "category_slug", "category_name"], limit_page_length=0
	)
	p_matched, p_unmatched, p_unused = (
		match_products(erp_products, product_items) if product_items else ([], [], [])
	)
	c_matched, c_unmatched, c_unused = (
		match_categories(erp_categories, category_items) if category_items else ([], [], [])
	)
	cleared = [p for p in p_unmatched if p.get("current")] if product_items else []

	report = {
		"applied": apply,
		"brand": brand,
		"products": {
			"matched": [
				{"product": p["name"], "new_id": p["item"]["id"], "old_id": p.get("current")}
				for p in p_matched
			],
			"cleared": [{"product": p["name"], "old_id": p["current"]} for p in cleared],
			"not_on_staging_site": [p["name"] for p in p_unmatched if not p.get("current")],
			"webflow_items_without_product": [
				{"id": i["id"], "slug": i["slug"], "name": i["name"]} for i in p_unused
			],
		},
		"categories": {
			"matched": [{"category": c["name"], "new_id": c["item"]["id"]} for c in c_matched],
			"not_on_staging_site": [c["name"] for c in c_unmatched],
			"webflow_items_without_category": [
				{"id": i["id"], "slug": i["slug"], "name": i["name"]} for i in c_unused
			],
		},
	}
	report["counts"] = {
		f"{group}.{key}": len(value)
		for group in ("products", "categories")
		for key, value in report[group].items()
	}
	if not apply:
		return report

	publications = {
		row.product: row.name
		for row in frappe.get_all(
			PUBLICATION, filters={"brand": brand}, fields=["name", "product"], limit_page_length=0
		)
	}
	for product in p_matched + cleared:
		item = product.get("item") or {}
		item_id = item.get("id")
		_set_sync_row(PRODUCT, product["name"], brand, item_id, "Pending" if item_id else "Never Synced")
		if is_default:
			frappe.db.set_value(
				PRODUCT,
				product["name"],
				{"webflow_item_id": item_id, "sync_status": "Pending" if item_id else "Never Synced"},
				update_modified=False,
			)
		if publications.get(product["name"]):
			frappe.db.set_value(
				PUBLICATION,
				publications[product["name"]],
				{
					"remote_item_id": item_id,
					"staged_hash": None,
					"staged_on": None,
					"live_hash": None,
					"published_on": _datetime(item.get("last_published")),
					"state": "NEEDS_REVIEW",
				},
				update_modified=False,
			)
	for category in c_matched:
		_set_sync_row(CATEGORY, category["name"], brand, category["item"]["id"], "Synced")
		if is_default:
			frappe.db.set_value(
				CATEGORY,
				category["name"],
				{"webflow_item_id": category["item"]["id"], "sync_status": "Synced"},
				update_modified=False,
			)
	frappe.db.commit()
	frappe.logger("webflow").info({"event": "staging_webflow_remap", "counts": report["counts"]})
	return report
