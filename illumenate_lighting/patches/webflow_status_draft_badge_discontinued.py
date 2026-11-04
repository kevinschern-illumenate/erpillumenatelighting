"""Phase 1b leftovers (plan 4.3, 4.8, D33, D36, D48, owner 2026-11-02).

- The Webflow Status stage "Draft" is merged into "Webflow Draft" (n8n already treated the two
  the same, so nothing changes on the website).
- ``product_badge`` moves to ``webflow_badge`` where the new field is empty. A product whose two
  badges disagree, or whose old badge is "Hide" (no longer an option, owner D50), keeps its
  Web Badge and is listed in one Error Log entry for the owner.
- ``is_discontinued`` gets its first value (stored directly; products are not saved).
"""

import frappe

from illumenate_lighting.illumenate_lighting.webflow_state import discontinued

PRODUCT = "ilL-Webflow-Product"
BADGES = ("New", "On Sale", "Quick Ship")


def execute():
	frappe.db.sql(
		f"update `tab{PRODUCT}` set webflow_status = 'Webflow Draft' where webflow_status = 'Draft'"
	)
	frappe.db.sql(
		f"update `tab{PRODUCT}` set webflow_status = 'Webflow Draft' where ifnull(webflow_status, '') = ''"
	)

	left = []
	if frappe.db.has_column(PRODUCT, "product_badge") and frappe.db.has_column(PRODUCT, "webflow_badge"):
		for row in frappe.get_all(
			PRODUCT,
			filters={"product_badge": ["is", "set"]},
			fields=["name", "product_badge", "webflow_badge"],
			limit_page_length=0,
		):
			old, new = row.product_badge, row.webflow_badge or ""
			if old == new:
				continue
			if not new and old in BADGES:
				frappe.db.set_value(PRODUCT, row.name, "webflow_badge", old, update_modified=False)
			else:
				left.append(f"{row.name}: Product Badge {old!r}, Web Badge {new!r}")
	if left:
		frappe.log_error(title="Product Badge values not moved to Web Badge", message="\n".join(left))

	if frappe.db.has_column(PRODUCT, "is_discontinued"):
		from illumenate_lighting.illumenate_lighting.web_listing_schema import WEBFLOW_PRODUCT_LINKS

		published = set(
			frappe.get_all(
				"ilL-Product-Publication", filters={"published_on": ["is", "set"]}, pluck="product"
			)
		) | set(
			frappe.get_all(
				"ilL-Child-Webflow-Sync-State",
				filters={"parenttype": PRODUCT, "webflow_item_id": ["is", "set"]},
				pluck="parent",
			)
		)
		fields = ["name", "webflow_status", "webflow_item_id", *WEBFLOW_PRODUCT_LINKS.values()]
		for row in frappe.get_all(PRODUCT, fields=fields, limit_page_length=0):
			status = None
			for doctype, field in WEBFLOW_PRODUCT_LINKS.items():
				if row.get(field):
					status = frappe.db.get_value(doctype, row[field], "product_status")
					break
			value = int(
				discontinued(row.webflow_status, status, row.name in published or row.webflow_item_id)
			)
			frappe.db.set_value(PRODUCT, row.name, "is_discontinued", value, update_modified=False)
	frappe.clear_cache(doctype=PRODUCT)
