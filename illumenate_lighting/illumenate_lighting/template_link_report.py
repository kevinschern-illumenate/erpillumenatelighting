"""Consistency report and one-time migration for the template link flip (plan 4.2, Phase 1a).

Before Phase 1a the product owned the link and wrote the template's ``webflow_product``
backlink. Now the template owns it. This report checks both sides agree on every site
and fills what can be filled safely. Dry run is the default::

    bench --site <site> execute \\
        illumenate_lighting.illumenate_lighting.template_link_report.link_consistency_report

    bench --site <site> execute \\
        illumenate_lighting.illumenate_lighting.template_link_report.link_consistency_report \\
        --kwargs "{'apply': True}"

``apply`` only does three things, all without running save hooks:

- sets a template's empty ``webflow_product`` where exactly one product links it;
- sets a product's empty link field where the template points at it and the product
  links no other template;
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
	by_parent = {}
	for row in frappe.get_all(
		BRAND_TARGET,
		filters={"parenttype": parenttype, "parentfield": "target_brands"},
		fields=["parent", "brand", "enabled"],
		limit_page_length=0,
	):
		if row.enabled and row.brand:
			by_parent.setdefault(row.parent, []).append(row.brand)
	return by_parent


def build_report(products, templates, product_brands, template_brands):
	"""Pure: compare both sides and plan the safe fixes.

	``products``: rows with name, product_type, product_category, series and the six link fields.
	``templates``: {doctype: rows with name, webflow_product, product_status, product_category,
	series and, for Tape/Neon, webflow_category}.
	"""
	report = {
		"consistent": [],
		"set_template_link": [],
		"set_product_link": [],
		"seed_template_brand": [],
		"conflicts": [],
		"active_without_product": [],
		"brand_needs_owner": [],
		"category_series_changes": [],
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
		if len(claimants) > 1:
			report["conflicts"].append(
				{"template": key, "issue": "linked from more than one product", "products": sorted(claimants)}
			)
			continue
		product_name = backlink or (claimants[0] if claimants else None)
		if not product_name:
			if row.get("product_status") == "Active":
				report["active_without_product"].append({"template": key})
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

	for key, product_name in pairs.items():
		doctype, name = key
		row = template_rows[key]
		product = product_by_name[product_name]
		if not template_brands.get(name):
			brands = product_brands.get(product_name, [])
			if len(brands) == 1:
				report["seed_template_brand"].append({"template": key, "brand": brands[0]})
			else:
				report["brand_needs_owner"].append(
					{"template": key, "product": product_name, "product_brands": brands}
				)
		elif len(template_brands[name]) > 1:
			report["brand_needs_owner"].append({"template": key, "template_brands": template_brands[name]})
		category = row.get("webflow_category") if doctype == TAPE else row.get("product_category")
		changes = {}
		if (category or None) != (product.get("product_category") or None):
			changes["product_category"] = [product.get("product_category"), category]
		if (row.get("series") or None) != (product.get("series") or None):
			changes["series"] = [product.get("series"), row.get("series")]
		if changes:
			report["category_series_changes"].append(
				{"template": key, "product": product_name, "from_to": changes}
			)

	seen = {}
	for doctype, name in template_rows:
		seen.setdefault(name.lower(), []).append((doctype, name))
	report["duplicate_names"] = [sorted(keys) for keys in seen.values() if len(keys) > 1]
	report["counts"] = {key: len(value) for key, value in report.items() if isinstance(value, list)}
	return report


@frappe.whitelist(methods=["POST"])
def link_consistency_report(apply=False):
	"""Report (and with ``apply``, fill) the template link on both sides. System Manager only."""
	frappe.only_for("System Manager")
	apply = frappe.parse_json(apply) if isinstance(apply, str) else bool(apply)
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
		template_brands.update(_brands(doctype))
	report = build_report(products, templates, _brands(PRODUCT), template_brands)
	report["applied"] = apply
	if not apply:
		return report

	for row in report["set_template_link"]:
		doctype, name = row["template"]
		frappe.db.set_value(doctype, name, "webflow_product", row["webflow_product"], update_modified=False)
	for row in report["set_product_link"]:
		frappe.db.set_value(PRODUCT, row["product"], row["field"], row["template"][1], update_modified=False)
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
