"""Consistency report and one-time migration for the template link flip (plan 4.2, Phase 1a).

Before Phase 1a the product owned the link and wrote the template's ``webflow_product``
backlink. Now the template owns it. This report checks both sides agree on every site
and fills what can be filled safely. Dry run is the default::

    bench --site <site> execute \\
        illumenate_lighting.illumenate_lighting.template_link_report.link_consistency_report

    bench --site <site> execute \\
        illumenate_lighting.illumenate_lighting.template_link_report.link_consistency_report \\
        --kwargs "{'apply': True}"

``apply`` only does four things, all without running save hooks:

- sets a template's empty ``webflow_product`` where exactly one product links it;
- sets a product's empty link field where the template points at it and the product
  links no other template;
- clears the link field of a product that claims a template whose own link points at a
  different product (the template owns the link, D2);
- seeds an empty template ``target_brands`` from its product when the product has exactly
  one enabled brand (D17, D22).

Everything else is listed for the owner and left alone: conflicting links, type
mismatches, Active templates without a product, ambiguous brands, duplicate record names,
and products whose category or series would change once they mirror the template (D55).
"""

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	TEMPLATE_DOCTYPES,
	WEBFLOW_PRODUCT_LINK_TYPES,
	WEBFLOW_PRODUCT_LINKS,
)

PRODUCT = "ilL-Webflow-Product"
BRAND_TARGET = "ilL-Child-Webflow-Brand-Target"
TAPE = "ilL-Tape-Neon-Template"


def _brands(parenttype):
	"""{parent: enabled brands}; a parent with rows but none enabled maps to []."""
	by_parent = {}
	for row in frappe.get_all(
		BRAND_TARGET,
		filters={"parenttype": parenttype, "parentfield": "target_brands"},
		fields=["parent", "brand", "enabled"],
		limit_page_length=0,
	):
		brands = by_parent.setdefault(row.parent, [])
		if row.enabled and row.brand:
			brands.append(row.brand)
	return by_parent


