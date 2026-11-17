"""Bulk media manifest for Catalog Builder Check → Import (plan 5.7).

A manifest row names a product, an image role and a file, for example
``product_slug=sl01, role=gallery, file_url_or_zip_path=/files/sl01-side.jpg``.
``plan()`` validates every row without writing anything (the dry run). ``apply()``
then attaches the files and fills the product fields and gallery.

Files are never fetched from other hosts. A file is an existing ``File`` document
(by name or ``file_url``), a ``/files/`` or ``/private/files/`` path on this site, or a
path inside an uploaded ZIP (``media_zip``). Every file passes
``portal.file_validation.validate_content`` (20 MiB, pixel cap, type sniffing).

Existing images are never replaced silently (owner decision D1): a row that would
change a hero, featured, dimensions or series image that is already set is skipped
and reported, unless the row says ``replace=1``. Gallery rows only ever add images.
"""

import csv
import hashlib
import io
import json
import os
import re
import zipfile
from pathlib import PurePosixPath
from urllib.parse import unquote

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import parse_bool
from illumenate_lighting.illumenate_lighting.api.product_projection import (
	GALLERY_DOCTYPE,
	HERO_LINKS,
	PRODUCT_DOCTYPE,
)
from illumenate_lighting.illumenate_lighting.portal.file_validation import (
	MAX_FILE_BYTES,
	stored_bytes,
	validate_content,
)

MAX_MEDIA_ROWS = 200
MAX_ZIP_BYTES = 512 * 1024 * 1024
MAX_ZIP_ENTRIES = 2000
MAX_COMPRESSION_RATIO = 200
MAX_ALT_TEXT = 140
COLUMNS = (
	"product_slug",
	"role",
	"file_url_or_zip_path",
	"alt_text",
	"display_order",
	"is_primary",
	"replace",
)
REQUIRED = ("product_slug", "role", "file_url_or_zip_path")
# Single-image roles: (target, field). "hero" lives on the source template (D1).
FIELD_ROLES = {
	"hero": ("template", "hero_image"),
	"featured": ("product", "featured_image"),
	"dimensions": ("product", "dimensions_image"),
	"series_family": ("product", "series_family_image"),
}
ROLES = (*FIELD_ROLES, "gallery")
FIELD_LABELS = {
	"hero_image": "hero image",
	"featured_image": "featured image",
	"dimensions_image": "dimensions image",
	"series_family_image": "series family image",
}
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


class ManifestError(ValueError):
	"""A manifest that cannot be read at all; the whole run is refused."""


def parse_manifest(media):
	"""Normalise a manifest (rows, a JSON list or CSV text with a header) into a list of dicts.

	Returns ``[]`` for an empty manifest. Raises ``ManifestError`` for an unreadable shape;
	per-row problems are reported later by ``plan()``.
	"""
	if media is None:
		return []
	if isinstance(media, str):
		text = media.strip().lstrip("\ufeff")
		if not text:
			return []
		if text.startswith("["):
			try:
				media = json.loads(text)
			except ValueError as error:
				raise ManifestError("The media manifest is not valid JSON") from error
		else:
			media = _csv_rows(text)
	if not isinstance(media, list) or any(not isinstance(row, dict) for row in media):
		raise ManifestError("The media manifest must be CSV text or a list of rows")
	if len(media) > MAX_MEDIA_ROWS:
		raise ManifestError(f"Split the media manifest: {len(media)} rows, limit {MAX_MEDIA_ROWS}")
	rows = []
	for index, raw in enumerate(media, 1):
		row = {}
		for key, value in raw.items():
			key = str(key or "").strip().lower()
			if not key:
				continue
			if key not in COLUMNS:
				raise ManifestError(f"Unknown media manifest column: {key}")
			if value is not None and not isinstance(value, (str, int, float, bool)):
				raise ManifestError(f"Media row {index}: {key} must be text")
			row[key] = "" if value is None else str(value).strip() if not isinstance(value, bool) else value
		rows.append(row)
	return rows


def _csv_rows(text):
	reader = csv.DictReader(io.StringIO(text))
	header = [str(name or "").strip().lower() for name in reader.fieldnames or ()]
	missing = [column for column in REQUIRED if column not in header]
	if missing:
		raise ManifestError("The media manifest CSV needs the columns " + ", ".join(REQUIRED))
	rows = []
	for row in reader:
		if None in row:
			raise ManifestError(f"Media CSV line {reader.line_num} has more cells than the header")
		if any(str(value or "").strip() for value in row.values()):
			rows.append(row)
		if len(rows) > MAX_MEDIA_ROWS:
			raise ManifestError(f"Split the media manifest: more than {MAX_MEDIA_ROWS} rows")
	return rows


