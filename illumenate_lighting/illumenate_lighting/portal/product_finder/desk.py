"""Desk endpoints for staff editing Product Finder content."""

import frappe
from frappe.rate_limiter import rate_limit

from illumenate_lighting.illumenate_lighting.portal.product_finder.facets import COMPARISONS, FACETS


def can_edit_content(user=None):
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	return any(allowed(capability, user) for capability in ("finder", "catalog", "sales", "engineering"))


def require_editor():
	if not can_edit_content():
		frappe.throw("Product Finder staff access is required", frappe.PermissionError)


@frappe.whitelist()
def facet_registry() -> dict:
	"""Facets with the ERP DocTypes and comparisons each allows, for the question form."""
	require_editor()
	return {
		name: {
			"label": spec["label"],
			"doctypes": list(spec["doctypes"]),
			"derived": bool(spec.get("derived")),
			"comparisons": list(COMPARISONS.get(spec["kind"], ())),
		}
		for name, spec in FACETS.items()
	}


@frappe.whitelist()
def preview_definition():
	from illumenate_lighting.illumenate_lighting.portal.product_finder.definition import load_definition

	require_editor()
	return load_definition(include_inactive=True)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
def preview_matches(answers):
	from illumenate_lighting.illumenate_lighting.portal.product_finder import (
		facts,
		matcher,
		server_definition,
		sessions,
	)

	require_editor()
	definition = server_definition.load(include_inactive=True)
	answers = sessions.validate_answers(definition, answers)
	products = facts.load()
	result = matcher.match(answers, definition=definition, facts=products, limit=20)
	by_name = {p["name"]: p for p in products}
	for match in result["matches"]:
		match["title"] = by_name[match["name"]]["title"]
	return result
