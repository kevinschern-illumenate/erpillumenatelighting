"""The link between a product template and its Webflow Product (plan 4.2, D2, D3, D17, D27, D28).

The template owns the link: ``template.webflow_product`` is the real field, and the
product's per-type link field (``kit_template``, ``fixture_template`` and the others) is a
read-only mirror written from here. Rules, checked on both sides:

- One template links to at most one product, and a product to exactly one template.
- The product's ``product_type`` must be one the template's link field serves.
- A template needs its Webflow Product once its Product Status is Active + Live (D60).
- Target Brands has at most one enabled row, and linking needs exactly one.
- The brand cannot change once the product was published on the old brand.
- No two templates, in any of the six doctypes, share a record name (case-insensitive):
  the stable spec-sheet URL is keyed on it (plan 4.7).

Linking happens by picking the product while the field is empty (it is read only once
set) or through ``link_webflow_product``. Unlinking only through ``unlink_webflow_product``.
Each template controller calls ``validate_template``, ``on_template_update`` and
``on_template_trash``.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	LIVE_STATUS,
	TEMPLATE_DOCTYPES,
	WEBFLOW_PRODUCT_LINK_TYPES,
	WEBFLOW_PRODUCT_LINKS,
)

PRODUCT = "ilL-Webflow-Product"
PUBLICATION = "ilL-Product-Publication"


# ---------------------------------------------------------------- permissions


def require_template_access(doctype, name):
	"""System User, write on the template, and the catalog capability (D28)."""
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	user = frappe.session.user
	if user != "Administrator" and frappe.db.get_value("User", user, "user_type") != "System User":
		frappe.throw(_("Only ERPNext desk users can do this."), frappe.PermissionError)
	if not frappe.has_permission(doctype, "write", doc=name):
		frappe.throw(_("You don't have permission to change this template."), frappe.PermissionError)
	if not allowed("catalog"):
		frappe.throw(_("This action needs the ilL Catalog Publisher role."), frappe.PermissionError)


# ---------------------------------------------------------------- helpers


def _check_doctype(doctype):
	if doctype not in TEMPLATE_DOCTYPES:
		frappe.throw(_("{0} is not a product template.").format(doctype))


def enabled_brands(doc):
	return [row.brand for row in (doc.get("target_brands") or []) if row.get("enabled") and row.get("brand")]


def _before(doc):
	return doc.get_doc_before_save() if not doc.is_new() else None


def linked_template(product):
	"""(doctype, name) pairs of every template that claims this product, from either side."""
	links = set()
	row = frappe.db.get_value(PRODUCT, product, list(WEBFLOW_PRODUCT_LINK_TYPES), as_dict=True) or {}
	for doctype, fieldname in WEBFLOW_PRODUCT_LINKS.items():
		if row.get(fieldname):
			links.add((doctype, row[fieldname]))
		for name in frappe.get_all(doctype, filters={"webflow_product": product}, pluck="name"):
			links.add((doctype, name))
	return links


# ---------------------------------------------------------------- validation


def validate_unique_name(doc):
	"""Block a new template whose name another template doctype already uses (any case)."""
	if not doc.is_new() or not doc.name:
		return
	for doctype in TEMPLATE_DOCTYPES:
		if doctype == doc.doctype:
			continue
		clash = frappe.db.sql(
			f"select name from `tab{doctype}` where lower(name) = lower(%s) limit 1", (doc.name,)
		)
		if clash:
			frappe.throw(
				_(
					"{0} {1} already uses the name {2}. Template names must be unique across all template types."
				).format(doctype, clash[0][0], doc.name)
			)


def validate_target_brands(doc):
	brands = enabled_brands(doc)
	if len(brands) > 1:
		frappe.throw(_("A template is listed under one brand. Enable only one Target Brand row."))
	before = _before(doc)
	if not before or not doc.get("webflow_product"):
		return
	old = enabled_brands(before)
	if not old or old == brands:
		return
	if frappe.db.get_value(
		PUBLICATION, {"product": doc.webflow_product, "brand": old[0], "published_on": ["is", "set"]}, "name"
	):
		frappe.throw(
			_("The brand cannot change: {0} has been published on {1}.").format(doc.webflow_product, old[0])
		)


def validate_webflow_product(doc):
	before = _before(doc)
	old = before.get("webflow_product") if before else None
	new = doc.get("webflow_product")
	if old and new != old and not doc.flags.webflow_link_action:
		frappe.throw(_("Use Actions > Unlink Webflow Product to change the Webflow Product."))
	if old and not new and doc.get("product_status") == LIVE_STATUS:
		frappe.throw(
			_("An Active + Live template needs its Webflow Product. Change the Product Status first.")
		)
	if new and new != old:
		require_template_access(doc.doctype, doc.name)
		_check_link(doc, new)
	if doc.get("product_status") == LIVE_STATUS and not new:
		became_live = not before or before.get("product_status") != LIVE_STATUS
		if became_live:
			frappe.throw(_("Link a Webflow Product before setting the Product Status to Active + Live."))


def _check_link(doc, product):
	fieldname = WEBFLOW_PRODUCT_LINKS[doc.doctype]
	product_type = frappe.db.get_value(PRODUCT, product, "product_type")
	if product_type is None:
		frappe.throw(_("Webflow Product {0} does not exist.").format(product))
	if product_type not in WEBFLOW_PRODUCT_LINK_TYPES[fieldname]:
		frappe.throw(
			_("Webflow Product {0} is a {1}. A {2} can only link a product of type {3}.").format(
				product,
				product_type or _("product with no type"),
				doc.doctype,
				", ".join(WEBFLOW_PRODUCT_LINK_TYPES[fieldname]),
			)
		)
	others = sorted(link for link in linked_template(product) if link != (doc.doctype, doc.name))
	if others:
		frappe.throw(
			_("Webflow Product {0} is already linked to {1} {2}.").format(product, others[0][0], others[0][1])
		)
	if len(enabled_brands(doc)) != 1:
		frappe.throw(_("Enable exactly one Target Brand on this template before linking a Webflow Product."))


def validate_template(doc):
	"""Call from each template controller's validate(), after apply_product_status."""
	validate_unique_name(doc)
	validate_target_brands(doc)
	validate_webflow_product(doc)


