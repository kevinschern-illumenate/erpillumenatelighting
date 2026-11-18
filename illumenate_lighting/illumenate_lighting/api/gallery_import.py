"""Import of the existing Webflow galleries (docs/WEBFLOW_GALLERY_SYNC.md, section 9a).

ERP holds no Webflow token. The controller exports the Galleries collection items (as the Webflow v2
list-items API returns them) and passes them to ``import_galleries``. ``map_webflow_item`` is pure.
Images come from the public Webflow CDN and are attached as public ERP files; nothing here calls the
Webflow API.
"""

import json
import os
import re
from html import unescape
from urllib.parse import unquote, urlparse

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.gallery_schema import (
	APPLICATIONS,
	CREDIT_FIELDS,
	DESIGN_SERVICES,
	GALLERY_TYPES,
)
from illumenate_lighting.illumenate_lighting.portal.staff import require

GALLERY = "ilL-Webflow-Gallery"
PRODUCT = "ilL-Webflow-Product"
SERIES = "ilL-Attribute-Series"
SYNC_STATE = "ilL-Child-Webflow-Sync-State"
BRAND = "ilL-Webflow-Brand"
CUSTOM_ALIASES = {"custom led tape", "custom extrusion kit"}
DEFAULT_SKIP = frozenset({"boutique-hotel-lounge"})
_TOKEN = re.compile(r"<p\b[^>]*>(.*?)</p>|<img\b[^>]*>", re.I | re.S)
_IMG = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"'][^>]*>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")


def _text(value) -> str:
	return value.strip() if isinstance(value, str) else ""


def _plain(html: str) -> str:
	return " ".join(unescape(_TAG.sub(" ", html or "")).split())


def _lookup(allowed, value):
	lowered = {entry.lower(): entry for entry in allowed}
	return lowered.get(value.strip().lower())


def _csv(value) -> list[str]:
	return [part.strip() for part in _text(value).split(",") if part.strip()]


def _images(data: dict, report: list[str]) -> list[dict]:
	rows = []
	for entry in data.get("gallery") or []:
		url = _text((entry or {}).get("url"))
		if url:
			rows.append({"image": url, "alt_text": _text(entry.get("alt")) or None})
	hero = data.get("featured-image") or {}
	hero_url = _text(hero.get("url")) if isinstance(hero, dict) else ""
	if hero_url and not rows:
		rows.append({"image": hero_url, "alt_text": _text(hero.get("alt")) or None})
	elif hero_url and hero_url != rows[0]["image"]:
		report.append("featured-image differs from the first gallery image; the first one is the hero")
	return rows


def _credits(data: dict) -> list[dict]:
	rows = []
	for credit_type, (name_field, site_field) in CREDIT_FIELDS.items():
		name = _text(data.get(name_field))
		if name:
			website = _text(data.get(site_field)) or None
			rows.append({"credit_type": credit_type, "credit_name": name, "website": website})
	return rows


def _custom_items(html, report: list[str]) -> list[dict]:
	items = []
	for match in _TOKEN.finditer(html or ""):
		inner = match.group(1)
		if inner is None:  # a bare <img>
			urls, text = _IMG.findall(match.group(0)), ""
		else:
			urls, text = _IMG.findall(inner), _plain(_IMG.sub("", inner))
		if text:
			name, _sep, detail = text.partition(":")
			items.append({"item_name": name.strip(), "detail": detail.strip() or None, "image": None})
		if urls:
			if items:
				items[-1]["image"] = items[-1]["image"] or urls[0]
			else:
				report.append("custom-items: an image before any item was ignored")
	return items


def _series(data: dict, series_by_name: dict, report: list[str]) -> list[str]:
	names = _csv(data.get("series-used")) or ["Custom"]
	found = []
	for name in names:
		label = "Custom" if name.lower() in CUSTOM_ALIASES else name
		docname = series_by_name.get(label.lower())
		if not docname:
			report.append(f"Series not found, left off: {label}")
		elif docname not in found:
			found.append(docname)
	return found


