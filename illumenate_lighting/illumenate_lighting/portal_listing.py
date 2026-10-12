"""Which Webflow Products the dealer portal shows.

A product linked to a template is on the portal when that template's Product Status is
Active, whether or not it is live on the website. ERPNext Only keeps it usable in
ERPNext but off the portal; Draft, Discontinued and Archived keep it off too. A listing
without a template (accessories and the other standalone listings) still follows its
Webflow Product's Active flag.

To see which products the switch shows or hides, from the System Console:

    print(frappe.call("illumenate_lighting.illumenate_lighting.portal_listing.visibility_changes"))
"""

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_migration import LINK_FIELDS, PRODUCT, template_link

PORTAL_STATUS = "Active"


def on_portal(product, status_of=None):
	"""Whether a Webflow Product (doc or dict) is shown on the portal.

	``status_of(doctype, name)`` returns a template's Product Status; pass one that reads
	preloaded rows when checking many products.
	"""
	doctype, name = template_link(product)
	if not doctype:
		return bool(int(product.get("is_active") or 0))
	status_of = status_of or (lambda doctype, name: frappe.db.get_value(doctype, name, "product_status"))
	return status_of(doctype, name) == PORTAL_STATUS


def portal_condition(table="`tabilL-Webflow-Product`"):
	"""SQL condition matching ``on_portal`` for rows of the Webflow Product table."""
	linked = [
		f"(ifnull({table}.{field}, '') != '' and exists(select 1 from `tab{doctype}` portal_template"
		f" where portal_template.name = {table}.{field}"
		f" and portal_template.product_status = '{PORTAL_STATUS}'))"
		for field, doctype in LINK_FIELDS.items()
	]
	unlinked = " and ".join(f"ifnull({table}.{field}, '') = ''" for field in LINK_FIELDS)
	return "(" + " or ".join([*linked, f"({unlinked} and {table}.is_active = 1)"]) + ")"


def portal_product(filters):
	"""The Webflow Product matching ``filters`` if the portal shows it, else None."""
	name = frappe.db.get_value(PRODUCT, filters, "name")
	if not name:
		return None
	product = frappe.get_doc(PRODUCT, name)
	return product if on_portal(product) else None


@frappe.whitelist()
def visibility_changes():
	"""Products the portal shows or hides now that template status decides, versus Active."""
	frappe.only_for("System Manager")
	changes = []
	for row in frappe.get_all(PRODUCT, fields=["name", "is_active", *LINK_FIELDS], order_by="name asc"):
		shown = on_portal(row)
		if shown != bool(row.is_active):
			doctype, name = template_link(row)
			status = frappe.db.get_value(doctype, name, "product_status") if doctype else None
			changes.append(
				{
					"listing": row.name,
					"now": "shown" if shown else "hidden",
					"template": f"{doctype} {name}" if doctype else None,
					"product_status": status,
				}
			)
	return changes
