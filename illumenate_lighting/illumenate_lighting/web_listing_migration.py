"""Copy product data from ilL-Webflow-Product onto the linked product templates.

The Webflow Product stays as the marketing record (copy, media, documents, compatibility,
brand targeting) and keeps the Webflow status and sync state. Product information
(lengths, feed lengths, spec-sheet data, weight, warranty, kit components) moves to the
template it links to, which becomes the place it is edited.

Only listings already linked to a template are migrated. Listings that merely share a
template's name are not linked here: those templates are being rebuilt, and each one is
linked with ``link_and_migrate`` once its template is confirmed.

Nothing on a template is overwritten. A field that already holds a different value, and
every field the template had before the Product Data tab, is left alone and reported
instead. Writes go straight to the database, so template controllers and the
publication approval hashes are not touched.

From the System Console (which does not allow imports), dry run first:

    print(frappe.call("illumenate_lighting.illumenate_lighting.web_listing_migration.migrate", dry_run=1))

``migrate`` is idempotent and can be re-run after more listings are linked.
"""

import json

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	PREEXISTING,
	TEMPLATE_DOCTYPES,
	WEBFLOW_PRODUCT_LINKS,
	added_fieldnames,
	template_doctypes_arg,
)

PRODUCT = "ilL-Webflow-Product"
LINK_FIELDS = {field: doctype for doctype, field in WEBFLOW_PRODUCT_LINKS.items()}

