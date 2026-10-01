"""Desk endpoints for staff editing Product Finder content."""

import frappe

from illumenate_lighting.illumenate_lighting.portal.product_finder.facets import COMPARISONS, FACETS

EDITOR_ROLES = (
	"System Manager",
	"ilL Product Finder Manager",
	"ilL Catalog Publisher",
	"ilL Sales Review",
	"ilL Engineering",
)


@frappe.whitelist()
def facet_registry() -> dict:
	"""Facets with the ERP DocTypes and comparisons each allows, for the question form."""
	frappe.only_for(EDITOR_ROLES)
	return {
		name: {
			"label": spec["label"],
			"doctypes": list(spec["doctypes"]),
			"derived": bool(spec.get("derived")),
			"comparisons": list(COMPARISONS.get(spec["kind"], ())),
		}
		for name, spec in FACETS.items()
	}
