# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Frappe-side glue for spec sheets: site branding, File-backed artwork, Chromium setup."""

import hashlib

import frappe

from illumenate_lighting.illumenate_lighting.api.spec_sheets.brands import (
	BRANDS_DIR,
	apply_site_overrides,
	load_brand,
)
from illumenate_lighting.illumenate_lighting.api.spec_sheets.svg import (
	FILE_URL_PREFIXES,
	FileURLAssets,
	has_fpo,
	image_mime,
)

CHROMIUM_JOB_ID = "ill_spec_sheet_install_chromium"


def _file_content(url):
	"""Raw bytes of the File at ``url``.

	Not ``File.get_content``: it decodes anything that decodes (SVG, and PNGs that happen
	to be valid Windows-1252) to ``str``.
	"""
	name = frappe.db.get_value("File", {"file_url": url}, "name")
	if not name:
		raise ValueError(f"No File record for {url!r}")
	with open(frappe.get_doc("File", name).get_full_path(), "rb") as handle:
		return handle.read()


def file_assets():
	"""Artwork stored as Frappe Files (spec asset rows, uploaded logos)."""
	return FileURLAssets(_file_content)


def stamp_spec_assets(doc, method=None):
	"""``validate`` on every DocType with a ``spec_assets`` table.

	Keeps each row's SHA-256 in step with its file and marks SVG artwork that still
	uses the FPO magenta swatch as a placeholder, so no revision can be approved with it.
	"""
	before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
	previous = {row.name: row.file for row in ((before.get("spec_assets") if before else None) or [])}
	for row in doc.get("spec_assets") or []:
		if not row.file:
			continue
		if row.sha256 and row.name in previous and previous[row.name] == row.file:
			continue
		if not row.file.startswith(FILE_URL_PREFIXES):
			frappe.throw(
				frappe._("Spec asset row {0}: upload the file to ERPNext instead of linking {1}").format(
					row.idx, row.file
				)
			)
		try:
			image_mime(row.file)
			content = _file_content(row.file)
		except ValueError as error:
			frappe.throw(frappe._("Spec asset row {0}: {1}").format(row.idx, error))
		row.sha256 = hashlib.sha256(content).hexdigest()
		if row.file.lower().endswith(".svg") and has_fpo(content) and not row.is_placeholder:
			row.is_placeholder = 1
			row.placeholder_note = row.placeholder_note or "Contains FPO magenta artwork"


def validate_document_branding(doc, method=None):
	"""``validate`` on ilL-Webflow-Brand: reject branding the spec sheet renderer would refuse."""
	code = doc.get("brand_code")
	base = load_brand(code if code and (BRANDS_DIR / code / "brand.json").is_file() else "illumenate")
	try:
		apply_site_overrides(base, doc.as_dict())
		for row in doc.get("document_logos") or []:
			if row.logo and not row.logo.startswith(FILE_URL_PREFIXES):
				raise ValueError(f"Logo for {row.spec_line} must be an uploaded file, not {row.logo}")
			if row.logo:
				image_mime(row.logo)
	except ValueError as error:
		frappe.throw(frappe._("Document Branding: {0}").format(error))


def site_brand(brand_code="illumenate"):
	"""App branding for ``brand_code`` with the site's ilL-Webflow-Brand overrides applied."""
	brand = load_brand(brand_code)
	name = frappe.db.get_value("ilL-Webflow-Brand", {"brand_code": brand_code}, "name")
	if name:
		record = frappe.get_doc("ilL-Webflow-Brand", name).as_dict()
		apply_site_overrides(brand, record)
	brand["file_assets"] = file_assets()
	return brand


def after_migrate():
	"""Queue the pinned Chromium install so no spec sheet request waits for the download.

	The bench's files are rebuilt on each deploy, so this runs after every migrate.
	It never raises and never downloads inline: when Redis is unreachable Frappe would
	run an enqueued job synchronously inside the migration, so the install is skipped
	instead (the render probe or the next migrate installs it).
	"""
	if frappe.in_test or _chromium_available():
		return
	if not _queue_reachable():
		print("Spec sheets: Redis queue unreachable; skipping the Chromium install job")
		return
	try:
		frappe.enqueue(
			"illumenate_lighting.illumenate_lighting.api.spec_sheets.site.install_chromium",
			queue="long",
			timeout=1800,
			job_id=CHROMIUM_JOB_ID,
			deduplicate=True,
		)
	except Exception:
		frappe.log_error(title="Spec sheet Chromium install could not be queued")


def _chromium_available():
	from illumenate_lighting.illumenate_lighting.api.spec_sheets.render import RenderError, find_chromium

	try:
		find_chromium(download=False)
	except RenderError:
		return False
	return True


def _queue_reachable():
	from frappe.utils.background_jobs import get_redis_conn

	try:
		return bool(get_redis_conn().ping())
	except Exception:
		return False


def install_chromium():
	from illumenate_lighting.illumenate_lighting.api.spec_sheets.render import find_chromium

	try:
		find_chromium(download=True)
	except Exception:
		frappe.log_error(title="Spec sheet Chromium install failed")
		raise