# Product data, under the same fieldname on the Webflow Product and the template.
SCALARS = (
	"min_length_mm",
	"max_length_mm",
	"length_increment_mm",
	"beam_angle",
	"l70_life_hours",
	"operating_temp_min_c",
	"operating_temp_max_c",
	"fixture_weight_per_foot_grams",
	"warranty_years",
)
TABLES = {
	"feed_lengths": "ilL-Child-Webflow-Feed-Length",
	"kit_components": "ilL-Child-Webflow-Kit-Component",
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
	if isinstance(left, str) and isinstance(right, list | dict):
		left, right = right, left
	if isinstance(left, list | dict) and isinstance(right, str):
		try:
			right = json.loads(right)
		except ValueError:
			return False
	if _empty(left) and _empty(right):
		return True
	return left == right


def _rows(rows):
	return [
		{key: value for key, value in row.items() if key not in ROW_META and not key.startswith("__")}
		for row in rows or []
	]


def carried(doctype):
	"""Product data fields one template type holds, scalars first.

	Includes fields the template defined before the Product Data tab (the Tape-Neon
	warranty): the migration leaves those alone, but the template is still their source.
	"""
	held = added_fieldnames(doctype) | PREEXISTING[doctype]
	return [field for field in (*SCALARS, *TABLES) if field in held]


def template_link(listing):
	"""Return (template doctype, template name) for a listing, or (None, None)."""
	for field, doctype in LINK_FIELDS.items():
		if listing.get(field):
			return doctype, listing.get(field)
	return None, None


def template_for(product):
	"""Return (doctype, name) of the template holding a Webflow Product's data, or (None, None).

	A template holds it once migrated, which the migration marks by pointing the
	template's Webflow Product backlink at the listing.
	"""
	listing = frappe.db.get_value(PRODUCT, product, list(LINK_FIELDS), as_dict=True)
	if listing:
		doctype, name = template_link(listing)
		if doctype and frappe.db.get_value(doctype, name, "webflow_product") == product:
			return doctype, name
	return None, None


def plan_listing(listing, template, doctype):
	"""Work out what to write onto one template; pure, so it can be unit tested.

	``listing`` and ``template`` are ``as_dict()`` dicts. Returns ``(values, tables, notes)``:
	scalar values to set, child tables to fill ({fieldname: rows}), and notes on everything
	left alone.
	"""
	added, preexisting = added_fieldnames(doctype), PREEXISTING[doctype]
	values, tables, notes = {}, {}, []
	if not template.get("webflow_product"):
		values["webflow_product"] = listing["name"]

	for field in SCALARS:
		value = listing.get(field)
		if _empty(value):
			continue
		current = template.get(field)
		if field in preexisting:
			if not _same(value, current):
				notes.append(f"{field} kept as {current!r}; listing has {value!r}")
		elif field not in added:
			notes.append(f"{field} not carried: {doctype} has no such field")
		elif _empty(current):
			values[field] = value
		elif not _same(value, current):
			notes.append(f"{field} kept as {current!r}; listing has {value!r}")

	for field in TABLES:
		rows = _rows(listing.get(field))
		if not rows:
			continue
		if field not in added:
			notes.append(f"{field} not carried: {doctype} has no such table")
		elif template.get(field):
			if _rows(template[field]) != rows:
				notes.append(f"{field} kept: template already has {len(template[field])} rows")
		else:
			tables[field] = rows

	backlink = template.get("webflow_product")
	if backlink and backlink != listing["name"]:
		notes.append(f"template's Webflow Product backlink points at {backlink}")
	return values, tables, notes


def _write(doctype, name, values, tables):
	if values:  # a top-up may only fill tables, and an empty UPDATE is a SQL error
		frappe.db.set_value(doctype, name, values, update_modified=False)
	for field, rows in tables.items():
		for idx, row in enumerate(rows, 1):
			frappe.get_doc(
				{
					"doctype": TABLES[field],
					"parent": name,
					"parenttype": doctype,
					"parentfield": field,
					"idx": idx,
					**row,
				}
			).db_insert()


def _migrate_one(listing, doctype, name, dry_run):
	row = {"listing": listing["name"], "template": f"{doctype} {name}"}
	if not frappe.db.exists(doctype, name):
		return {**row, "action": "skipped", "notes": ["template does not exist"]}
	template = frappe.get_doc(doctype, name).as_dict()
	backlink = template.get("webflow_product")
	if backlink and backlink != listing["name"]:
		return {**row, "action": "skipped", "notes": [f"template belongs to Webflow Product {backlink}"]}
	values, tables, notes = plan_listing(listing, template, doctype)
	if not values and not tables:
		return {**row, "action": "already migrated", "notes": notes}
	if backlink:
		action = "would top up" if dry_run else "topped up"
	else:
		action = "would migrate" if dry_run else "migrated"
	if not dry_run:
		_write(doctype, name, values, tables)
	row.update(
		action=action,
		fields=sorted(values),
		tables={field: len(rows) for field, rows in tables.items()},
		notes=notes,
	)
	return row


def _migrate_one_safely(listing, doctype, name, dry_run):
	"""Migrate one listing; a failure is reported and undone instead of stopping the run."""
	savepoint = "web_listing_migration"
	frappe.db.savepoint(savepoint)
	try:
		return _migrate_one(listing, doctype, name, dry_run)
	except Exception as error:
		frappe.db.rollback(save_point=savepoint)
		return {
			"listing": listing["name"],
			"template": f"{doctype} {name}",
			"action": "failed",
			"notes": [f"{type(error).__name__}: {error}", frappe.get_traceback()],
		}


def _listing(name):
	return json.loads(frappe.as_json(frappe.get_doc(PRODUCT, name).as_dict()))


@frappe.whitelist(methods=["POST"])
def migrate(dry_run=1):
	"""Migrate every linked listing's product data; return a report."""
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
		report.append(_migrate_one_safely(listings[0], doctype, template, dry_run))
	return {"listings": report, "left_on_webflow_product": unlinked}


@frappe.whitelist(methods=["POST"])
def link_and_migrate(listing, template, dry_run=1):
	"""Link a listing to a confirmed template and move its product data there.

	For listings whose template link was removed while the template was rebuilt. The
	listing stays off the website until its Webflow Product is made Active.
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
	row = _migrate_one(data, doctype, template, dry_run)
	if not dry_run and row["action"] in ("migrated", "topped up", "already migrated"):
		frappe.db.set_value(PRODUCT, listing, field, template)
		frappe.db.set_value(doctype, template, "webflow_product", listing, update_modified=False)
	return row


@frappe.whitelist()
def parity_report():
	"""List every migrated listing whose template differs from it on a product data field."""
	frappe.only_for("System Manager")
	report = []
	for name in frappe.get_all(PRODUCT, pluck="name", order_by="name asc"):
		doctype, template_name = template_for(name)
		if not doctype:
			continue
		template = frappe.get_doc(doctype, template_name).as_dict()
		differences = parity_differences(_listing(name), template, doctype)
		if differences:
			report.append(
				{"listing": name, "template": f"{doctype} {template_name}", "differences": differences}
			)
	return report


def parity_differences(listing, template, doctype):
	"""Product data fields where the template's value differs from the listing's; pure."""
	differences = []
	for field in carried(doctype):
		if field in TABLES:
			if _rows(listing.get(field)) != _rows(template.get(field)):
				differences.append(field)
		elif not _same(listing.get(field), template.get(field)):
			differences.append(field)
	return differences


# --- Listing fields the spec sheet reads from the template (production, 2026-11-24) ---------
#
# Production's catalog data sits on the Webflow Product; the spec sheet and the sync read the
# template (docs/superpowers/specs/2026-11-24-production-fixture-readiness-design.md). These
# fill EMPTY template fields from the linked product, never overwrite, and report differences.
# Brand, category and series are seeded by template_link_report.link_consistency_report.

# template field: product field
CARRY_SCALARS = {
	"sublabel": "sublabel",
	"dimensions_image": "dimensions_image",
	"hero_image": "featured_image",
}
# Owner, 2026-11-24: the featured image is a starting point; the report asks staff to check it.
CARRY_REVIEW = {"hero_image": "hero_image is the product's featured image: check it"}
CERTIFICATION_ROW = "ilL-Child-Spec-Certification"


def plan_carry(listing, template, fields):
	"""Pure: what to copy from a Webflow Product onto its template.

	``fields`` is the set of fieldnames the template type has. Returns
	``(values, tables, notes, review)``: scalars to set, child tables to fill, differences left
	alone, and copies staff should check.
	"""
	values, tables, notes, review = {}, {}, [], []
	for field, source in CARRY_SCALARS.items():
		value = listing.get(source)
		if field not in fields or _empty(value):
			continue
		current = template.get(field)
		if _empty(current):
			values[field] = value
			if field in CARRY_REVIEW:
				review.append(CARRY_REVIEW[field])
		elif field not in CARRY_REVIEW and not _same(value, current):
			# A hero image other than the featured image is the point of having one.
			notes.append(f"{field} kept as {current!r}; product has {value!r}")
	certifications = [row for row in listing.get("certifications") or [] if row.get("certification")]
	if "certifications" in fields and certifications:
		if template.get("certifications"):
			notes.append(f"certifications kept: template already has {len(template['certifications'])} rows")
		else:
			ordered = sorted(certifications, key=lambda row: row.get("display_order") or 0)
			tables["certifications"] = [{"certification": row["certification"]} for row in ordered]
	return values, tables, notes, review


def _carry_write(doctype, name, values, tables):
	if values:
		frappe.db.set_value(doctype, name, values, update_modified=False)
	for idx, row in enumerate(tables.get("certifications") or [], 1):
		frappe.get_doc(
			{
				"doctype": CERTIFICATION_ROW,
				"parent": name,
				"parenttype": doctype,
				"parentfield": "certifications",
				"idx": idx,
				**row,
			}
		).db_insert()


@frappe.whitelist(methods=["POST"])
def carry_listing_fields(dry_run=1, doctypes=None):
	"""Fill empty template fields (sublabel, images, certifications) from the linked product.

	Dry run by default. ``doctypes`` defaults to the site's webflow_sync_scope (fixtures on
	production first). Only templates whose Webflow Product links back to them are touched.
	"""
	dry_run = int(dry_run)
	frappe.only_for("System Manager")
	report, not_linked = [], []
	for doctype in template_doctypes_arg(doctypes):
		meta = frappe.get_meta(doctype)
		fields = {field for field in (*CARRY_SCALARS, "certifications") if meta.has_field(field)}
		link_field = WEBFLOW_PRODUCT_LINKS[doctype]
		for name in frappe.get_all(doctype, pluck="name", order_by="name asc"):
			template = frappe.get_doc(doctype, name).as_dict()
			key = f"{doctype} {name}"
			product = template.get("webflow_product")
			if not product or not frappe.db.exists(PRODUCT, product):
				not_linked.append(key)
				continue
			listing = frappe.get_doc(PRODUCT, product).as_dict()
			row = {"template": key, "listing": product}
			if listing.get(link_field) != name:
				report.append(
					{**row, "action": "skipped", "notes": [f"{product} links {listing.get(link_field)!r}"]}
				)
				continue
			values, tables, notes, review = plan_carry(listing, template, fields)
			if not values and not tables:
				report.append({**row, "action": "nothing to carry", "notes": notes, "review": review})
				continue
			if not dry_run:
				frappe.db.savepoint("carry_listing_fields")
				_carry_write(doctype, name, values, tables)
			report.append(
				{
					**row,
					"action": "would carry" if dry_run else "carried",
					"fields": sorted(values),
					"tables": {field: len(rows) for field, rows in tables.items()},
					"notes": notes,
					"review": review,
				}
			)
	if not dry_run:
		frappe.db.commit()
	return {"templates": report, "not_linked": not_linked}
