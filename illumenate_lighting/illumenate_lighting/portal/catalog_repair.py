"""Find and repair catalog products whose configurator cannot open.

A product page opens its family configurator only when the ``ilL-Webflow-Product``
is configurable and links an active template (see ``product_projection``). Templates
already record the product they belong to in ``webflow_product``; this module uses
that back-link to fill in a missing forward link and the ``is_configurable`` flag.

It never overwrites a different template link, and it reports mismatches instead of
guessing. Run a dry run first:

	bench --site <site> execute \
		illumenate_lighting.illumenate_lighting.portal.catalog_repair.link_configurable_products \
		--kwargs "{'dry_run': 1}"

or use the "Preview repair" / "Apply repair" buttons on the Catalog Configurability report.
"""

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import FAMILY_ALIASES, parse_bool
from illumenate_lighting.illumenate_lighting.api.product_projection import TEMPLATE_DOCTYPES, TEMPLATE_FIELDS

PRODUCT = "ilL-Webflow-Product"
REPAIR_ROLES = ("System Manager", "ilL Catalog Publisher")


def template_backlinks() -> dict:
	"""``{product name: [(DocType, template, is_active, product_category)]}`` from template back-links."""
	links: dict = {}
	for doctype in sorted(set(TEMPLATE_DOCTYPES.values())):
		fields = ["name", "webflow_product", "is_active"]
		if doctype == "ilL-Tape-Neon-Template":
			fields.append("product_category")
		for row in frappe.get_all(
			doctype, filters={"webflow_product": ["is", "set"]}, fields=fields, ignore_permissions=True
		):
			links.setdefault(row.webflow_product, []).append(
				(doctype, row.name, parse_bool(row.is_active), row.get("product_category"))
			)
	return links


def _plan(product, backlinks) -> tuple[dict, list]:
	"""Return ``(changes, conflicts)`` for one active product."""
	family = FAMILY_ALIASES.get(product.product_type, product.product_type)
	field, doctype = TEMPLATE_FIELDS.get(family), TEMPLATE_DOCTYPES.get(family)
	candidates = [row for row in backlinks.get(product.name, []) if row[2]]
	if not field or not candidates:
		return {}, []
	matching = [row for row in candidates if row[0] == doctype and (not row[3] or row[3] == family)]
	if not matching:
		return {}, [
			f"Active template {name} ({linked_doctype}) points at this {product.product_type} product, "
			"but that template does not belong to this product type"
			for linked_doctype, name, _active, _category in candidates
		]
	current = product.get(field)
	if current and current not in {row[1] for row in matching}:
		return {}, [f"Product links {current}, but active template {matching[0][1]} points at it"]
	if not current and len(matching) > 1:
		names = ", ".join(row[1] for row in matching)
		return {}, [f"Several active templates point at this product ({names}); link one manually"]
	changes = {}
	if not current:
		changes[field] = matching[0][1]
	if not parse_bool(product.is_configurable):
		changes["is_configurable"] = 1
	return changes, []


def link_configurable_products(dry_run=1) -> dict:
	"""Link active products to the active template that points at them, and mark them configurable.

	Saving a product regenerates its attribute links and configurator options, and marks a
	previously synced product as pending Webflow sync.
	"""
	dry_run = parse_bool(dry_run, default=True)
	backlinks = template_backlinks()
	fields = [
		"name",
		"product_name",
		"product_type",
		"is_configurable",
		*sorted(set(TEMPLATE_FIELDS.values())),
	]
	products = (
		frappe.get_all(
			PRODUCT,
			filters={"is_active": 1, "name": ["in", list(backlinks)]},
			fields=fields,
			order_by="name asc",
			ignore_permissions=True,
		)
		if backlinks
		else []
	)
	result = {"dry_run": dry_run, "changes": [], "conflicts": [], "errors": []}
	for product in products:
		changes, conflicts = _plan(product, backlinks)
		for message in conflicts:
			result["conflicts"].append(
				{"product": product.name, "product_name": product.product_name, "message": message}
			)
		if not changes:
			continue
		entry = {"product": product.name, "product_name": product.product_name, "changes": changes}
		if not dry_run:
			savepoint = "ill_catalog_repair"
			frappe.db.savepoint(savepoint)
			try:
				doc = frappe.get_doc(PRODUCT, product.name)
				doc.update(changes)
				doc.save(ignore_permissions=True)
			except Exception as exc:
				frappe.db.rollback(save_point=savepoint)
				result["errors"].append({**entry, "message": str(exc)})
				continue
		result["changes"].append(entry)
	return result


@frappe.whitelist(methods=["POST"])
def repair(dry_run=1) -> dict:
	"""Desk entry point for the Catalog Configurability report buttons."""
	frappe.only_for(REPAIR_ROLES)
	return link_configurable_products(dry_run=dry_run)
