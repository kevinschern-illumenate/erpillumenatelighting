# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Pure ERP gallery -> Webflow payload projection (docs/WEBFLOW_GALLERY_SYNC.md, section 5.1).

Takes plain dicts only: the gallery as `doc.as_dict()` and the product Webflow references. No Frappe.
"""

import datetime
import re
from html import escape
from urllib.parse import quote, urlsplit, urlunsplit

SCHEMA_VERSION = 1


def _encode_path(path: str) -> str:
	"""Percent-encode a URL path so Webflow can fetch it (spaces, `#`, `?`, non-ASCII file names).

	Idempotent: `/` separators and existing `%XX` escapes are kept, so encoding twice changes nothing. A `%`
	that is not part of an escape (a file named `100% cotton.png`) becomes `%25`.
	"""
	return quote(re.sub(r"%(?![0-9A-Fa-f]{2})", "%25", path), safe="/%")


def absolute_url(path: str, base_url: str) -> str:
	"""Public paths under the brand's site become absolute and percent-encoded; https URLs are encoded too.

	An ERP file URL is the raw file name (`/files/Lilium Static White_Hero.png`), and Webflow rejects a
	URL with spaces in it ("Invalid file url") when it imports the image on publish. A bare relative path
	(`files/a.jpg`) gets a leading slash first and is encoded as a whole, so a `#` or `?` in a file name is
	part of the name. An absolute https URL is a real URL: only its path is encoded. `http://` and `//host`
	forms are left unchanged: readiness already blocks them, so they never reach Webflow.
	"""
	path = (path or "").strip()
	lowered = path.lower()
	if not path or lowered.startswith(("http://", "//")):
		return path
	if lowered.startswith("https://"):
		parts = urlsplit(path)
		return urlunsplit((parts.scheme, parts.netloc, _encode_path(parts.path), parts.query, parts.fragment))
	if not path.startswith("/"):
		path = "/" + path
	return base_url.rstrip("/") + _encode_path(path)


def _text(value) -> str:
	return (value or "").strip() if isinstance(value, str) else ""


def _date(value) -> str | None:
	if not value:
		return None
	if isinstance(value, datetime.date | datetime.datetime):
		return value.strftime("%Y-%m-%d")
	return str(value).strip()[:10] or None


def _names(gallery: dict, table: str, field: str) -> list[str]:
	return [row[field] for row in gallery.get(table) or [] if row.get(field)]


def _images(gallery: dict, base_url: str) -> list[dict]:
	images = []
	for row in gallery.get("gallery_images") or []:
		url = _text(row.get("image"))
		if url:
			images.append({"url": absolute_url(url, base_url), "alt": _text(row.get("alt_text"))})
	return images


def _product_notes(rows: list[dict], product_refs: dict) -> str:
	paragraphs = []
	for row in rows:
		product, note = row.get("product"), _text(row.get("note"))
		if product and note:
			name = (product_refs.get(product) or {}).get("name") or product
			paragraphs.append(f"<p>{escape(name)}: {escape(note)}</p>")
	return "".join(paragraphs)


def _custom_items(rows: list[dict], base_url: str) -> str:
	parts = []
	for row in rows:
		name = _text(row.get("item_name"))
		parts.append(f"<p>{escape(name)}: {escape(_text(row.get('detail')))}</p>")
		image = _text(row.get("image"))
		if image:
			parts.append(f'<img src="{escape(absolute_url(image, base_url))}" alt="{escape(name)}">')
	return "".join(parts)


def build_payload(gallery: dict, *, base_url: str, product_refs: dict) -> dict:
	images = _images(gallery, base_url)
	products = gallery.get("products_used") or []

	series_used: list[str] = []
	for row in products:
		series = row.get("series")
		if series and series not in series_used:
			series_used.append(series)

	item_ids = []
	for row in products:
		item_id = (product_refs.get(row.get("product")) or {}).get("webflow_item_id")
		if row.get("product") and item_id and item_id not in item_ids:
			item_ids.append(item_id)

	credits = {}
	for row in gallery.get("credits") or []:
		name = _text(row.get("credit_name"))
		if name:
			credits[row.get("credit_type")] = {"name": name, "website": _text(row.get("website"))}

	slug = gallery.get("slug") or gallery.get("name")
	return {
		"schema_version": SCHEMA_VERSION,
		"erp_sync_id": gallery.get("name") or slug,
		"slug": slug,
		"name": gallery.get("gallery_title"),
		"featured": bool(gallery.get("featured")),
		"hero_image": images[0] if images else None,
		"gallery_images": images,
		"seo_description": gallery.get("seo_description") or "",
		"about": gallery.get("about") or "",
		"case_study_html": gallery.get("case_study") or "",
		"gallery_type": gallery.get("gallery_type"),
		"applications": _names(gallery, "applications", "application"),
		"services_provided": _names(gallery, "services_provided", "service"),
		"series_used": series_used,
		"product_item_ids": item_ids,
		"product_notes_html": _product_notes(products, product_refs),
		"quote": gallery.get("quote") or "",
		"quote_attribution": gallery.get("quote_attribution") or "",
		"location": gallery.get("location") or "",
		"completion_date": _date(gallery.get("completion_date")),
		"credits": credits,
		"videos": [v for v in re.split(r"[\s,]+", gallery.get("videos") or "") if v],
		"custom_items_html": _custom_items(gallery.get("custom_items") or [], base_url),
	}