def _products(data, series, product_by_webflow_id, product_series, report) -> list[dict]:
	rows, remaining = [], list(series)
	own = product_series or {}
	for webflow_id in data.get("products-used") or []:
		product = product_by_webflow_id.get(webflow_id)
		if not product:
			report.append(f"Product {webflow_id} is not synced for this brand; row left out")
			continue
		matched = own.get(product)
		if matched in remaining:
			remaining.remove(matched)
		else:
			matched = None
		rows.append({"product": product, "series": matched, "note": None})
	rows.extend({"product": None, "series": name, "note": None} for name in remaining)
	return rows


def _attach_notes(html, rows: list[dict], product_names: dict, report: list[str]):
	for match in re.finditer(r"<p\b[^>]*>(.*?)</p>", html or "", re.I | re.S):
		text = _plain(match.group(1))
		if not text:
			continue
		label, sep, note = text.partition(":")
		row = None
		if sep:
			wanted = label.strip().lower()
			row = next(
				(
					r
					for r in rows
					if r["product"]
					and wanted in (r["product"].lower(), _text(product_names.get(r["product"])).lower())
				),
				None,
			)
		if row:
			row["note"] = note.strip() or None
		else:
			report.append(f"Product note not matched to a product: {text}")


def _lists(data: dict, report: list[str]):
	kind = _text(data.get("project-type"))
	gallery_type = _lookup(GALLERY_TYPES, kind) if kind else None
	if kind and not gallery_type:
		report.append(f"Unknown project type left empty: {kind}")
	picked = {}
	for field, allowed, key in (
		("applications", APPLICATIONS, "application"),
		("services-provided", DESIGN_SERVICES, "service"),
	):
		picked[key] = []
		for value in _csv(data.get(field)):
			match = _lookup(allowed, value)
			if not match:
				report.append(f"Unknown {key} dropped: {value}")
			elif {key: match} not in picked[key]:
				picked[key].append({key: match})
	return gallery_type, picked["application"], picked["service"]


def map_webflow_item(
	item: dict,
	*,
	series_by_name: dict,
	product_by_webflow_id: dict,
	skip_slugs=DEFAULT_SKIP,
	product_series: dict | None = None,
	product_names: dict | None = None,
) -> tuple[dict | None, list[str]]:
	"""Map one Webflow item to the gallery dict shape; returns (None, report) when it is skipped."""
	data = item.get("fieldData") or {}
	slug = _text(data.get("slug"))
	if slug in skip_slugs:
		return None, [f"{slug}: skipped (excluded from import)"]
	if item.get("isArchived"):
		return None, [f"{slug}: skipped (archived in Webflow)"]
	report = []
	if item.get("isDraft"):
		report.append(f"{slug}: draft in Webflow, imported inactive")
	gallery_type, applications, services = _lists(data, report)
	series = _series(data, series_by_name, report)
	products = _products(data, series, product_by_webflow_id, product_series, report)
	_attach_notes(data.get("product-notes"), products, product_names or {}, report)
	gallery = {
		"webflow_item_id": item.get("id"),
		"slug": slug,
		"gallery_title": _text(data.get("name")) or slug,
		"is_active": 0 if item.get("isDraft") else 1,
		"featured": 1 if data.get("featured") else 0,
		"seo_description": _text(data.get("short-description")) or None,
		"about": _text(data.get("about")) or None,
		"case_study": _text(data.get("case-study")) or None,
		"gallery_type": gallery_type,
		"quote": _text(data.get("quote")) or None,
		"quote_attribution": _text(data.get("quote-attribution")) or None,
		"location": _text(data.get("location")) or None,
		"completion_date": _text(data.get("completion-date"))[:10] or None,
		"videos": _text(data.get("videos")) or None,
		"gallery_images": _images(data, report),
		"applications": applications,
		"services_provided": services,
		"products_used": products,
		"credits": _credits(data),
		"custom_items": _custom_items(data.get("custom-items"), report),
	}
	return gallery, [f"{slug}: {line}" if not line.startswith(slug) else line for line in report]


# ---------------------------------------------------------------------------------------------------
# Database side


def _download(url: str) -> bytes:
	import requests

	response = requests.get(url, timeout=30)
	response.raise_for_status()
	return response.content


