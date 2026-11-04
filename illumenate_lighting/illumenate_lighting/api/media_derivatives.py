"""WebP derivatives for staff product images (hardening plan 5.8).

``on_file_insert`` (File ``after_insert``) only enqueues. ``process_file`` runs in the
worker: it records width/height, removes EXIF GPS from the original and writes 480/1200/2400
px WebP copies (never upscaled) as unattached File docs named ``<stem>.ill-w<width>.webp``.
The metadata lives in ``ilL-Image-Derivative``; File itself is unchanged apart from the
GPS-free bytes. Webflow payloads reference derivatives only behind
``ill_webflow_image_derivatives`` (default off).
"""

import hashlib
import io
import json
import os
from pathlib import PurePosixPath

import frappe

from illumenate_lighting.illumenate_lighting.api.product_projection import HERO_LINKS, PRODUCT_DOCTYPE
from illumenate_lighting.illumenate_lighting.portal import site_flags
from illumenate_lighting.illumenate_lighting.portal.file_validation import stored_bytes, validate_content

DOCTYPE = "ilL-Image-Derivative"
RECIPE = "webp-v1"
WIDTHS = (480, 1200, 2400)
WEBP_QUALITY = 82
GPS_IFD = 0x8825
EXTENSIONS = (".jpg", ".jpeg", ".png")
# Gallery rows are child rows, so their uploads attach to the parent with the row's field name.
WATCHED_FIELDS = {
	PRODUCT_DOCTYPE: frozenset(
		("featured_image", "dimensions_image", "custom_dimensions_image_2", "series_family_image", "image")
	),
	**{doctype: frozenset(("hero_image", "image")) for _, doctype in HERO_LINKS},
}
# Product fields whose derivatives the flag-gated Webflow payload lists, gallery rows aside.
PAYLOAD_FIELDS = ("featured_image", "hero_image", "dimensions_image", "custom_dimensions_image_2", "series_family_image")


def is_relevant(doc):
	"""An uploaded JPEG/PNG in a gallery or featured field of a product or template."""
	fields = WATCHED_FIELDS.get(doc.get("attached_to_doctype"))
	if not fields or doc.get("attached_to_field") not in fields:
		return False
	name = doc.get("attached_to_name") or ""
	if not name or name.startswith("new-"):
		return False
	url = doc.get("file_url") or ""
	return url.startswith(("/files/", "/private/files/")) and PurePosixPath(url).suffix.lower() in EXTENSIONS


def idempotency_key(doc):
	"""Same bytes and visibility → the same job and record, however often they are attached."""
	identity = doc.get("content_hash") or doc.get("file_url")
	return f"ill-img-deriv:{identity}:{int(bool(doc.get('is_private')))}:{RECIPE}"


def on_file_insert(doc, method=None):
	"""File ``after_insert``: enqueue after commit, never process inline or block the upload."""
	try:
		if not site_flags.media_derivatives_enabled() or not is_relevant(doc):
			return
		key = idempotency_key(doc)
		frappe.enqueue(
			f"{__name__}.process_file",
			queue="long",
			job_id=key,
			deduplicate=True,
			enqueue_after_commit=True,
			file_name=doc.name,
			key=key,
		)
	except Exception:
		frappe.log_error(title="Image derivative enqueue failed", message=frappe.get_traceback())


def _pillow():
	try:
		from PIL import Image, ImageOps
	except ImportError:
		return None, None
	return Image, ImageOps


def make_derivatives(content, Image, ImageOps, widths=WIDTHS):
	"""Pure transform: dimensions, WebP copies (no EXIF) and the original without GPS.

	Callers validate the bytes first (size and pixel caps). ``stripped`` is None when the original has no GPS block and must stay byte-identical."""
	with Image.open(io.BytesIO(content)) as opened:
		source_format = opened.format
		exif = opened.getexif()
		has_gps = GPS_IFD in exif
		image = ImageOps.exif_transpose(opened) or opened
		width, height = image.size
		if image.mode not in ("RGB", "RGBA"):
			alpha = "A" in image.mode or "transparency" in image.info
			image = image.convert("RGBA" if alpha else "RGB")
		derivatives = []
		for target in sorted(set(widths)):
			if target > width:
				continue
			resized = image
			if target != width:
				resized = image.resize((target, max(1, round(height * target / width))), Image.LANCZOS)
			buffer = io.BytesIO()
			resized.save(buffer, "WEBP", quality=WEBP_QUALITY, method=6)
			derivatives.append({"width": target, "height": resized.size[1], "content": buffer.getvalue()})
		stripped = None
		if has_gps:
			del exif[GPS_IFD]
			options = {"exif": exif.tobytes()}
			if opened.info.get("icc_profile"):
				options["icc_profile"] = opened.info["icc_profile"]
			if source_format == "JPEG":
				options.update(quality="keep", subsampling="keep")
			buffer = io.BytesIO()
			opened.save(buffer, source_format, **options)
			stripped = buffer.getvalue()
	return {"width": width, "height": height, "derivatives": derivatives, "stripped": stripped}