def manifest_hash(rows, zip_identity=None):
	"""Hash of the normalised manifest and the ZIP's content, for the Check → Import gate."""
	text = json.dumps(
		{"media": rows, "zip": zip_identity}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
	)
	return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------
# Sources


def classify_source(value):
	"""Return ``(kind, key)``: kind is ``url``, ``file`` (File name) or ``zip``.

	Raises ``ValueError`` for remote URLs and any path outside this site's file folders.
	"""
	value = (value or "").strip()
	if not value:
		raise ValueError("file_url_or_zip_path is required")
	if "://" in value or value.startswith("//") or _SCHEME.match(value):
		raise ValueError(
			"Remote URLs are not fetched. Upload the image to ERPNext or add it to the ZIP, then use its path."
		)
	if "\\" in value or "?" in value or "#" in value or any(ord(char) < 32 for char in value):
		raise ValueError("Use a plain file path without query strings")
	decoded = unquote(value)
	if any(part in ("..", ".") for part in decoded.split("/")):
		raise ValueError("File paths cannot contain . or .. segments")
	if value.startswith(("/files/", "/private/files/")):
		return "url", value
	if value.startswith("/"):
		raise ValueError("Only /files/ and /private/files/ paths on this site are accepted")
	if "/" not in value and "." not in value:
		return "file", value
	return "zip", value


class ZipSource:
	"""Bounded reader for an uploaded ZIP File document. Only read when a row names an entry."""

	def __init__(self, reference):
		self.reference = (reference or "").strip()
		self._file = None
		self._archive = None

	def file_doc(self):
		if self._file is None:
			name = self.reference
			if name.startswith(("/files/", "/private/files/")):
				name = frappe.db.get_value("File", {"file_url": name}, "name")
			if not name or not frappe.db.exists("File", name):
				raise ManifestError("The media ZIP must be a file uploaded to ERPNext")
			doc = frappe.get_doc("File", name)
			if not frappe.has_permission("File", "read", doc=doc):
				raise ManifestError("You cannot read the media ZIP")
			if not (doc.get("file_name") or doc.get("file_url") or "").lower().endswith(".zip"):
				raise ManifestError("The media ZIP must be a .zip file")
			if frappe.utils.cint(doc.get("file_size")) > MAX_ZIP_BYTES:
				raise ManifestError("The media ZIP is larger than 512 MiB")
			self._file = doc
		return self._file

	def identity(self):
		doc = self.file_doc()
		return {"file": doc.name, "content_hash": doc.get("content_hash") or doc.get("file_url")}

	def archive(self):
		if self._archive is None:
			try:
				archive = zipfile.ZipFile(self.file_doc().get_full_path())
			except (OSError, zipfile.BadZipFile) as error:
				raise ManifestError("The media ZIP cannot be opened") from error
			if len(archive.infolist()) > MAX_ZIP_ENTRIES:
				raise ManifestError(f"The media ZIP has more than {MAX_ZIP_ENTRIES} entries")
			self._archive = archive
		return self._archive

	def read(self, path):
		try:
			info = self.archive().getinfo(path)
		except KeyError:
			raise ValueError(f"{path} is not in the media ZIP") from None
		if info.is_dir():
			raise ValueError(f"{path} is a folder")
		if info.flag_bits & 0x1:
			raise ValueError("Encrypted ZIP entries are not supported")
		if info.file_size > MAX_FILE_BYTES:
			raise ValueError("File must contain between 1 byte and 20 MiB")
		if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
			raise ValueError(f"{path} is compressed too much to be a normal image")
		with self.archive().open(info) as handle:
			content = handle.read(MAX_FILE_BYTES + 1)
		if len(content) > MAX_FILE_BYTES:
			raise ValueError("File must contain between 1 byte and 20 MiB")
		return content

	def close(self):
		if self._archive is not None:
			self._archive.close()


