"""The product-type cards on /portal/configure: which a user sees, where each leads, its photo.

The cards come from the Product Finder's family question (``presentation.chooser``). This
module makes each one lead somewhere useful:

- A family the site has not rolled out to the user is left out (opening it would refuse).
- A family with nothing to configure (no offered templates, or for controllers no
  configurable listing) leads to its catalog listings instead, for catalog users; with no
  listings either, it is left out.
- A catalog card (accessories and parts) is left out when the catalog has nothing to show.

Each card shows a product photo from its own family, in this order: an image staff uploaded
to the Finder option; the main image of a portal listing in the family (template hero image,
featured image, gallery, the same order the catalog uses); a photo of an enabled Item in the
family's Item Groups. Quiz artwork bundled with the app is kept only when there is no photo.
"""

import re
from urllib.parse import urlencode

import frappe

PRODUCT = "ilL-Webflow-Product"
# Artwork shipped with the app for the seeded Finder options; a stand-in, not a product photo.
BUNDLED_ART = "/assets/illumenate_lighting/product_finder/"
CATALOG = "catalog"
# Webflow Product types listed under each card.
LISTING_TYPES = {
	"Linear Fixture": ("Fixture Template",),
	"LED Tape": ("LED Tape",),
	"COB Tape": ("COB Tape",),
	"LED Neon": ("LED Neon",),
	"LED Sheet": ("LED Sheet",),
	"Extrusion Kit": ("Extrusion Kit",),
	"Driver": ("Driver",),
	"Controller": ("Controller",),
	CATALOG: ("Accessory", "Component"),
}
# Templates each family configures from. Tape and neon are left out: with no template the
# configurator still offers spec-derived options, so they always have something to configure.
# Controllers are configured from configurable listings, counted from the listings themselves.
TEMPLATES = {
	"Linear Fixture": "ilL-Fixture-Template",
	"LED Sheet": "ilL-LED-Sheet-Template",
	"Extrusion Kit": "ilL-Extrusion-Kit-Template",
	"Driver": "ilL-Driver-Template",
}
# Item Groups whose Item photos stand in when no listing in the family has one.
ITEM_GROUPS = {
	"Linear Fixture": ("Linear Fixture", "Linear Fixtures"),
	"LED Tape": ("LED Tape",),
	"COB Tape": ("COB Tape",),
	"LED Neon": ("LED Neon",),
	"LED Sheet": ("LED Sheet", "LED Sheets"),
	"Extrusion Kit": ("Extrusion Kit", "Extrusion Kits"),
	"Driver": ("Power Supplies", "Power Supply", "Drivers"),
	"Controller": ("Controls", "Controllers"),
	CATALOG: ("Accessories", "LED Accessories", "Components", "Endcaps", "Mounting", "Lenses"),
}
# Finder swatches are CSS colours or gradients typed in Desk; anything else is dropped.
SWATCH = re.compile(r"^[#(),.%\w\s-]{1,160}$")
STILL = (".jpg", ".jpeg", ".png", ".webp", ".avif")


def cards(options, query, show_pricing):
	"""Return the chooser ``options`` a user can open, each with its photo and destination.

	``query`` holds the schedule context carried on every link; ``show_pricing`` is whether
	the user may browse the catalog (EDIT collaborators configure for one schedule only).
	"""
	from illumenate_lighting.illumenate_lighting.api.configuration_contract import FAMILY_ALIASES
	from illumenate_lighting.illumenate_lighting.portal import rollout

	listings = _listings()
	photos = _photos(listings)
	context = {k: query[k] for k in ("schedule", "line_key", "line_idx", "draft", "finder") if query.get(k)}
	result = []
	for option in options:
		card = dict(option)
		if card.get("routesTo") == CATALOG or str(card.get("href") or "").startswith("/portal/products"):
			key = CATALOG
			if not show_pricing or not listings.get(key):
				continue
		else:
			key = FAMILY_ALIASES.get(card.get("value"), card.get("value"))
			if key in LISTING_TYPES:
				if not rollout.available(key):
					continue
				if not _configurable(key, listings):
					if not show_pricing or not listings.get(key):
						continue
					card["href"] = "/portal/products?" + urlencode(
						{**context, "type": ",".join(LISTING_TYPES[key])}
					)
					card["badge"] = card.get("badge") or "Browse catalog"
					card["routesTo"] = CATALOG
		card.update(_picture(card, photos.get(key)))
		result.append(card)
	return result


