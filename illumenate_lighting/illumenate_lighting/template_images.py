"""Images the spec sheet shows, stored on the template's own tables (owner, 2026-11-02).

Filled on every template save (``refresh``, from ``template_listing.refresh_template``):

- Kit components: ``component_image`` on each row is the image of its component type: the
  first row of that type with an item, that item's template item (``variant_of``) image, else
  the item's own image. The same lookup the Webflow Product used for its kit groups.
  ``component_description`` is the item's variant attribute for its type: Profile Finish, Lens
  Lens Color, Endcap Set Endcap Color (owner, 2026-11-03). Other types, and items without that
  attribute, keep the Description typed on the row.
- Certifications: ``badge_image`` on each row is the linked certification's dark badge for the
  template's brand: ilLumenate ``badge_image_dark``, 206 Lighting
  ``badge_image_dark_206``.

Values are stored as Frappe keeps them (``/files/...``); readers make them absolute.
"""

import frappe

CERTIFICATION = "ilL-Attribute-Certification"
BADGE_FIELDS = {
	"illumenate": "badge_image_dark",
	"lighting_206": "badge_image_dark_206",
}


def item_image(item_code):
	"""The template item's image (``variant_of``), else the item's own image."""
	if not item_code:
		return None
	row = frappe.db.get_value("Item", item_code, ["variant_of", "image"], as_dict=True)
	if not row:
		return None
	if row.variant_of:
		image = frappe.db.get_value("Item", row.variant_of, "image")
		if image:
			return image
	return row.image


def fill_component_images(template, image_of=item_image, describe=None):
	describe = describe or variant_attribute_value
	images = {}
	for row in template.get("kit_components") or []:
		kind = row.get("component_type")
		if kind and kind not in images and row.get("component_item"):
			images[kind] = image_of(row.component_item)
	for row in template.get("kit_components") or []:
		row.component_image = images.get(row.get("component_type"))
		value = describe(row.get("component_type"), row.get("component_item"))
		if value:
			row.component_description = value


# The variant attribute that names each component (owner, 2026-11-03). Other component types
# keep the Description typed on the row.
DESCRIPTION_ATTRIBUTES = {"Profile": "Finish", "Lens": "Lens Color", "Endcap Set": "Endcap Color"}


def variant_attribute_value(component_type, item_code):
	"""The item's value for its component type's attribute (Item > Variants > Attributes)."""
	attribute = DESCRIPTION_ATTRIBUTES.get(component_type)
	if not attribute or not item_code:
		return None
	for row in frappe.get_all(
		"Item Variant Attribute",
		filters={"parenttype": "Item", "parent": item_code},
		fields=["attribute", "attribute_value"],
	):
		if (row.attribute or "").strip().lower() == attribute.lower() and (row.attribute_value or "").strip():
			return row.attribute_value.strip()
	return None


def template_brand(template):
	brands = [
		row.brand for row in template.get("target_brands") or [] if row.get("enabled") and row.get("brand")
	]
	return brands[0] if brands else None


def fill_certification_badges(template, badge_of=None):
	field = BADGE_FIELDS.get(template_brand(template) or "illumenate")
	if badge_of is None:

		def badge_of(name):
			if not field or not frappe.get_meta(CERTIFICATION).has_field(field):
				return None
			return frappe.db.get_value(CERTIFICATION, name, field)

	for row in template.get("certifications") or []:
		row.badge_image = badge_of(row.certification) if row.get("certification") else None


def refresh(template):
	if template.get("kit_components"):
		fill_component_images(template)
	if template.get("certifications"):
		fill_certification_badges(template)