# ---------------------------------------------------------------- writing the mirror


def on_template_update(doc):
	"""Write the product side of a changed link. Call from each template's on_update().

	Returns True when it saved the newly linked product (so it already has the template's rows).
	"""
	before = doc.get_doc_before_save()
	old = before.get("webflow_product") if before else None
	new = doc.get("webflow_product")
	if old == new:
		return False
	fieldname = WEBFLOW_PRODUCT_LINKS[doc.doctype]
	if old and frappe.db.get_value(PRODUCT, old, fieldname) == doc.name:
		frappe.db.set_value(PRODUCT, old, fieldname, None)
	if new:
		# A full save, so the product mirrors the template's data on the same request.
		product = frappe.get_doc(PRODUCT, new)
		product.set(fieldname, doc.name)
		product.flags.from_template_link = True
		product.save(ignore_permissions=True)
		return True
	return False


def on_template_trash(doc):
	product = doc.get("webflow_product")
	fieldname = WEBFLOW_PRODUCT_LINKS[doc.doctype]
	if product and frappe.db.get_value(PRODUCT, product, fieldname) == doc.name:
		frappe.db.set_value(PRODUCT, product, fieldname, None)


def validate_product_links(product):
	"""Product side: link fields are mirrors. Call from the product's validate()."""
	if product.flags.from_template_link:
		return
	if product.flags.in_copy:
		# A duplicate never inherits the original's template.
		for fieldname in WEBFLOW_PRODUCT_LINK_TYPES:
			product.set(fieldname, None)
		return
	if product.is_new():
		_validate_new_product_link(product)
		return
	before = product.get_doc_before_save()
	type_changed = bool(before) and before.get("product_type") != product.get("product_type")
	for fieldname, product_types in WEBFLOW_PRODUCT_LINK_TYPES.items():
		value = product.get(fieldname)
		old = before.get(fieldname) if before else None
		if value != old:
			frappe.throw(
				_(
					"Templates are linked from the template: set its Webflow Product field instead of {0}."
				).format(fieldname)
			)
		if value and type_changed and product.get("product_type") not in product_types:
			frappe.throw(
				_(
					"This product is linked to template {0}, which does not fit type {1}. Unlink it from the template first."
				).format(value, product.get("product_type"))
			)


def _new_product_links(product):
	return [
		(doctype, fieldname, product.get(fieldname))
		for doctype, fieldname in WEBFLOW_PRODUCT_LINKS.items()
		if product.get(fieldname)
	]


def _validate_new_product_link(product):
	"""Creating a product for a template (catalog import, and later the Create popup).

	Allowed when the template exists, is not linked yet, serves the product's type and the
	user may change it (D28). on_product_insert then writes the template side.
	"""
	links = _new_product_links(product)
	if not links:
		return
	if len(links) > 1:
		frappe.throw(_("A Webflow Product links exactly one template."))
	doctype, fieldname, template = links[0]
	if product.get("product_type") not in WEBFLOW_PRODUCT_LINK_TYPES[fieldname]:
		frappe.throw(
			_("A {0} can only link a product of type {1}.").format(
				doctype, ", ".join(WEBFLOW_PRODUCT_LINK_TYPES[fieldname])
			)
		)
	if not frappe.db.exists(doctype, template):
		frappe.throw(_("{0} {1} does not exist.").format(doctype, template))
	current = frappe.db.get_value(doctype, template, "webflow_product")
	if current and current != product.name:
		frappe.throw(_("{0} {1} is already linked to {2}.").format(doctype, template, current))
	require_template_access(doctype, template)


