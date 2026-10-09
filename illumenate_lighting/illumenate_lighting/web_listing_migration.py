"""Copy ilL-Webflow-Product content onto the linked product templates (merge plan, step 3).

Only listings already linked to a template are migrated. Listings that merely share a
template's name are not linked here: those templates are being rebuilt, and each one is
linked with ``link_and_migrate`` once its template is confirmed.

Nothing on a template is overwritten. A Web Listing field that already holds a different
value, and every field the template had before the Web Listing tab, is left alone and
reported instead. Writes go straight to the database, so template controllers and the
publication approval hashes are not touched.

From the System Console, dry run first:

    from illumenate_lighting.illumenate_lighting.web_listing_migration import migrate
    print(migrate(dry_run=1))

``migrate`` is idempotent and can be re-run after more listings are linked.
"""

import json

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	PREEXISTING,
	TEMPLATE_DOCTYPES,
	WEBFLOW_PRODUCT_LINKS,
	added_fieldnames,
)

PRODUCT = "ilL-Webflow-Product"
PUBLICATION_DOCTYPES = ("ilL-Product-Publication", "ilL-Publish-Job", "ilL-Product-Verification-Request")
LINK_FIELDS = {field: doctype for doctype, field in WEBFLOW_PRODUCT_LINKS.items()}

# Webflow Product field -> template field, where the names differ.
RENAMED = {"product_category": "web_category"}
SCALARS = (
	"product_category",
	"portal_item",
	"short_description",
	"sublabel",
	"product_badge",
	"features",
	"warranty_years",
	"featured_image",
	"dimensions_image",
	"series_family_image",
	"is_configurable",
	"configurator_intro_text",
	"min_length_mm",
	"max_length_mm",
	"length_increment_mm",
	"beam_angle",
	"l70_life_hours",
	"operating_temp_min_c",
	"operating_temp_max_c",
	"fixture_weight_per_foot_grams",
)
TABLES = {
	"gallery_images": "ilL-Child-Webflow-Gallery-Image",
	"documents": "ilL-Child-Webflow-Document",
	"feed_lengths": "ilL-Child-Webflow-Feed-Length",
	"kit_components": "ilL-Child-Webflow-Kit-Component",
	"target_brands": "ilL-Child-Webflow-Brand-Target",
	"configurator_options": "ilL-Child-Webflow-Configurator-Option",
	"attribute_links": "ilL-Child-Webflow-Attribute-Link",
	"compatible_products": "ilL-Child-Webflow-Compatibility",
}
ROW_META = {
	"name",
	"parent",
	"parentfield",
	"parenttype",
	"idx",
	"doctype",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
}


def _empty(value):
	return value in (None, "", 0, 0.0, [], {}) or value == "[]"


def _same(left, right):
	if isinstance(left, str) and isinstance(right, (list, dict)):
		left, right = right, left
	if isinstance(left, (list, dict)) and isinstance(right, str):
		try:
			right = json.loads(right)
		except ValueError:
			return False
	if _empty(left) and _empty(right):
		return True
	return left == right


def _rows(rows):
	return [{key: value for key, value in row.items() if key not in ROW_META} for row in rows or []]


def template_link(listing):
	"""Return (template doctype, template name) for a listing, or (None, None)."""
	for field, doctype in LINK_FIELDS.items():
		if listing.get(field):
			return doctype, listing[field]
	return None, None


