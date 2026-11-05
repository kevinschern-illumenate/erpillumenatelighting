"""Product readiness dashboard (hardening plan 5.6): one traffic-light row per Webflow Product.

Read-only and batched: a page costs a fixed number of queries, never one per product.
The full channel preflight (product_readiness.preview) stays one click away per row.
"""

import frappe

from illumenate_lighting.illumenate_lighting.api.product_projection import resolve_product_images
from illumenate_lighting.illumenate_lighting.portal.staff import allowed
from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	WEBFLOW_PRODUCT_LINK_TYPES,
	WEBFLOW_PRODUCT_LINKS,
)

PRODUCT = "ilL-Webflow-Product"
PUBLICATION = "ilL-Product-Publication"
COLUMNS = ("identity", "source", "specs", "images", "alt_text", "docs", "spec_sheet", "publication", "webflow_sync")
OK, WARN, FAIL, NA = "ok", "warn", "fail", "na"
SEVERITY = (FAIL, WARN, OK, NA)
TEMPLATE_FIELDS = {field: doctype for doctype, field in WEBFLOW_PRODUCT_LINKS.items()}
SOURCE_FIELD = {
	product_type: field for field, product_types in WEBFLOW_PRODUCT_LINK_TYPES.items() for product_type in product_types
}
PUBLICATION_STATUS = {"LIVE": OK, "STAGED": OK, "QUEUED": OK, "READY": WARN, "NEEDS_REVIEW": WARN, "FAILED": FAIL, "RETIRED": NA}
SYNC_STATUS = {"Synced": OK, "Pending": WARN, "Never Synced": WARN, "Error": FAIL}
MAX_LIMIT = 100


def require_reader():
	if not any(allowed(capability) for capability in ("catalog", "engineering", "integration")):
		frappe.throw("Product authoring staff access required", frappe.PermissionError)


def cell(status, message, field=None, doctype=PRODUCT, name=None):
	return {"status": status, "message": message, "field": field, "doctype": doctype, "name": name}


def row_status(product, template=None, image=None, specs=0, docs=0, gallery=(), publications=()):
	"""Traffic lights for one product. ``template`` is the linked source template row, if any."""
	name = product["name"]

	def here(status, message, field=None):
		return cell(status, message, field, PRODUCT, name)

	missing = [field for field in ("product_name", "product_slug", "product_type") if not product.get(field)]
	cells = {"identity": here(FAIL, "Missing " + ", ".join(missing), missing[0]) if missing else here(OK, "Complete")}

	source_field = SOURCE_FIELD.get(product.get("product_type"))
	if source_field:
		if not product.get(source_field):
			cells["source"] = here(FAIL if product.get("is_configurable") else WARN, "Link the family template", source_field)
		elif template is None:
			cells["source"] = here(FAIL, "Linked template no longer exists", source_field)
		else:
			cells["source"] = cell(OK, product[source_field], None, TEMPLATE_FIELDS[source_field], product[source_field])
	elif product.get("portal_item"):
		cells["source"] = here(OK, product["portal_item"], "portal_item")
	else:
		cells["source"] = here(NA, "No template for this product type")

	cells["specs"] = here(OK, f"{specs} rows") if specs else here(WARN, "No specification rows", "webflow_specifications")

	primary = (image or {}).get("primary")
	if primary:
		cells["images"] = here(OK, (image or {}).get("primary_source") or "Image")
	elif template is not None:
		cells["images"] = cell(FAIL, "Add the main product image", "hero_image", TEMPLATE_FIELDS[source_field], template["name"])
	else:
		cells["images"] = here(FAIL, "Add the main product image", "featured_image")

	unlabeled = sum(1 for row in gallery if row.get("image") and not (row.get("alt_text") or "").strip())
	if template is not None and template.get("hero_image") and not (template.get("hero_image_alt") or "").strip():
		cells["alt_text"] = cell(WARN, "Main image has no alt text", "hero_image_alt", TEMPLATE_FIELDS[source_field], template["name"])
	elif unlabeled:
		cells["alt_text"] = here(WARN, f"{unlabeled} gallery image(s) without alt text", "gallery_images")
	else:
		cells["alt_text"] = here(OK, "Complete")

	cells["docs"] = here(OK, f"{docs} documents") if docs else here(WARN, "No documents", "documents")

	if template is None:
		cells["spec_sheet"] = here(NA, "No family template")
	elif template.get("spec_sheet"):
		cells["spec_sheet"] = cell(OK, "Attached", None, TEMPLATE_FIELDS[source_field], template["name"])
	else:
		cells["spec_sheet"] = cell(WARN, "No spec sheet", "spec_sheet", TEMPLATE_FIELDS[source_field], template["name"])

	if publications:
		worst = min(publications, key=lambda row: SEVERITY.index(PUBLICATION_STATUS.get(row["state"], WARN)))
		summary = ", ".join(f"{row['brand']}: {row['state']}" for row in publications)
		cells["publication"] = cell(PUBLICATION_STATUS.get(worst["state"], WARN), summary, None, PUBLICATION, worst.get("name"))
	else:
		cells["publication"] = here(NA if not product.get("is_active") else WARN, "Not requested")

	sync = product.get("sync_status") or "Never Synced"
	cells["webflow_sync"] = here(SYNC_STATUS.get(sync, WARN), product.get("sync_error_message") or sync, "sync_status")
	return {
		"product": name,
		"product_name": product.get("product_name"),
		"product_type": product.get("product_type"),
		"is_active": bool(product.get("is_active")),
		"cells": cells,
		"ready": all(cells[column]["status"] in (OK, NA) for column in COLUMNS),
	}