def on_product_insert(product):
	"""Write the template side for a product created with a template link."""
	for doctype, _fieldname, template in _new_product_links(product):
		frappe.db.set_value(doctype, template, "webflow_product", product.name, update_modified=False)


# ---------------------------------------------------------------- explicit actions


@frappe.whitelist(methods=["POST"])
def link_webflow_product(template_doctype, template_id, product):
	"""Link an existing Webflow Product to a template (one call writes both sides)."""
	_check_doctype(template_doctype)
	require_template_access(template_doctype, template_id)
	doc = frappe.get_doc(template_doctype, template_id)
	if doc.get("webflow_product"):
		frappe.throw(
			_("This template is already linked to {0}. Unlink it first.").format(doc.webflow_product)
		)
	doc.webflow_product = product
	doc.flags.webflow_link_action = True
	doc.save()
	return {"template": doc.name, "webflow_product": doc.webflow_product}


def product_defaults(template):
	"""Pure: the new Webflow Product's fields from a template (dict-like), for the popup."""
	fieldname = WEBFLOW_PRODUCT_LINKS[template.get("doctype")]
	types = list(WEBFLOW_PRODUCT_LINK_TYPES[fieldname])
	own_type = template.get("product_type")
	return {
		"link_field": fieldname,
		"product_name": template.get("display_name") or template.get("template_name") or template.get("name"),
		"product_slug": slugify(template.get("name")),
		"product_types": types,
		"product_type": own_type if own_type in types else types[0],
		"brands": enabled_brands(template),
	}


def slugify(value):
	"""Pure: "KIT-RA03" -> "kit-ra03"; spaces and other characters become hyphens."""
	import re

	return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


@frappe.whitelist()
def go_live_defaults(template_doctype, template_id):
	"""For the popup shown when a template without a Webflow Product is set to Active + Live
	(plan 4.5, D3; owner 2026-11-08)."""
	_check_doctype(template_doctype)
	require_template_access(template_doctype, template_id)
	return product_defaults(frappe.get_doc(template_doctype, template_id))


@frappe.whitelist(methods=["POST"])
def create_webflow_product(template_doctype, template_id, product_name, product_slug, product_type=None):
	"""Create the template's Webflow Product (popup "Create new"). The popup then links it by
	saving the template with the new product and Active + Live, so both sides are written by the
	normal save and the user's other unsaved edits are kept. Returns the product's name.
	"""
	_check_doctype(template_doctype)
	require_template_access(template_doctype, template_id)
	template = frappe.get_doc(template_doctype, template_id)
	if template.get("webflow_product"):
		frappe.throw(_("This template is already linked to {0}.").format(template.webflow_product))
	defaults = product_defaults(template)
	if len(defaults["brands"]) != 1:
		frappe.throw(
			_("Enable exactly one Target Brand on this template before creating its Webflow Product.")
		)
	product_type = product_type or defaults["product_type"]
	if product_type not in defaults["product_types"]:
		frappe.throw(
			_("A {0} can only link a product of type {1}.").format(
				template_doctype, ", ".join(defaults["product_types"])
			)
		)
	slug = slugify(product_slug)
	if not slug or not (product_name or "").strip():
		frappe.throw(_("Enter a product name and slug."))
	if frappe.db.exists(PRODUCT, slug):
		frappe.throw(
			_("A Webflow Product {0} already exists. Choose Link existing, or another slug.").format(slug)
		)
	product = frappe.get_doc(
		{
			"doctype": PRODUCT,
			"product_name": product_name.strip(),
			"product_slug": slug,
			"product_type": product_type,
			"webflow_status": "Webflow Draft",
			"target_brands": [{"brand": defaults["brands"][0], "enabled": 1}],
		}
	)
	product.insert()
	return product.name


@frappe.whitelist(methods=["POST"])
def unlink_webflow_product(template_doctype, template_id):
	"""Clear the link on both sides. Not allowed while the template is Active + Live."""
	_check_doctype(template_doctype)
	require_template_access(template_doctype, template_id)
	doc = frappe.get_doc(template_doctype, template_id)
	if not doc.get("webflow_product"):
		return {"template": doc.name, "webflow_product": None}
	doc.webflow_product = None
	doc.flags.webflow_link_action = True
	doc.save()
	return {"template": doc.name, "webflow_product": None}