def _site_file(url):
	"""Bytes of a ``/files/`` or ``/private/files/`` path with no File document."""
	private = url.startswith("/private/files/")
	name = unquote(url.split("/files/", 1)[1])
	if not name or "/" in name:
		raise ValueError("Use a file directly in /files/ or /private/files/")
	folder = os.path.realpath(frappe.get_site_path("private" if private else "public", "files"))
	path = os.path.realpath(os.path.join(folder, name))
	if os.path.dirname(path) != folder or not os.path.isfile(path):
		raise ValueError(f"{url} does not exist on this site")
	if os.path.getsize(path) > MAX_FILE_BYTES:
		raise ValueError("File must contain between 1 byte and 20 MiB")
	with open(path, "rb") as handle:
		return name, handle.read(), private


def _file_doc_bytes(doc):
	if not frappe.has_permission("File", "read", doc=doc):
		raise ValueError(f"You cannot read the file {doc.get('file_url') or doc.name}")
	if frappe.utils.cint(doc.get("file_size")) > MAX_FILE_BYTES:
		raise ValueError("File must contain between 1 byte and 20 MiB")
	filename = doc.get("file_name") or PurePosixPath(doc.get("file_url") or "").name
	return filename, stored_bytes(doc), bool(frappe.utils.cint(doc.get("is_private")))


def load_source(kind, key, zip_source):
	"""Return a dict describing the validated image: url (if reusable), content and filename."""
	doc = None
	if kind == "file":
		if not frappe.db.exists("File", key):
			raise ValueError(f"No File document named {key}")
		doc = frappe.get_doc("File", key)
	elif kind == "url":
		name = frappe.db.get_value("File", {"file_url": key}, "name")
		if name:
			doc = frappe.get_doc("File", name)
	if doc is not None:
		filename, content, private = _file_doc_bytes(doc)
		url = doc.get("file_url")
	elif kind == "url":
		filename, content, private = _site_file(key)
		url = key
	else:
		if zip_source is None:
			raise ValueError("Upload a media ZIP to use ZIP paths, or use a /files/ URL")
		content = zip_source.read(key)
		filename, private, url = PurePosixPath(key).name, True, None
	info = validate_content(filename, content)
	if not str(info.get("mime_type") or "").startswith("image/"):
		raise ValueError("Only JPEG and PNG images can be product images")
	# A public File is linked as is. Anything else becomes a new public File on Import.
	reuse = url if url and not private else None
	predicted = reuse or _existing_public_url(content)
	return {
		"filename": info["filename"],
		"content": None if reuse else content,
		"url": reuse,
		"predicted_url": predicted,
		"private_source": bool(private and url),
	}


def _existing_public_url(content):
	"""The URL Frappe will reuse for identical public content, if any (File dedupes by hash)."""
	digest = hashlib.md5(content, usedforsecurity=False).hexdigest()
	found = frappe.get_all(
		"File",
		filters={"content_hash": digest, "is_private": 0},
		pluck="file_url",
		limit_page_length=1,
	)
	return found[0] if found else None


# --------------------------------------------------------------------------------------
# Plan (dry run)


def _products(slugs):
	fields = [
		"name",
		"product_slug",
		"featured_image",
		"dimensions_image",
		"series_family_image",
		*(field for field, _doctype in HERO_LINKS),
	]
	found = {}
	for row in frappe.get_all(
		PRODUCT_DOCTYPE, filters={"product_slug": ["in", slugs]}, fields=fields, limit_page_length=0
	):
		found[row["product_slug"]] = row
	missing = [slug for slug in slugs if slug not in found]
	if missing:
		for row in frappe.get_all(
			PRODUCT_DOCTYPE, filters={"name": ["in", missing]}, fields=fields, limit_page_length=0
		):
			found.setdefault(row["name"], row)
	return found


def _templates(products):
	wanted = {}
	for product in products.values():
		for field, doctype in HERO_LINKS:
			if product.get(field):
				wanted.setdefault(doctype, set()).add(product[field])
				break
	found = {}
	for doctype, names in wanted.items():
		meta = frappe.get_meta(doctype)
		fields = ["name", "hero_image"] + (["hero_image_alt"] if meta.has_field("hero_image_alt") else [])
		for row in frappe.get_all(
			doctype, filters={"name": ["in", sorted(names)]}, fields=fields, limit_page_length=0
		):
			found[(doctype, row["name"])] = row
	return found


def _template_of(product):
	for field, doctype in HERO_LINKS:
		if product.get(field):
			return doctype, product[field]
	return None


def _gallery(product_names):
	rows = frappe.get_all(
		GALLERY_DOCTYPE,
		filters={"parenttype": PRODUCT_DOCTYPE, "parent": ["in", product_names], "parentfield": "gallery_images"},
		fields=["parent", "image", "display_order"],
		limit_page_length=0,
	)
	galleries = {}
	for row in rows:
		galleries.setdefault(row["parent"], []).append(row)
	return galleries