def build_report(products, templates, product_brands, template_brands, default_brand=None):
	"""Pure: compare both sides and plan the safe fixes.

	``products``: rows with name, product_type, product_category, series and the six link fields.
	``templates``: {doctype: rows with name, webflow_product, product_status, product_category,
	series and, for Tape/Neon, webflow_category}.
	``product_brands`` / ``template_brands``: {name: enabled brands}, a name absent when it has no
	Target Brand rows at all. A product with no rows syncs to ``default_brand`` today
	(publication._targeted), so that is the brand its template is seeded with.
	"""
	report = {
		"consistent": [],
		"set_template_link": [],
		"set_product_link": [],
		"clear_product_link": [],
		"seed_template_brand": [],
		"seed_template_category_series": [],
		"suggested_links": [],
		"conflicts": [],
		"active_without_product": [],
		"brand_needs_owner": [],
		"category_series_conflicts": [],
		"duplicate_names": [],
	}
	product_by_name = {row["name"]: row for row in products}
	template_rows = {(doctype, row["name"]): row for doctype, rows in templates.items() for row in rows}

	# Who claims what, from each side.
	claimed_by_products = {}
	for product in products:
		links = [
			(doctype, product[fieldname])
			for doctype, fieldname in WEBFLOW_PRODUCT_LINKS.items()
			if product.get(fieldname)
		]
		if len(links) > 1:
			report["conflicts"].append(
				{"product": product["name"], "issue": "links more than one template", "templates": links}
			)
			continue
		for key in links:
			claimed_by_products.setdefault(key, []).append(product["name"])
	claimed_by_templates = {}
	for key, row in template_rows.items():
		if row.get("webflow_product"):
			claimed_by_templates.setdefault(row["webflow_product"], []).append(key)

	pairs = {}
	unlinked = []
	for product, keys in claimed_by_templates.items():
		if len(keys) > 1:
			report["conflicts"].append(
				{"product": product, "issue": "claimed by more than one template", "templates": sorted(keys)}
			)
	for key, row in sorted(template_rows.items()):
		doctype, name = key
		fieldname = WEBFLOW_PRODUCT_LINKS[doctype]
		backlink = row.get("webflow_product")
		claimants = claimed_by_products.get(key, [])
		if len(claimants) > 1 and backlink in claimants:
			# The template owns the link (D2): the products it does not point at lose theirs.
			for other in sorted(set(claimants) - {backlink}):
				report["clear_product_link"].append({"template": key, "product": other, "field": fieldname})
			claimants = [backlink]
		if len(claimants) > 1:
			report["conflicts"].append(
				{
					"template": key,
					"issue": "linked from more than one product",
					"products": sorted(claimants),
					"webflow_product": backlink,
				}
			)
			continue
		product_name = backlink or (claimants[0] if claimants else None)
		if not product_name:
			unlinked.append(key)
			continue
		product = product_by_name.get(product_name)
		if not product:
			report["conflicts"].append({"template": key, "issue": f"links missing product {product_name}"})
			continue
		if backlink and claimants and claimants[0] != backlink:
			report["conflicts"].append(
				{
					"template": key,
					"issue": "template and product disagree",
					"webflow_product": backlink,
					"linked_from": claimants[0],
				}
			)
			continue
		if len(claimed_by_templates.get(product_name, [])) > 1:
			continue  # already reported
		if product.get("product_type") not in WEBFLOW_PRODUCT_LINK_TYPES[fieldname]:
			report["conflicts"].append(
				{
					"template": key,
					"product": product_name,
					"issue": f"product type {product.get('product_type')!r} does not fit",
				}
			)
			continue
		if not backlink:
			report["set_template_link"].append({"template": key, "webflow_product": product_name})
		elif product.get(fieldname) != name:
			other = [f for f in WEBFLOW_PRODUCT_LINK_TYPES if f != fieldname and product.get(f)]
			if product.get(fieldname) or other:
				report["conflicts"].append(
					{"template": key, "product": product_name, "issue": "product links another template"}
				)
				continue
			report["set_product_link"].append({"template": key, "product": product_name, "field": fieldname})
		else:
			report["consistent"].append({"template": key, "product": product_name})
		pairs[key] = product_name

	# Templates linked from neither side: suggest the product with the same name (any case)
	# when it is free too and its type fits. Applied only on request (link_suggestions).
	claimed = (
		set(pairs.values())
		| set(claimed_by_templates)
		| {name for names in claimed_by_products.values() for name in names}
	)
	free_products = {
		row["name"].lower(): row
		for row in products
		if row["name"] not in claimed and not any(row.get(f) for f in WEBFLOW_PRODUCT_LINK_TYPES)
	}
	for key in unlinked:
		doctype, name = key
		row = template_rows[key]
		match = free_products.get(name.lower())
		fieldname = WEBFLOW_PRODUCT_LINKS[doctype]
		if match and match.get("product_type") in WEBFLOW_PRODUCT_LINK_TYPES[fieldname]:
			report["suggested_links"].append(
				{
					"template": key,
					"product": match["name"],
					"field": fieldname,
					"product_status": row.get("product_status"),
				}
			)
		elif row.get("product_status") == "Active":
			report["active_without_product"].append({"template": key})

	for key, product_name in pairs.items():
		doctype, name = key
		row = template_rows[key]
		product = product_by_name[product_name]
		template_brand = template_brands.get(key)
		if not template_brand:
			if product_name in product_brands:
				brands = product_brands[product_name]
				source = "product"
			else:
				brands = [default_brand] if default_brand else []
				source = "default brand (the product has no Target Brand rows)"
			if len(brands) == 1:
				report["seed_template_brand"].append({"template": key, "brand": brands[0], "from": source})
			else:
				report["brand_needs_owner"].append(
					{"template": key, "product": product_name, "product_brands": brands}
				)
		elif len(template_brand) > 1:
			report["brand_needs_owner"].append({"template": key, "template_brands": template_brand})
		# D55: the product will mirror the template. Fill empty template fields from the product
		# (nothing on the product changes); list real disagreements for the owner.
		category_field = "webflow_category" if doctype == TAPE else "product_category"
		seed, conflicts = {}, {}
		for template_field, product_field in ((category_field, "product_category"), ("series", "series")):
			template_value = row.get(template_field) or None
			product_value = product.get(product_field) or None
			if template_value == product_value or product_value is None:
				continue  # nothing changes, or the product just gains the template's value
			if template_value is None:
				seed[template_field] = product_value
			else:
				conflicts[product_field] = [product_value, template_value]
		if seed:
			report["seed_template_category_series"].append({"template": key, "values": seed})
		if conflicts:
			report["category_series_conflicts"].append(
				{"template": key, "product": product_name, "product_then_template": conflicts}
			)

	seen = {}
	for doctype, name in template_rows:
		seen.setdefault(name.lower(), []).append((doctype, name))
	report["duplicate_names"] = [sorted(keys) for keys in seen.values() if len(keys) > 1]
	report["counts"] = {key: len(value) for key, value in report.items() if isinstance(value, list)}
	return report