def plan_listing(listing, template, doctype, web_listed=None):
	"""Work out what to write onto one template; pure, so it can be unit tested.

	``listing`` and ``template`` are ``as_dict()`` dicts. Returns ``(values, tables, notes)``:
	scalar values to set, child tables to fill ({fieldname: rows}), and notes on everything
	left alone.
	"""
	added, preexisting = added_fieldnames(doctype), PREEXISTING[doctype]
	values, tables, notes = {}, {}, []
	values["web_slug"] = listing["name"]
	values["web_listed"] = int(bool(listing.get("is_active") if web_listed is None else web_listed))
	if listing.get("product_name") and listing["product_name"] != template.get("template_name"):
		values["web_title"] = listing["product_name"]

	for source in SCALARS:
		target = RENAMED.get(source, source)
		value = listing.get(source)
		if _empty(value):
			continue
		current = template.get(target)
		if target in preexisting:
			if not _same(value, current):
				notes.append(f"{target} kept as {current!r}; listing has {value!r}")
		elif target not in added:
			notes.append(f"{source} not carried: {doctype} has no such field")
		elif _empty(current):
			values[target] = value
		elif not _same(value, current):
			notes.append(f"{target} kept as {current!r}; listing has {value!r}")

	for field in TABLES:
		rows = _rows(listing.get(field))
		if not rows:
			continue
		if field not in added:
			notes.append(f"{field} not carried: {doctype} has no such table")
		elif template.get(field):
			notes.append(f"{field} kept: template already has {len(template[field])} rows")
		else:
			tables[field] = rows

	certifications = {row.get("certification") for row in listing.get("certifications") or []}
	certifications.discard(None)
	if "certifications" in preexisting:
		missing = certifications - {row.get("certification") for row in template.get("certifications") or []}
		if missing:
			notes.append(f"certifications kept; listing also has {', '.join(sorted(missing))}")
	elif certifications and not template.get("certifications"):
		tables["certifications"] = [{"certification": name} for name in sorted(certifications)]

	backlink = template.get("webflow_product")
	if backlink and backlink != listing["name"]:
		notes.append(f"template's Webflow Product backlink points at {backlink}")
	return values, tables, notes


def _child_doctype(doctype, field):
	return frappe.get_meta(doctype).get_field(field).options


def _write(doctype, name, values, tables):
	frappe.db.set_value(doctype, name, values, update_modified=False)
	for field, rows in tables.items():
		child = _child_doctype(doctype, field)
		for idx, row in enumerate(rows, 1):
			frappe.get_doc(
				{
					"doctype": child,
					"parent": name,
					"parenttype": doctype,
					"parentfield": field,
					"idx": idx,
					**row,
				}
			).db_insert()


def _slug_owner(slug, doctype, name):
	for other in TEMPLATE_DOCTYPES:
		filters = {"web_slug": slug}
		if other == doctype:
			filters["name"] = ["!=", name]
		owner = frappe.db.get_value(other, filters, "name")
		if owner:
			return f"{other} {owner}"
	return None


def _migrate_one(listing, doctype, name, dry_run, web_listed=None):
	row = {"listing": listing["name"], "template": f"{doctype} {name}"}
	if not frappe.db.exists(doctype, name):
		return {**row, "action": "skipped", "notes": ["template does not exist"]}
	template = frappe.get_doc(doctype, name).as_dict()
	if template.get("web_slug") == listing["name"]:
		return {**row, "action": "already migrated", "notes": []}
	if template.get("web_slug"):
		return {
			**row,
			"action": "skipped",
			"notes": [f"template already has web slug {template['web_slug']}"],
		}
	owner = _slug_owner(listing["name"], doctype, name)
	if owner:
		return {**row, "action": "skipped", "notes": [f"slug already used by {owner}"]}
	values, tables, notes = plan_listing(listing, template, doctype, web_listed)
	if not dry_run:
		_write(doctype, name, values, tables)
	row.update(
		action="would migrate" if dry_run else "migrated",
		fields=sorted(values),
		tables={field: len(rows) for field, rows in tables.items()},
		notes=notes,
	)
	return row


def _listing(name):
	return json.loads(frappe.as_json(frappe.get_doc(PRODUCT, name).as_dict()))


def migrate(dry_run=1):
	"""Migrate every linked listing and backfill publication listing links; return a report."""
	dry_run = int(dry_run)
	frappe.only_for("System Manager")
	claims, unlinked = {}, 0
	for name in frappe.get_all(PRODUCT, pluck="name", order_by="name asc"):
		listing = _listing(name)
		doctype, template = template_link(listing)
		if doctype:
			claims.setdefault((doctype, template), []).append(listing)
		else:
			unlinked += 1
	report = []
	for (doctype, template), listings in sorted(claims.items()):
		if len(listings) > 1:
			names = ", ".join(listing["name"] for listing in listings)
			report.append(
				{
					"listing": names,
					"template": f"{doctype} {template}",
					"action": "skipped",
					"notes": ["template is linked from more than one listing"],
				}
			)
			continue
		report.append(_migrate_one(listings[0], doctype, template, dry_run))
	return {
		"listings": report,
		"left_on_webflow_product": unlinked,
		"publications": backfill_publication_listings(dry_run),
	}


