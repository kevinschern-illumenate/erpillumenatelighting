"""Keep only product data on the templates (Webflow Product merge, revised 2026-10-11).

The Webflow Product stays as the marketing record, so the marketing tables the first
migration copied onto templates are removed, every template gets a Product Status
matching its Active flag, and publication records point back at their Webflow Product.
Every row removed here is a copy; the Webflow Product still holds the original.
"""

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_schema import TEMPLATE_DOCTYPES

# Template tables the first release added and the revised plan leaves on the Webflow Product.
MARKETING_TABLES = {
	"gallery_images": "ilL-Child-Webflow-Gallery-Image",
	"documents": "ilL-Child-Webflow-Document",
	"web_certifications": "ilL-Child-Webflow-Certification-Link",
	"compatible_products": "ilL-Child-Webflow-Compatibility",
	"target_brands": "ilL-Child-Webflow-Brand-Target",
	"attribute_links": "ilL-Child-Webflow-Attribute-Link",
	"configurator_options": "ilL-Child-Webflow-Configurator-Option",
}
PUBLICATION_DOCTYPES = ("ilL-Product-Publication", "ilL-Publish-Job", "ilL-Product-Verification-Request")


def execute():
	for fieldname, child in MARKETING_TABLES.items():
		frappe.db.delete(child, {"parenttype": ["in", list(TEMPLATE_DOCTYPES)], "parentfield": fieldname})
	for doctype in TEMPLATE_DOCTYPES:
		table = f"`tab{doctype}`"
		frappe.db.sql(
			f"""update {table} set product_status = if(is_active, 'Active', 'Draft')
			where ifnull(product_status, '') = ''"""
		)
	for doctype in PUBLICATION_DOCTYPES:
		frappe.db.sql(
			f"""update `tab{doctype}` set listing_doctype = 'ilL-Webflow-Product', listing_name = product
			where ifnull(product, '') != ''"""
		)
