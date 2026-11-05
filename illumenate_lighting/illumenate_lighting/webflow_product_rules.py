# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Webflow Product rules from the owner's changes of 2026-11-05 (plan 4.17).

- Features: the ``web_features`` table (Title, Description) is written into the hidden
  ``features`` JSON on every save, in the shape the other readers already use.
- 16:9: a warning (never an error) when the featured image or a gallery image is not 16:9.
- Power supplies: the template's compatible power supplies become calculated "Recommended
  With" rows in ``compatible_products``; rows added by hand are never touched.
"""

import json

import frappe
from frappe import _

RECOMMENDED = "Recommended With"
RATIO = 16 / 9
RATIO_TOLERANCE = 0.01


# --- Features ---------------------------------------------------------------------------


def features_json(rows):
	"""Pure: ``[{"title", "description"}, ...]`` for the rows with a title or a description,
	in table order; None when there are none."""
	features = [
		{"title": (row.get("title") or "").strip(), "description": (row.get("description") or "").strip()}
		for row in rows or []
	]
	features = [row for row in features if row["title"] or row["description"]]
	return json.dumps(features, ensure_ascii=False) if features else None


def feature_rows(value):
	"""Pure: table rows from a stored ``features`` value. None when it cannot be read.

	Accepts a JSON string or a list; each item is an object with ``title`` and
	``description`` (a plain string is taken as a title).
	"""
	if value in (None, ""):
		return []
	try:
		data = json.loads(value) if isinstance(value, str) else value
	except ValueError:
		return None
	if isinstance(data, dict):
		data = [data]
	if not isinstance(data, list):
		return None
	rows = []
	for item in data:
		if isinstance(item, str):
			rows.append({"title": item.strip(), "description": ""})
		elif isinstance(item, dict):
			rows.append(
				{
					"title": str(item.get("title") or "").strip(),
					"description": str(item.get("description") or "").strip(),
				}
			)
		else:
			return None
	return [row for row in rows if row["title"] or row["description"]]


def write_features(doc):
	"""Write ``web_features`` into ``features`` (Webflow Product before_save)."""
	if not doc.meta.has_field("web_features"):
		return
	doc.features = features_json(doc.get("web_features"))


# --- 16:9 ---------------------------------------------------------------------------------


def is_16_9(width, height):
	"""Pure: True when width:height is within 1% of 16:9."""
	if not width or not height:
		return True
	return abs((width / height) / RATIO - 1) <= RATIO_TOLERANCE


def image_size(file_url):
	"""(width, height) of an uploaded image, or None when it cannot be read (SVG, external)."""
	if not file_url or file_url.lower().split("?")[0].endswith(".svg"):
		return None
	try:
		from io import BytesIO

		from PIL import Image

		name = frappe.db.get_value("File", {"file_url": file_url}, "name")
		if not name:
			return None
		content = frappe.get_doc("File", name).get_content()
		with Image.open(BytesIO(content)) as image:
			return image.size
	except Exception:
		return None


def _changed(doc, fieldname):
	return doc.is_new() or doc.has_value_changed(fieldname)


def warn_aspect_ratios(doc):
	"""Warn (never block) when the featured image or a gallery image is not 16:9."""
	notes = []
	if doc.get("featured_image") and _changed(doc, "featured_image"):
		size = image_size(doc.featured_image)
		if size and not is_16_9(*size):
			notes.append(_("Featured Image is {0} x {1}, not 16:9.").format(*size))
	before = doc.get_doc_before_save() if not doc.is_new() else None
	old = {row.image for row in (before.get("gallery_images") if before else [])}
	for row in doc.get("gallery_images") or []:
		if not row.get("image") or row.image in old:
			continue
		size = image_size(row.image)
		if size and not is_16_9(*size):
			notes.append(_("Gallery image row {0} is {1} x {2}, not 16:9.").format(row.idx, *size))
	if notes:
		frappe.msgprint(
			"<br>".join(notes) + "<br>" + _("Use 16:9 images (for example 1920 x 1080)."),
			title=_("Image size"),
			indicator="orange",
		)


# --- Power supplies as compatible products ------------------------------------------------


def calculated_compatibility(rows, products, managed):
	"""Pure: the compatible product rows after the calculation.

	``rows`` are the current rows (dicts), ``products`` the power supply products to
	recommend, in order, and ``managed`` every power supply product. Calculated
	Recommended With rows pointing at a power supply product are replaced; every other row
	is kept as it is. A product that already has a hand-added Recommended With row is not
	added again.
	"""
	kept = [
		row
		for row in rows
		if not (
			row.get("is_calculated")
			and row.get("relationship_type") == RECOMMENDED
			and row.get("related_product") in managed
		)
	]
	present = {row.get("related_product") for row in kept if row.get("relationship_type") == RECOMMENDED}
	added = [
		{"related_product": product, "relationship_type": RECOMMENDED, "is_calculated": 1}
		for product in products
		if product not in present
	]
	return kept + added


def linked_template(doc):
	"""(doctype, name) of the template this product links to, or (None, None)."""
	from illumenate_lighting.illumenate_lighting.web_listing_schema import WEBFLOW_PRODUCT_LINKS

	for doctype, fieldname in WEBFLOW_PRODUCT_LINKS.items():
		if doc.get(fieldname):
			return doctype, doc.get(fieldname)
	return None, None


def recommend_power_supplies(doc):
	"""Fill the calculated Recommended With rows from the template's power supplies."""
	from illumenate_lighting.illumenate_lighting import template_power_supplies as supplies

	doctype, name = linked_template(doc)
	if doctype not in supplies.DOCTYPES:
		part_numbers = []
	else:
		part_numbers = frappe.get_all(
			"ilL-Child-Comp-Power",
			filters={"parenttype": doctype, "parent": name, "parentfield": supplies.FIELD},
			pluck="part_number",
			order_by="idx asc",
		)
	products, missing = supplies.power_supply_products(part_numbers)
	products = [product for product in products if product != doc.name]
	current = [
		row.as_dict() if hasattr(row, "as_dict") else dict(row)
		for row in doc.get("compatible_products") or []
	]
	rows = calculated_compatibility(current, products, supplies.power_supply_product_names())
	if [(r.get("related_product"), r.get("relationship_type"), r.get("is_calculated")) for r in rows] != [
		(r.get("related_product"), r.get("relationship_type"), r.get("is_calculated")) for r in current
	]:
		doc.set("compatible_products", rows)
	if missing:
		frappe.msgprint(
			_("No power supply Webflow Product found for: {0}").format(", ".join(missing)),
			title=_("Compatible power supplies"),
			indicator="orange",
		)