def _int(value, label):
	if value in (None, ""):
		return None
	try:
		number = int(str(value).strip())
	except ValueError:
		raise ValueError(f"{label} must be a whole number") from None
	if not 0 <= number <= 100_000:
		raise ValueError(f"{label} must be between 0 and 100000")
	return number


def plan(rows, zip_source=None):
	"""Validate every manifest row and work out what Import would do. Writes nothing.

	Each result is ``{"row", "product_slug", "role", "source", "status", "message", "targets",
	"warnings"}`` with status ``ok``, ``skipped`` (D1: it would replace an image) or ``error``.
	The returned list also carries private ``_actions`` used by ``apply()``.
	"""
	slugs = sorted({str(row.get("product_slug") or "").strip() for row in rows} - {""})
	products = _products(slugs) if slugs else {}
	templates = _templates(products)
	galleries = _gallery(sorted({p["name"] for p in products.values()})) if products else {}
	claimed = {}
	writable = {}
	results = []
	for index, row in enumerate(rows, 1):
		slug = str(row.get("product_slug") or "").strip()
		role = str(row.get("role") or "").strip().lower().replace("-", "_").replace(" ", "_")
		source = str(row.get("file_url_or_zip_path") or "").strip()
		result = {
			"row": index,
			"product_slug": slug,
			"role": role,
			"source": source,
			"status": "ok",
			"message": "",
			"targets": [],
			"warnings": [],
			"_actions": [],
		}
		results.append(result)
		try:
			_plan_row(result, row, products, templates, galleries, claimed, writable, zip_source)
		except ManifestError:
			raise
		except ValueError as error:
			result.update(status="error", message=str(error)[:500], _actions=[])
	return results


def _can_write(doctype, name, writable):
	key = (doctype, name)
	if key not in writable:
		writable[key] = bool(frappe.has_permission(doctype, "write", doc=name))
	return writable[key]


def _plan_row(result, row, products, templates, galleries, claimed, writable, zip_source):
	slug, role = result["product_slug"], result["role"]
	if not slug:
		raise ValueError("product_slug is required")
	if role not in ROLES:
		raise ValueError("role must be one of " + ", ".join(ROLES))
	product = products.get(slug)
	if not product:
		raise ValueError(f"No ilL-Webflow-Product with product_slug {slug}")
	alt_text = str(row.get("alt_text") or "").strip()
	if len(alt_text) > MAX_ALT_TEXT:
		raise ValueError(f"alt_text must be at most {MAX_ALT_TEXT} characters")
	order = _int(row.get("display_order"), "display_order")
	is_primary = parse_bool(row.get("is_primary"), default=False)
	replace = parse_bool(row.get("replace"), default=False)

	roles = [role]
	if is_primary and role != "hero":
		roles.append("hero")
	targets = []
	for each in roles:
		if each == "gallery":
			targets.append((PRODUCT_DOCTYPE, product["name"], "gallery_images"))
			continue
		where, field = FIELD_ROLES[each]
		if where == "template":
			template = _template_of(product)
			if not template:
				raise ValueError(f"{slug} has no source template, so it has no hero image to set")
			targets.append((template[0], template[1], field))
		else:
			targets.append((PRODUCT_DOCTYPE, product["name"], field))
	for doctype, name, field in targets:
		if not _can_write(doctype, name, writable):
			raise ValueError(f"You cannot edit {doctype} {name}")
		if field != "gallery_images":
			other = claimed.get((doctype, name, field))
			if other:
				raise ValueError(f"Row {other} already sets the {FIELD_LABELS[field]} of {name}")
	kind, key = classify_source(result["source"])
	image = load_source(kind, key, zip_source)
	if image["private_source"]:
		result["warnings"].append("Private file: Import attaches a public copy, because dealers and Webflow show it.")
	url = image["predicted_url"]

	actions, kept = [], []
	for doctype, name, field in targets:
		if field == "gallery_images":
			gallery = galleries.setdefault(name, [])
			if url and any(entry.get("image") == url for entry in gallery):
				result["warnings"].append(f"Already in the gallery of {name}")
				continue
			if order is None:
				order_value = max([frappe.utils.cint(e.get("display_order")) for e in gallery] or [0]) + 1
			else:
				order_value = order
			gallery.append({"image": url or f"(row {result['row']})", "display_order": order_value})
			actions.append(
				{"doctype": doctype, "name": name, "field": field, "alt_text": alt_text, "display_order": order_value}
			)
			result["targets"].append(f"{doctype} {name}: gallery #{order_value}")
			continue
		current = (
			templates.get((doctype, name)) if doctype != PRODUCT_DOCTYPE else product
		) or {}
		existing = current.get(field)
		label = FIELD_LABELS[field]
		if existing and url and existing == url:
			result["warnings"].append(f"Already the {label} of {name}")
			continue
		if existing and not replace:
			kept.append(f"{name} already has a {label} ({existing}). Add replace=1 to this row to change it.")
			continue
		alt_field = "hero_image_alt" if field == "hero_image" and "hero_image_alt" in current else None
		actions.append(
			{
				"doctype": doctype,
				"name": name,
				"field": field,
				"alt_field": alt_field,
				"alt_text": alt_text,
				"replace": bool(existing),
			}
		)
		claimed[(doctype, name, field)] = result["row"]
		result["targets"].append(f"{doctype} {name}: {label}" + (" (replace)" if existing else ""))
	if kept:
		# D1: never overwrite silently. A row is all-or-nothing, so nothing in it is applied.
		result.update(status="skipped", message=" ".join(kept), targets=[], _actions=[])
		for action in actions:
			claimed.pop((action["doctype"], action["name"], action["field"]), None)
		return
	result["_actions"] = [{**action, "image": image} for action in actions]
	if not actions:
		result["message"] = "Nothing to change"


