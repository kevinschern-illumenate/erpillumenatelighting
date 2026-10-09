"""Read web content from the template that carries a listing (merge plan, step 4).

Staff still edit the Webflow Product form until writers switch over, so each save is
mirrored onto the migrated template, and readers take the listing's web content from
the template. A listing that has not been migrated reads from its Webflow Product as
before.

Identity, targeting and sync state (product type, Active, template links, sync rows)
stay on the Webflow Product. So do the attribute links and configurator options, which
the Webflow Product rebuilds from its template on every save; templates start computing
them when writers switch.

Setting ``web_listing_legacy_read`` to 1 in site config sends every reader back to the
Webflow Product. Before relying on the template path, compare the two from the System
Console; ``[]`` means no publication payload changes, so no approval resets:

    print(frappe.call("illumenate_lighting.illumenate_lighting.web_listing_source.payload_parity"))
"""

import json

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_migration import (
	CHILD_DOCTYPES,
	PRODUCT,
	RENAMED,
	SCALARS,
	TABLES,
	_rows,
	_same,
	listing_for,
)
from illumenate_lighting.illumenate_lighting.web_listing_schema import added_fieldnames

COMPUTED = {"attribute_links", "configurator_options"}


def carried(doctype, computed=False):
	"""Webflow Product field -> template field, for the fields one template type carries."""
	added = added_fieldnames(doctype)
	fields = {source: RENAMED.get(source, source) for source in (*SCALARS, *TABLES)}
	return {
		source: target
		for source, target in fields.items()
		if target in added and (computed or source not in COMPUTED)
	}


def legacy_read():
	return bool(
		getattr(frappe.flags, "web_listing_legacy_read", None) or frappe.conf.get("web_listing_legacy_read")
	)


def title(template):
	return template.get("web_title") or template.get("template_name")


class Listing:
	"""A Webflow Product whose web content comes from its template once migrated.

	Reads like the Webflow Product document (``get``, attributes, ``as_dict``), so
	readers can take it in place of one. ``source`` is the Webflow Product itself.
	"""

	def __init__(self, product):
		self.source = product
		doctype, name = (PRODUCT, product.name) if legacy_read() else listing_for(product.name)
		self.template = None if doctype == PRODUCT else frappe.get_doc(doctype, name)
		self.fields = carried(doctype) if self.template else {}

	def get(self, key, default=None):
		if key in self.fields:
			value = self.template.get(self.fields[key])
			if key not in TABLES:
				# Equal values can differ in form (a blank Select is "" on one doctype and
				# None on the other); keep the Webflow Product's form so payloads, and the
				# approvals hashed from them, do not change.
				current = self.source.get(key)
				if _same(value, current):
					return current
			return value
		if key == "product_name" and self.template:
			return title(self.template)
		return self.source.get(key, default)

	def __getattr__(self, key):
		if key.startswith("__") or key in ("source", "template", "fields"):
			raise AttributeError(key)
		if key in self.fields or key == "product_name":
			return self.get(key)
		return getattr(self.source, key)

	def overlay(self, data):
		"""Replace the web content in a Webflow Product dict with the template's."""
		if self.template:
			for source in self.fields:
				if source in data:
					value = self.get(source)
					data[source] = [row.as_dict() for row in value or []] if source in TABLES else value
			if "product_name" in data:
				data["product_name"] = title(self.template)
		return data

	def as_dict(self):
		return self.overlay(self.source.as_dict())


def mirror_to_template(product):
	"""Apply a Webflow Product edit to its migrated template.

	A field is only updated where the template still held the listing's previous value,
	so a value kept on the template on purpose is never overwritten. Writes go straight to
	the database, like the migration, so template controllers and approval hashes are
	not touched.
	"""
	before = product.get_doc_before_save()
	doctype, name = listing_for(product.name)
	if not before or doctype == PRODUCT:
		return []
	template = frappe.get_doc(doctype, name).as_dict()
	values, changed = {}, []
	for source, target in carried(doctype, computed=True).items():
		old, new = before.get(source), product.get(source)
		if source in TABLES:
			old, new = _rows(row.as_dict() for row in old or []), _rows(row.as_dict() for row in new or [])
			if old == new or _rows(template.get(target)) != old:
				continue
			frappe.db.delete(
				CHILD_DOCTYPES[target], {"parent": name, "parenttype": doctype, "parentfield": target}
			)
			for idx, row in enumerate(new, 1):
				frappe.get_doc(
					{
						"doctype": CHILD_DOCTYPES[target],
						"parent": name,
						"parenttype": doctype,
						"parentfield": target,
						"idx": idx,
						**row,
					}
				).db_insert()
			changed.append(target)
		elif not _same(old, new) and _same(template.get(target), old):
			values[target] = new
	if before.get("product_name") != product.get("product_name") and title(template) == before.get(
		"product_name"
	):
		values["web_title"] = (
			product.get("product_name")
			if product.get("product_name") != template.get("template_name")
			else None
		)
	if values:
		frappe.db.set_value(doctype, name, values, update_modified=False)
	return sorted(changed + list(values))


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
		if listing_for(name)[0] == PRODUCT:
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