def _counts(doctype, names):
	rows = frappe.get_all(
		doctype,
		filters={"parenttype": PRODUCT, "parent": ["in", names]},
		fields=["parent", "count(name) as rows"],
		group_by="parent",
	)
	return {row["parent"]: row["rows"] for row in rows}


@frappe.whitelist(methods=["GET"])
def dashboard(family=None, brand=None, after=None, limit=50, only_incomplete=0):
	"""A keyset page of products, optionally one product type (family) or one target brand."""
	require_reader()
	limit = max(1, min(int(limit or 50), MAX_LIMIT))
	filters = {}
	if family:
		filters["product_type"] = family
	if after:
		filters["name"] = [">", after]
	if brand:
		targeted = frappe.get_all(
			"ilL-Child-Webflow-Brand-Target",
			filters={"parenttype": PRODUCT, "brand": brand, "enabled": 1},
			pluck="parent",
		)
		targeted = sorted(name for name in set(targeted) if not after or name > after)
		filters["name"] = ["in", targeted or [""]]
	fields = [
		"name", "product_name", "product_slug", "product_type", "is_active", "is_configurable",
		"portal_item", "sync_status", "sync_error_message", *TEMPLATE_FIELDS,
	]
	products = frappe.get_all(PRODUCT, filters=filters, fields=fields, order_by="name asc", limit_page_length=limit + 1)
	page = products[:limit]
	names = [row["name"] for row in page]
	if not names:
		return {"columns": list(COLUMNS), "rows": [], "next_cursor": None}
	templates = {}
	for field, doctype in TEMPLATE_FIELDS.items():
		linked = [row[field] for row in page if row.get(field)]
		if linked:
			for row in frappe.get_all(
				doctype,
				filters={"name": ["in", linked]},
				fields=["name", "hero_image", "hero_image_alt", "spec_sheet"],
			):
				templates[(doctype, row["name"])] = row
	images = resolve_product_images(PRODUCT, names)
	specs = _counts("ilL-Child-Webflow-Spec-Custom", names)  # the template's specifications, mirrored
	docs = _counts("ilL-Child-Webflow-Document", names)
	gallery = {}
	for row in frappe.get_all(
		"ilL-Child-Webflow-Gallery-Image",
		filters={"parenttype": PRODUCT, "parent": ["in", names]},
		fields=["parent", "image", "alt_text"],
	):
		gallery.setdefault(row["parent"], []).append(row)
	publication_filters = {"product": ["in", names]}
	if brand:
		publication_filters["brand"] = brand
	publications = {}
	for row in frappe.get_all(PUBLICATION, filters=publication_filters, fields=["name", "product", "brand", "state"]):
		publications.setdefault(row["product"], []).append(row)
	rows = []
	for product in page:
		field = SOURCE_FIELD.get(product.get("product_type"))
		template = templates.get((TEMPLATE_FIELDS.get(field), product.get(field))) if field else None
		rows.append(
			row_status(
				product,
				template,
				images.get(product["name"]),
				specs.get(product["name"], 0),
				docs.get(product["name"], 0),
				gallery.get(product["name"], ()),
				publications.get(product["name"], ()),
			)
		)
	if str(only_incomplete).strip().lower() in ("1", "true", "yes", "on"):
		rows = [row for row in rows if not row["ready"]]
	return {
		"columns": list(COLUMNS),
		"rows": rows,
		"next_cursor": page[-1]["name"] if len(products) > limit else None,
	}