# --------------------------------------------------------------------------------------
# Apply (Import)


def public_result(result):
	return {key: value for key, value in result.items() if not key.startswith("_")}


def apply(results, created_paths):
	"""Attach the files and fill the fields for planned rows.

	Paths of files newly written to disk are appended to ``created_paths``, so a caller that
	rolls back can delete them with ``remove_new_files``.

	Templates are saved before products, because a template save copies its hero image onto
	the linked product, and a product loaded earlier would then fail its timestamp check.
	Saves use normal permission and validation checks.
	"""
	pending = [result for result in results if result["status"] == "ok" and result["_actions"]]
	urls = {}
	for result in pending:
		for action in result["_actions"]:
			image = action["image"]
			if not image["url"] and id(image) not in urls:
				urls[id(image)], path = _new_public_file(image, action)
				if path:
					created_paths.append(path)
	for products_pass in (False, True):
		docs = {}
		for result in pending:
			for action in result["_actions"]:
				if (action["doctype"] == PRODUCT_DOCTYPE) != products_pass:
					continue
				key = (action["doctype"], action["name"])
				if key not in docs:
					docs[key] = frappe.get_doc(action["doctype"], action["name"])
				doc = docs[key]
				url = action["image"]["url"] or urls[id(action["image"])]
				if action["field"] == "gallery_images":
					doc.append(
						"gallery_images",
						{
							"image": url,
							"alt_text": action["alt_text"] or None,
							"display_order": action["display_order"],
						},
					)
				else:
					doc.set(action["field"], url)
					if action.get("alt_field") and action["alt_text"]:
						doc.set(action["alt_field"], action["alt_text"])
		for doc in docs.values():
			doc.save()
	for result in results:
		if result["status"] == "ok":
			result["status"] = "attached" if result["_actions"] else "unchanged"


def _new_public_file(image, action):
	"""Create a public File for ZIP or private content. Returns its URL and a new disk path."""
	existed = _existing_public_url(image["content"])
	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": image["filename"],
			"content": image["content"],
			"is_private": 0,
			"attached_to_doctype": action["doctype"],
			"attached_to_name": action["name"],
			"attached_to_field": "image" if action["field"] == "gallery_images" else action["field"],
		}
	)
	doc.insert()
	path = None
	if not existed:
		try:
			path = doc.get_full_path()
		except Exception:
			path = None
	return doc.file_url, path


def remove_new_files(paths):
	"""Best effort: delete files written by a rolled-back Import, so no orphan stays on disk."""
	for path in paths or ():
		try:
			os.remove(path)
		except OSError:
			pass


def summary(results):
	return {
		"media_rows": len(results),
		"media_attached": sum(row["status"] == "attached" for row in results),
		"media_checked": sum(row["status"] == "ok" for row in results),
		"media_skipped": sum(row["status"] == "skipped" for row in results),
		"media_errors": sum(row["status"] == "error" for row in results),
	}
