"""Webflow Product changes of 2026-11-05 (plan 4.17).

- Copy each product's existing ``features`` JSON into the new ``web_features`` table, in the
  same order. A product whose JSON cannot be read keeps it as it is and is listed in the log.
- Delete the child rows of the removed product tables: the old Specifications table and
  Compatible Power Supplies (now on the templates).
"""

import frappe

PRODUCT = "ilL-Webflow-Product"
FEATURE = "ilL-Child-Web-Feature"


def execute():
	from illumenate_lighting.illumenate_lighting.webflow_product_rules import feature_rows

	if frappe.db.table_exists(FEATURE):
		filled = set(frappe.get_all(FEATURE, filters={"parenttype": PRODUCT}, pluck="parent", distinct=True))
		unreadable = []
		for product in frappe.get_all(
			PRODUCT, filters={"features": ["is", "set"]}, fields=["name", "features"], limit_page_length=0
		):
			if product.name in filled:
				continue
			rows = feature_rows(product.features)
			if rows is None:
				unreadable.append(product.name)
				continue
			for idx, row in enumerate(rows, start=1):
				frappe.get_doc(
					{
						"doctype": FEATURE,
						"parent": product.name,
						"parenttype": PRODUCT,
						"parentfield": "web_features",
						"idx": idx,
						**row,
					}
				).db_insert()
		if unreadable:
			print("web_features: features JSON could not be read, left as it is: " + ", ".join(unreadable))
			frappe.log_error(
				title="web_features: unreadable features JSON",
				message="\n".join(unreadable),
			)

	for child, field in (
		("ilL-Child-Webflow-Specification", "specifications"),
		("ilL-Child-Comp-Power", "webflow_compatible_power_supplies"),
	):
		if frappe.db.table_exists(child):
			frappe.db.delete(child, {"parenttype": PRODUCT, "parentfield": field})