def _picture(card, photo):
	"""The card's ``image``/``image_alt``, and a ``swatch`` CSS background for a card without one."""
	uploaded = card.get("image") and not str(card["image"]).startswith(BUNDLED_ART)
	if uploaded:
		image, alt = card["image"], card.get("label") or ""
	elif photo:
		image, alt = photo
	else:
		image, alt = card.get("image"), ""
	swatch = card.get("color") or ""
	return {"image": image or None, "image_alt": alt, "swatch": swatch if SWATCH.match(swatch) else ""}


def _configurable(family, listings):
	if family == "Controller":
		return any(row.get("is_configurable") for row in listings.get(family, ()))
	doctype = TEMPLATES.get(family)
	if not doctype:
		return True
	from illumenate_lighting.illumenate_lighting.portal_listing import template_filters

	return bool(frappe.db.count(doctype, template_filters()))


def _listings():
	"""``{card key: [listing]}`` for the Webflow Products the user sees on the portal."""
	from illumenate_lighting.illumenate_lighting.portal_listing import LINK_FIELDS, portal_condition

	types = sorted({t for values in LISTING_TYPES.values() for t in values})
	# A listing linked to one of our templates, rather than a standalone (often third-party) one.
	linked = " or ".join(f"ifnull({field}, '') != ''" for field in LINK_FIELDS)
	rows = frappe.db.sql(
		f"""select name, product_name, product_type, is_configurable, ({linked or "0"}) as linked
		from `tab{PRODUCT}`
		where product_type in %(types)s and {portal_condition()}
		order by product_name asc, name asc""",
		{"types": tuple(types)},
		as_dict=True,
	)
	keys = {t: key for key, values in LISTING_TYPES.items() for t in values}
	grouped = {}
	for row in rows:
		grouped.setdefault(keys[row.product_type], []).append(row)
	return grouped


def _photos(listings):
	"""``{card key: (url, alt)}``: one product photo per card, from listings, then Items."""
	from illumenate_lighting.illumenate_lighting.api.product_projection import (
		resolve_product_images,
		safe_document_url,
	)

	names = [row.name for rows in listings.values() for row in rows]
	resolved = resolve_product_images(PRODUCT, names) if names else {}
	photos = {}
	for key, rows in listings.items():
		candidates = [(row, safe_document_url((resolved.get(row.name) or {}).get("primary"))) for row in rows]
		# Configurable products first (what the card leads to), then our own products over
		# standalone listings, then still images stored on this site.
		ranked = sorted(
			((row, url) for row, url in candidates if url),
			key=lambda pair: (not pair[0].get("is_configurable"), not pair[0].get("linked"), _rank(pair[1])),
		)
		if ranked:
			row, url = ranked[0]
			photos[key] = (url, (resolved.get(row.name) or {}).get("primary_alt") or row.product_name or "")
	missing = [key for key in LISTING_TYPES if key not in photos]
	if missing:
		photos.update(_item_photos(missing))
	return photos


def _item_photos(keys):
	groups = {group: key for key in keys for group in ITEM_GROUPS.get(key, ())}
	if not groups:
		return {}
	from illumenate_lighting.illumenate_lighting.api.product_projection import safe_document_url

	rows = frappe.get_all(
		"Item",
		filters={"item_group": ["in", list(groups)], "disabled": 0, "image": ["is", "set"]},
		fields=["item_group", "item_name", "image"],
		order_by="item_name asc",
		ignore_permissions=True,
	)
	photos = {}
	for row in sorted(rows, key=lambda r: _rank(r.image or "")):
		key, url = groups.get(row.item_group), safe_document_url(row.image)
		if key and url and key not in photos:
			photos[key] = (url, row.item_name or "")
	return photos


def _rank(url):
	"""Sort key preferring still images stored on this site over animations and remote links."""
	path = url.split("?", 1)[0].lower()
	animated = "animated" in path or path.endswith(".gif") or not path.endswith(STILL)
	return (animated, not path.startswith("/files/"))