@frappe.whitelist(methods=["POST"])
def link_consistency_report(apply=False, link_suggestions=False):
	"""Report (and with ``apply``, fill) the template link on both sides. System Manager only.

	``link_suggestions`` also links the same-name pairs in ``suggested_links``.
	"""
	frappe.only_for("System Manager")
	apply = frappe.parse_json(apply) if isinstance(apply, str) else bool(apply)
	link_suggestions = (
		frappe.parse_json(link_suggestions) if isinstance(link_suggestions, str) else bool(link_suggestions)
	)
	link_fields = list(WEBFLOW_PRODUCT_LINK_TYPES)
	products = frappe.get_all(
		PRODUCT,
		fields=["name", "product_type", "product_category", "series", *link_fields],
		limit_page_length=0,
	)
	templates = {}
	template_brands = {}
	for doctype in TEMPLATE_DOCTYPES:
		fields = ["name", "webflow_product", "product_status", "product_category", "series"]
		if doctype == TAPE:
			fields.append("webflow_category")
		templates[doctype] = frappe.get_all(doctype, fields=fields, limit_page_length=0)
		template_brands.update({(doctype, name): brands for name, brands in _brands(doctype).items()})
	from illumenate_lighting.illumenate_lighting.api.webflow_brand import get_default_brand

	report = build_report(products, templates, _brands(PRODUCT), template_brands, get_default_brand())
	report["applied"] = apply
	report["linked_suggestions"] = link_suggestions
	if link_suggestions:
		# Only the link; run the report again with apply to seed brands and categories.
		for row in report["suggested_links"]:
			doctype, name = row["template"]
			frappe.db.set_value(doctype, name, "webflow_product", row["product"], update_modified=False)
			frappe.db.set_value(PRODUCT, row["product"], row["field"], name, update_modified=False)
	if not apply:
		if link_suggestions:
			frappe.db.commit()
		return report

	for row in report["set_template_link"]:
		doctype, name = row["template"]
		frappe.db.set_value(doctype, name, "webflow_product", row["webflow_product"], update_modified=False)
	for row in report["set_product_link"]:
		frappe.db.set_value(PRODUCT, row["product"], row["field"], row["template"][1], update_modified=False)
	for row in report["clear_product_link"]:
		frappe.db.set_value(PRODUCT, row["product"], row["field"], None, update_modified=False)
	for row in report["seed_template_category_series"]:
		doctype, name = row["template"]
		frappe.db.set_value(doctype, name, row["values"], update_modified=False)
	for row in report["seed_template_brand"]:
		doctype, name = row["template"]
		frappe.get_doc(
			{
				"doctype": BRAND_TARGET,
				"parent": name,
				"parenttype": doctype,
				"parentfield": "target_brands",
				"idx": 1,
				"brand": row["brand"],
				"enabled": 1,
			}
		).db_insert()
	frappe.db.commit()
	return report