def listing_for(product):
	"""Return (doctype, name) of the record that now carries a Webflow Product's listing."""
	listing = frappe.db.get_value(PRODUCT, product, list(LINK_FIELDS), as_dict=True)
	if listing:
		doctype, name = template_link(listing)
		if doctype and frappe.db.get_value(doctype, name, "web_slug") == product:
			return doctype, name
	return PRODUCT, product


def backfill_publication_listings(dry_run=1, products=None):
	"""Point Publication, Publish Job and Verification Request rows at their listing record."""
	counts = {}
	cache = {}
	for doctype in PUBLICATION_DOCTYPES:
		filters = {"product": ["is", "set"]}
		if products:
			filters["product"] = ["in", list(products)]
		changed = 0
		for row in frappe.get_all(
			doctype, filters=filters, fields=["name", "product", "listing_doctype", "listing_name"]
		):
			if row.product not in cache:
				cache[row.product] = listing_for(row.product)
			target = cache[row.product]
			if (row.listing_doctype, row.listing_name) == target:
				continue
			changed += 1
			if not int(dry_run):
				frappe.db.set_value(
					doctype,
					row.name,
					{"listing_doctype": target[0], "listing_name": target[1]},
					update_modified=False,
				)
		counts[doctype] = changed
	return counts


def link_and_migrate(listing, template, dry_run=1):
	"""Link a listing to a confirmed template and migrate it with Listed on Web off.

	For listings whose template link was removed while the template was rebuilt. Tick
	Listed on Web on the template once it is ready to go back on the web.
	"""
	dry_run = int(dry_run)
	frappe.only_for("System Manager")
	data = _listing(listing)
	current_doctype, current = template_link(data)
	if current:
		frappe.throw(f"{listing} is already linked to {current_doctype} {current}")
	doctype = next((d for d in TEMPLATE_DOCTYPES if frappe.db.exists(d, template)), None)
	if not doctype:
		frappe.throw(f"No product template named {template}")
	field = WEBFLOW_PRODUCT_LINKS[doctype]
	claimed = frappe.db.get_value(PRODUCT, {field: template, "name": ["!=", listing]}, "name")
	if claimed:
		frappe.throw(f"{doctype} {template} is already linked from {claimed}")
	data[field] = template
	row = _migrate_one(data, doctype, template, dry_run, web_listed=0)
	if not dry_run and row["action"] == "migrated":
		frappe.db.set_value(PRODUCT, listing, field, template)
		if not frappe.db.get_value(doctype, template, "webflow_product"):
			frappe.db.set_value(doctype, template, "webflow_product", listing, update_modified=False)
		row["publications"] = backfill_publication_listings(0, products=[listing])
	return row


def parity_report():
	"""List every migrated listing whose template no longer matches it on a carried field."""
	report = []
	for name in frappe.get_all(PRODUCT, pluck="name", order_by="name asc"):
		listing = _listing(name)
		doctype, template_name = template_link(listing)
		if not doctype or frappe.db.get_value(doctype, template_name, "web_slug") != name:
			continue
		template = frappe.get_doc(doctype, template_name).as_dict()
		differences = parity_differences(listing, template, doctype)
		if differences:
			report.append(
				{"listing": name, "template": f"{doctype} {template_name}", "differences": differences}
			)
	return report


def parity_differences(listing, template, doctype):
	"""Carried fields where the template's value differs from the listing's; pure."""
	added = added_fieldnames(doctype)
	differences = []
	for source in SCALARS:
		target = RENAMED.get(source, source)
		if target in added and not _same(listing.get(source), template.get(target)):
			differences.append(target)
	for field in TABLES:
		if field in added and _rows(listing.get(field)) != _rows(template.get(field)):
			differences.append(field)
	title = template.get("web_title") or template.get("template_name")
	if listing.get("product_name") and listing["product_name"] != title:
		differences.append("web_title")
	return differences