def derivative_name(file_name, width):
	return f"{PurePosixPath(file_name).stem}.ill-w{width}.webp"


def _record(key, file):
	name = frappe.db.get_value(DOCTYPE, {"idempotency_key": key})
	if name:
		return frappe.get_doc(DOCTYPE, name)
	return frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"idempotency_key": key,
			"source_file": file.name,
			"source_url": file.file_url,
			"content_hash": file.get("content_hash"),
			"recipe": RECIPE,
			"status": "Queued",
		}
	).insert(ignore_permissions=True)


def _finish(record, status, **values):
	record.update({"status": status, "processed_at": frappe.utils.now_datetime(), **values})
	record.save(ignore_permissions=True)
	return status


def _replace_original(file, content):
	"""Atomically swap in the GPS-free bytes and keep every File row of that URL in step."""
	path = file.get_full_path()
	temporary = f"{path}.ill-gps-tmp"
	with open(temporary, "wb") as handle:
		handle.write(content)
	os.replace(temporary, path)
	for name in frappe.get_all("File", filters={"file_url": file.file_url}, pluck="name"):
		frappe.db.set_value(
			"File",
			name,
			{"content_hash": hashlib.md5(content).hexdigest(), "file_size": len(content)},
			update_modified=False,
		)


def _save_derivatives(file, derivatives):
	created = []
	try:
		for item in derivatives:
			doc = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": derivative_name(file.file_name or file.file_url, item["width"]),
					"content": item["content"],
					"is_private": file.is_private,
					"folder": file.get("folder") or "Home",
				}
			).insert(ignore_permissions=True)
			created.append(doc)
	except Exception:
		for doc in created:
			frappe.delete_doc("File", doc.name, ignore_permissions=True, force=True)
		raise
	return [
		{"width": item["width"], "height": item["height"], "file": doc.name, "url": doc.file_url}
		for item, doc in zip(derivatives, created, strict=True)
	]


def process_file(file_name, key=None):
	"""Worker job. Idempotent: a Done record for the key is never redone."""
	if not frappe.db.exists("File", file_name):
		return "Missing"
	file = frappe.get_doc("File", file_name)
	key = key or idempotency_key(file)
	record = _record(key, file)
	if record.status == "Done":
		return "Done"
	Image, ImageOps = _pillow()
	if Image is None:
		return _finish(record, "Skipped", error="Pillow is not installed on this site")
	try:
		content = stored_bytes(file)
		validate_content(file.file_name or PurePosixPath(file.file_url).name, content)
		result = make_derivatives(content, Image, ImageOps)
		if result["stripped"] is not None:
			_replace_original(file, result["stripped"])
		saved = _save_derivatives(file, result["derivatives"])
		return _finish(
			record,
			"Done",
			width=result["width"],
			height=result["height"],
			gps_removed=int(result["stripped"] is not None),
			derivatives=json.dumps(saved),
			error=None,
		)
	except Exception as exc:
		frappe.log_error(title="Image derivatives failed", message=frappe.get_traceback())
		return _finish(record, "Error", error=str(exc)[:500])


def derivative_map(urls):
	"""{source_url: {"width", "height", "derivatives": [...]}} for finished records, one query."""
	urls = sorted({url for url in urls if url})
	if not urls:
		return {}
	found = {}
	for row in frappe.get_all(
		DOCTYPE,
		filters={"source_url": ["in", urls], "status": "Done"},
		fields=["source_url", "width", "height", "derivatives"],
		order_by="modified desc",
	):
		if row.source_url in found:
			continue
		try:
			derivatives = json.loads(row.derivatives or "[]")
		except (TypeError, ValueError):
			derivatives = []
		found[row.source_url] = {
			"width": row.width,
			"height": row.height,
			"derivatives": [{"width": d["width"], "height": d["height"], "url": d["url"]} for d in derivatives],
		}
	return found
