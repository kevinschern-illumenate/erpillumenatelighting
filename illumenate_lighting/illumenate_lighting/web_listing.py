"""Validation for the Web Listing fields on product templates.

A ``web_slug`` names one product page across the whole catalog, so it must be
unique across all six template doctypes and must not belong to a Webflow Product
that describes a different product.
"""

import re

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	TEMPLATE_DOCTYPES,
	WEBFLOW_PRODUCT_LINKS,
)

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_web_listing(doc):
	"""Normalise and check the Web Listing fields; call from each template's validate()."""
	slug = (getattr(doc, "web_slug", None) or "").strip().lower()
	doc.web_slug = slug or None
	if not slug:
		if getattr(doc, "web_listed", None):
			frappe.throw(_("Set a Web Slug before listing this template on the web"))
		return
	if not SLUG.match(slug):
		frappe.throw(
			_("Web Slug {0} may only contain lowercase letters, digits and single hyphens").format(slug)
		)
	for doctype in TEMPLATE_DOCTYPES:
		filters = {"web_slug": slug}
		if doctype == doc.doctype:
			filters["name"] = ["!=", doc.name]
		owner = frappe.db.get_value(doctype, filters, "name")
		if owner:
			frappe.throw(_("Web Slug {0} is already used by {1} {2}").format(slug, doctype, owner))
	# During the transition an old Webflow Product with this slug may be unlinked (templates
	# being rebuilt) or linked to this template, but not linked to a different one.
	link_field = WEBFLOW_PRODUCT_LINKS[doc.doctype]
	linked = frappe.db.get_value("ilL-Webflow-Product", slug, link_field)
	if linked and linked != doc.name:
		frappe.throw(_("Web Slug {0} belongs to a Webflow Product linked to {1}").format(slug, linked))
