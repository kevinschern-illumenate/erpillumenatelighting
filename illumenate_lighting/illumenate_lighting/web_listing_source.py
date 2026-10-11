"""Product data comes from the template; marketing content stays on the Webflow Product.

A Webflow Product linked to a migrated template (one whose Webflow Product backlink
points back at it) takes its product data, such as lengths, feed lengths, spec-sheet
data and kit components, from that template. Everything else, including copy, media,
documents, compatibility, brand targeting, Active and sync state, stays on the Webflow
Product. A listing without a template keeps everything on the Webflow Product.

Templates are where product data is edited. Each template save copies it onto the
linked Webflow Product, so readers that still read it there stay current.

Setting ``web_listing_legacy_read`` to 1 in site config sends every reader back to the
Webflow Product. To compare the two paths from the System Console (``[]`` means no
publication payload changes, so no approval resets):

    print(frappe.call("illumenate_lighting.illumenate_lighting.web_listing_source.payload_parity"))
"""

import json

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_migration import (
	PRODUCT,
	TABLES,
	_listing,
	_migrate_one_safely,
	_rows,
	_same,
	carried,
	template_for,
	template_link,
)
from illumenate_lighting.illumenate_lighting.web_listing_schema import WEBFLOW_PRODUCT_LINKS


def legacy_read():
	return bool(
		getattr(frappe.flags, "web_listing_legacy_read", None) or frappe.conf.get("web_listing_legacy_read")
	)


class Listing:
	"""A Webflow Product whose product data comes from its template once migrated.

	Reads like the Webflow Product document (``get``, attributes, ``as_dict``), so
	readers can take it in place of one. ``source`` is the Webflow Product itself.
	"""

	def __init__(self, product):
		self.source = product
		doctype, name = (None, None) if legacy_read() else template_for(product.name)
		self.template = frappe.get_doc(doctype, name) if doctype else None
		self.fields = set(carried(doctype)) if doctype else set()

	def get(self, key, default=None):
		if key in self.fields:
			value = self.template.get(key)
			if key not in TABLES:
				# Equal values can differ in form (a blank field is "" on one doctype and
				# None on the other); keep the Webflow Product's form so payloads, and the
				# approvals hashed from them, do not change.
				current = self.source.get(key)
				if _same(value, current):
					return current
			return value
		return self.source.get(key, default)

	def __getattr__(self, key):
		if key.startswith("__") or key in ("source", "template", "fields"):
			raise AttributeError(key)
		if key in self.fields:
			return self.get(key)
		return getattr(self.source, key)

	def overlay(self, data):
		"""Replace the product data in a Webflow Product dict with the template's."""
		for field in self.fields:
			if field in data:
				value = self.get(field)
				data[field] = [row.as_dict() for row in value or []] if field in TABLES else value
		return data

	def as_dict(self):
		return self.overlay(self.source.as_dict())


def sync_to_listing(template, method=None):
	"""Copy a template's product data onto its Webflow Product after the template is saved.

	Hooked to on_update of the six templates. Writes go straight to the database; the
	Webflow Product is then marked for review and sync like any edit to it.
	"""
	product = template.get("webflow_product")
	if not product or template_for(product) != (template.doctype, template.name):
		return []
	listing = _listing(product)
	values, changed = {}, []
	for field in carried(template.doctype):
		value = template.get(field)
		if field in TABLES:
			rows = _rows(row.as_dict() for row in value or [])
			if rows == _rows(listing.get(field)):
				continue
			frappe.db.delete(TABLES[field], {"parent": product, "parenttype": PRODUCT, "parentfield": field})
			for idx, row in enumerate(rows, 1):
				frappe.get_doc(
					{
						"doctype": TABLES[field],
						"parent": product,
						"parenttype": PRODUCT,
						"parentfield": field,
						"idx": idx,
						**row,
					}
				).db_insert()
			changed.append(field)
		elif not _same(value, listing.get(field)):
			values[field] = value
	if values:
		frappe.db.set_value(PRODUCT, product, values, update_modified=False)
	if values or changed:
		from illumenate_lighting.illumenate_lighting.api.webflow_sync_events import on_product_update

		on_product_update(frappe.get_doc(PRODUCT, product), "on_update")
	return sorted(changed + list(values))


def top_up_template(product):
	"""Move product data onto a template newly linked from a Webflow Product.

	Called from the Webflow Product's on_update. Only empty template fields are filled,
	as in the migration, so the template stays the place product data is edited.
	"""
	before = product.get_doc_before_save()
	listing = json.loads(frappe.as_json(product.as_dict()))
	doctype, name = template_link(listing)
	if not doctype or (before and before.get(WEBFLOW_PRODUCT_LINKS[doctype]) == name):
		return None
	return _migrate_one_safely(listing, doctype, name, dry_run=0)


def _export(name, brand):
	from illumenate_lighting.illumenate_lighting.api.product_readiness import content_record
	from illumenate_lighting.illumenate_lighting.api.webflow_export import get_webflow_products

	products = get_webflow_products(brand=brand, product_slug=name, limit=1)["products"]
	return content_record(json.loads(frappe.as_json(products[0]))) if products else {}


@frappe.whitelist()
def payload_parity():
	"""Export every migrated listing both ways and list the payload keys that differ."""
	frappe.only_for("System Manager")
	from illumenate_lighting.illumenate_lighting.api.webflow_brand import get_default_brand

	report = []
	for name in frappe.get_all(PRODUCT, pluck="name", order_by="name asc"):
		if not template_for(name)[0]:
			continue
		brands = frappe.get_all("ilL-Product-Publication", filters={"product": name}, pluck="brand")
		for brand in sorted(set(brands)) or [get_default_brand()]:
			current = _export(name, brand)
			frappe.flags.web_listing_legacy_read = True
			try:
				legacy = _export(name, brand)
			finally:
				frappe.flags.web_listing_legacy_read = False
			differences = sorted(key for key in {*current, *legacy} if current.get(key) != legacy.get(key))
			if differences:
				report.append({"listing": name, "brand": brand, "differences": differences})
	return report
