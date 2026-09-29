# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Frappe-side glue for spec sheets: site branding, File-backed artwork, Chromium setup."""

import frappe

from illumenate_lighting.illumenate_lighting.api.spec_sheets.brands import apply_site_overrides, load_brand
from illumenate_lighting.illumenate_lighting.api.spec_sheets.svg import FileURLAssets

CHROMIUM_JOB_ID = "ill_spec_sheet_install_chromium"


def _file_content(url):
	name = frappe.db.get_value("File", {"file_url": url}, "name")
	if not name:
		raise ValueError(f"No File record for {url!r}")
	return frappe.get_doc("File", name).get_content()


def file_assets():
	"""Artwork stored as Frappe Files (spec asset rows, uploaded logos)."""
	return FileURLAssets(_file_content)


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
