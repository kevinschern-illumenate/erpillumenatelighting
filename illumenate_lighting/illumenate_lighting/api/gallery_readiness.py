# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Pure readiness checks for a Webflow Gallery (docs/WEBFLOW_GALLERY_SYNC.md, section 6).

Takes plain dicts only: the gallery as `doc.as_dict()` (child rows as lists of dicts), the brand config,
product Webflow references and the set of active series names.
"""

import re
from urllib.parse import urlparse

from illumenate_lighting.illumenate_lighting.api.gallery_schema import (
	APPLICATIONS,
	DESIGN_SERVICES,
	GALLERY_TYPES,
	SLUG_RE,
)

SEO_MAX_LENGTH = 160
VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "loom.com")


def is_public_file(url: str) -> bool:
	"""True for a public relative path (/files/...) or an https URL; false for private ERP files."""
	url = (url or "").strip()
	return bool(url) and "/private/" not in url


def _https_host(url: str) -> str | None:
	"""Return the host when `url` is a valid https URL, else None."""
	try:
		parsed = urlparse(url.strip())
	except ValueError:
		return None
	if parsed.scheme != "https" or not parsed.hostname:
		return None
	return parsed.hostname.lower()


def _is_supported_video(url: str) -> bool:
	host = _https_host(url)
	if not host:
		return False
	if any(host == h or host.endswith("." + h) for h in VIDEO_HOSTS):
		return True
	return urlparse(url.strip()).path.lower().endswith(".mp4")


def evaluate(gallery: dict, *, config: dict, product_refs: dict, active_series: set) -> dict:
	"""Return {"ready", "issues", "warnings", "dependencies"} for one gallery and one target brand."""
	issues: list[dict] = []
	warnings: list[dict] = []
	record = gallery.get("slug") or gallery.get("name") or ""

	def block(field, message, rec=None):
		issues.append({"record": rec or record, "field": field, "message": message})

	def warn(field, message):
		warnings.append({"record": record, "field": field, "message": message})

	if not (gallery.get("gallery_title") or "").strip():
		block("gallery_title", "Gallery title is required.")
	slug = gallery.get("slug")
	if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
		block("slug", "Slug is required and must be lowercase letters, digits and hyphens.")

	images = gallery.get("gallery_images") or []
	if not images:
		block("gallery_images", "At least one gallery image is required (the first is the hero image).")
	for idx, row in enumerate(images, start=1):
		if not is_public_file(row.get("image")):
			block("gallery_images", f"Image row {idx} must be a public file, not a private ERP file.")

	if gallery.get("gallery_type") not in GALLERY_TYPES:
		block("gallery_type", "Gallery type must be one of the allowed values.")
	for row in gallery.get("applications") or []:
		if row.get("application") not in APPLICATIONS:
			block("applications", f"Application {row.get('application')!r} is not an allowed value.")
	for row in gallery.get("services_provided") or []:
		if row.get("service") not in DESIGN_SERVICES:
			block("services_provided", f"Service {row.get('service')!r} is not an allowed value.")

	products = gallery.get("products_used") or []
	if not products:
		block("products_used", "At least one product used is required.")
	product_ids: dict[str, str | None] = {}
	series_used: set[str] = set()
	for row in products:
		name = row.get("product")
		series = row.get("series")
		if not series:
			block("products_used", f"Product {name} has no series.", name)
		elif series not in active_series:
			block("products_used", f"Series {series} is not an active series.", name)
		else:
			series_used.add(series)
		ref = product_refs.get(name) or {}
		item_id = ref.get("webflow_item_id")
		product_ids[name] = item_id
		if not item_id:
			block("products_used", f"Product {name} is not staged in this brand (no Webflow item ID).", name)

	credits = gallery.get("credits") or []
	integrators = [c for c in credits if c.get("credit_type") == "Integrator"]
	if not any((c.get("credit_name") or "").strip() for c in integrators):
		block("credits", "An Integrator credit with a name is required.")
	elif not any((c.get("website") or "").strip() for c in integrators):
		warn("credits", "The Integrator credit has no website.")
	for row in credits:
		website = (row.get("website") or "").strip()
		if website and not _https_host(website):
			block("credits", f"{row.get('credit_type')} website must be a valid https URL.")

	for link in re.split(r"[,\n]+", gallery.get("videos") or ""):
		link = link.strip()
		if link and not _is_supported_video(link):
			block("videos", f"Video link {link} must be https from YouTube, Vimeo, Loom or an .mp4 file.")

	if not config.get("is_active"):
		block("brand_active", "The target brand is not active.")
	if not config.get("sync_enabled"):
		block("sync_enabled", "Sync is not enabled for the target brand.")
	if not (config.get("collections") or {}).get("Galleries"):
		block("galleries_collection", "The brand has no Galleries collection ID.")

	seo = (gallery.get("seo_description") or "").strip()
	if not seo:
		warn("seo_description", "SEO description is empty.")
	elif len(seo) > SEO_MAX_LENGTH:
		warn("seo_description", f"SEO description is longer than {SEO_MAX_LENGTH} characters.")
	if not gallery.get("completion_date"):
		warn("completion_date", "No completion date (used for sorting).")
	if not (gallery.get("about") or "").strip():
		warn("about", "No about text.")

	return {
		"ready": not issues,
		"issues": issues,
		"warnings": warnings,
		"dependencies": {"products": product_ids, "series": sorted(series_used)},
	}