def _lookups(brand: str):
	series = {row.name.lower(): row.name for row in frappe.get_all(SERIES, fields=["name"])}
	states = frappe.get_all(
		SYNC_STATE,
		filters={"parenttype": PRODUCT, "brand": brand, "sync_status": "Synced"},
		fields=["parent", "webflow_item_id"],
	)
	by_id = {row.webflow_item_id: row.parent for row in states if row.webflow_item_id}
	products = frappe.get_all(
		PRODUCT,
		filters={"name": ["in", list(by_id.values())]},
		fields=["name", "series", "product_name"],
	)
	return (
		series,
		by_id,
		{row.name: row.series for row in products if row.series},
		{row.name: row.product_name for row in products if row.product_name},
	)


def _file_name(slug: str, index: int, url: str) -> str:
	base = os.path.basename(unquote(urlparse(url).path)) or "image.jpg"
	return f"{slug}-{index}-{base}"[:140]


def _attach(slug: str, index: int, url: str, report: list[str]) -> str | None:
	try:
		content = _download(url)
		doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": _file_name(slug, index, url),
				"content": content,
				"attached_to_doctype": GALLERY,
				"attached_to_name": slug,
				"is_private": 0,
			}
		).insert(ignore_permissions=True)
		return doc.file_url
	except Exception as error:
		report.append(f"{slug}: image not imported ({url}): {error}")
		return None


def _create(mapped: dict, brand: str, report: list[str]):
	slug = mapped["slug"]
	images, custom = mapped.pop("gallery_images"), mapped.pop("custom_items")
	item_id = mapped.pop("webflow_item_id")
	doc = frappe.get_doc(
		{
			"doctype": GALLERY,
			**mapped,
			"target_brands": [{"brand": brand, "enabled": 1}],
			"sync_targets": [{"brand": brand, "webflow_item_id": item_id, "sync_status": "Pending"}],
		}
	).insert(ignore_permissions=True)
	counter = 0
	rows = []
	for row in images:
		counter += 1
		url = _attach(slug, counter, row["image"], report)
		if url:
			rows.append({**row, "image": url})
	items = []
	for row in custom:
		if row["image"]:
			counter += 1
			row = {**row, "image": _attach(slug, counter, row["image"], report)}
		items.append(row)
	doc.set("gallery_images", rows)
	doc.set("custom_items", items)
	doc.save(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def import_galleries(items, brand, commit=0) -> dict:
	"""Import exported Webflow gallery items; a dry run unless `commit` is 1."""
	require("catalog")
	if isinstance(items, str):
		items = json.loads(items)
	if not isinstance(items, list):
		frappe.throw(_("items must be a list of Webflow CMS items"))
	if not frappe.db.exists(BRAND, brand):
		frappe.throw(_("Unknown brand {0}").format(brand))
	commit = str(commit).lower() in ("1", "true")
	series, by_id, product_series, product_names = _lookups(brand)
	report, created, would_create = [], [], []
	for raw in items:
		slug = _text(((raw or {}).get("fieldData") or {}).get("slug"))
		mapped, lines = map_webflow_item(
			raw or {},
			series_by_name=series,
			product_by_webflow_id=by_id,
			product_series=product_series,
			product_names=product_names,
		)
		report.extend(lines)
		if mapped is None:
			continue
		if frappe.db.exists(GALLERY, {"slug": slug}):
			report.append(f"{slug}: exists, skipped")
			continue
		if not commit:
			would_create.append(slug)
			continue
		try:
			_create(mapped, brand, report)
			frappe.db.commit()
			created.append(slug)
		except Exception as error:
			frappe.db.rollback()
			report.append(f"{slug}: import failed, nothing saved ({error})")
	path = _write_report(brand, commit, report)
	return {
		"committed": 1 if commit else 0,
		"brand": brand,
		"created": created,
		"would_create": would_create,
		"report": report,
		"report_file": path,
	}


def _write_report(brand: str, commit: bool, report: list[str]) -> str:
	name = f"gallery_import_{brand}_{'commit' if commit else 'dry_run'}_{frappe.generate_hash(length=8)}.txt"
	path = frappe.get_site_path("private", "files", name)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w") as handle:
		handle.write("\n".join(report) or "No issues.")
	return path
