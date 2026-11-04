"""Duplicate a Webflow Product or a family template as a new draft (hardening plan 5.3).

The exclude lists below are mirrored in docs/B2B_AUTHORING_FIELD_REGISTER.md
("Duplicate as new product") and a unit test keeps the two in step.
"""

import re

import frappe

from illumenate_lighting.illumenate_lighting.portal.staff import allowed
from illumenate_lighting.illumenate_lighting.web_listing_schema import WEBFLOW_PRODUCT_LINKS

PRODUCT = "ilL-Webflow-Product"
TEMPLATES = tuple(WEBFLOW_PRODUCT_LINKS)
DRAFT_STATUS = "Draft"

# Always cleared: identity, Webflow sync/publication state and back-links. Timestamps,
# owner and names are reset by frappe.copy_doc.
PRODUCT_EXCLUDES = (
	"product_name",
	"product_slug",
	"is_active",
	"webflow_item_id",
	"webflow_collection_slug",
	"last_synced_at",
	"sync_status",
	"sync_error_message",
	"sync_targets",
	# Saving reciprocates compatibility onto the other products, so staff add it deliberately.
	"compatible_products",
)
TEMPLATE_EXCLUDES = ("template_code", "template_name", "is_active", "webflow_product")

# Cleared unless the caller keeps media. Kept media links the same File, it is not copied.
PRODUCT_MEDIA = ("featured_image", "dimensions_image", "series_family_image", "gallery_images", "documents")
TEMPLATE_MEDIA = (
	"hero_image",
	"hero_image_alt",
	"image",
	"diagram_icon",
	"photometric_image",
	"tm30_chart_image",
	"polar_chart_image",
	"spec_sheet",
)

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{0,138}$")


def flag(value):
	return str(value).strip().lower() in ("1", "true", "yes", "on")


def slugify(text):
	return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", str(text or "").lower())).strip("-")[:120]


def require_author(doctype):
	if doctype != PRODUCT and doctype not in TEMPLATES:
		frappe.throw("Only Webflow Products and family templates can be duplicated", frappe.ValidationError)
	if not allowed("catalog") or not frappe.has_permission(doctype, "create"):
		frappe.throw("Product authoring access required", frappe.PermissionError)


def clear(doc, fields):
	meta = frappe.get_meta(doc.doctype)
	for field in fields:
		if not meta.has_field(field):
			continue
		definition = meta.get_field(field)
		if definition.fieldtype == "Table":
			doc.set(field, [])
		else:
			doc.set(field, definition.default or None)


def clone_template(doctype, name, code, title=None, include_media=True):
	if not frappe.has_permission(doctype, "create"):
		frappe.throw("Not permitted to create that template", frappe.PermissionError)
	source = frappe.get_doc(doctype, name)
	if not frappe.has_permission(doctype, "read", doc=source):
		frappe.throw("Not permitted to read that template", frappe.PermissionError)
	code = str(code or "").strip()
	if not CODE.match(code):
		frappe.throw("Enter a template code of letters, numbers, spaces, dots, dashes or slashes", frappe.ValidationError)
	if frappe.db.exists(doctype, code):
		frappe.throw(f"Template {code} already exists", frappe.ValidationError)
	doc = frappe.copy_doc(source)
	doc.flags.in_copy = True
	clear(doc, TEMPLATE_EXCLUDES + (() if include_media else TEMPLATE_MEDIA))
	doc.template_code = code
	doc.template_name = str(title or "").strip()[:140] or code
	doc.product_status = DRAFT_STATUS
	doc.insert()
	return doc


def clone_product(name, product_name, slug=None, include_media=True, template_code=None):
	source = frappe.get_doc(PRODUCT, name)
	if not frappe.has_permission(PRODUCT, "read", doc=source):
		frappe.throw("Not permitted to read that product", frappe.PermissionError)
	product_name = str(product_name or "").strip()[:140]
	if not product_name:
		frappe.throw("Enter the new product name", frappe.ValidationError)
	slug = slugify(slug or product_name)
	if not SLUG.match(slug):
		frappe.throw("Enter a slug of lowercase letters, numbers and dashes", frappe.ValidationError)
	if frappe.db.exists(PRODUCT, slug):
		frappe.throw(f"A product with the slug {slug} already exists", frappe.ValidationError)
	doc = frappe.copy_doc(source)
	doc.flags.in_copy = True
	clear(doc, PRODUCT_EXCLUDES + (() if include_media else PRODUCT_MEDIA))
	doc.product_name = product_name
	doc.product_slug = slug
	doc.is_active = 0
	template = None
	for template_doctype, field in WEBFLOW_PRODUCT_LINKS.items():
		linked = source.get(field)
		# A template points back at one product, so a clone keeps no shared template link.
		doc.set(field, None)
		if linked and template_code and template is None:
			template = clone_template(template_doctype, linked, template_code, product_name, include_media)
			doc.set(field, template.name)
	if template_code and template is None:
		frappe.throw("This product has no family template to duplicate", frappe.ValidationError)
	doc.insert()
	return doc, template


@frappe.whitelist(methods=["POST"])
def duplicate(doctype, name, new_name, new_slug=None, include_media=1, template_code=None, template_name=None):
	"""Create a draft copy. Products may also copy their family template (template_code)."""
	require_author(doctype)
	keep_media = flag(include_media)
	if doctype == PRODUCT:
		product, template = clone_product(name, new_name, new_slug, keep_media, template_code or None)
		result = {"doctype": PRODUCT, "name": product.name, "readiness": "product"}
		if template:
			result["template"] = {"doctype": template.doctype, "name": template.name}
		return result
	template = clone_template(doctype, name, new_name, template_name, keep_media)
	return {"doctype": doctype, "name": template.name, "readiness": "template"}
