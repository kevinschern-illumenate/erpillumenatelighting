"""Stable spec sheet links (plan 4.7, Phase 4, D6, D19, D24).

Every template has one public link that never changes, for its own brand (owner, 2026-11-03):
``https://<site>/spec-sheets/<brand>_<template record name, lowercase>.pdf``, for example
``/spec-sheets/illumenate-lighting_kit-ra01.pdf`` or ``/spec-sheets/206-lighting_kit-ra01.pdf``. It is a redirect, not a file: nothing is stored at
``/spec-sheets/``. The link answers with a temporary redirect (302, ``Cache-Control:
no-store``) to the file the template's Spec Sheet field points at, so a new spec sheet is
served as soon as it is registered, and the old one keeps being served until then.

- Lookup is case-insensitive across the six template doctypes. No match, or more than one,
  is a 404 (and is logged). ``template_link.validate_unique_name`` keeps names unique.
- The ``.pdf`` suffix is optional: ``/spec-sheets/kit-ra01`` works too.
- The brand part must be the template's own brand (its enabled Target Brand), else 404. A
  link without the brand part (``/spec-sheets/kit-ra01.pdf``) also works.
- After a successful run, ``detach_older`` unattaches the template's older spec sheet files
  (owner, 2026-11-03: only the current one stays attached; the files stay in File Manager).
  Nothing changes after a failed run.

Served by ``SpecSheetRedirect`` (hooks ``page_renderer``), which Frappe asks before its own
page and static-file handling.
"""

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_schema import TEMPLATE_DOCTYPES

PREFIX = "spec-sheets/"
SUFFIX = ".pdf"


def key_from_path(path):
	"""Pure: the template key in a request path, or None when the path is not a spec link."""
	path = (path or "").strip("/")
	if not path.lower().startswith(PREFIX):
		return None
	key = path[len(PREFIX) :]
	if key.lower().endswith(SUFFIX):
		key = key[: -len(SUFFIX)]
	return key if key and "/" not in key else None


# Brand names in file names and links (owner, 2026-11-03); other brands use their Brand Label.
BRAND_NAMES = {"illumenate": "ilLumenate Lighting", "lighting_206": "206 Lighting"}


def brand_name(brand):
	if brand in BRAND_NAMES:
		return BRAND_NAMES[brand]
	label = frappe.db.get_value("ilL-Webflow-Brand", {"brand_code": brand}, "brand_label") if brand else None
	return label or brand or ""


def brand_slug(name):
	"""Pure: "ilLumenate Lighting" -> "illumenate-lighting"."""
	import re

	return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def public_url(template_name, brand):
	from frappe.utils import get_url

	return f"{get_url()}/{PREFIX}{brand_slug(brand_name(brand))}_{template_name.lower()}{SUFFIX}"


def template_brand(doctype, name):
	rows = frappe.get_all(
		"ilL-Child-Webflow-Brand-Target",
		filters={"parenttype": doctype, "parent": name, "enabled": 1},
		pluck="brand",
	)
	return rows[0] if rows else None


def split_key(key):
	"""Pure: ("illumenate-lighting", "kit-ra01") for "illumenate-lighting_kit-ra01";
	(None, key) when there is no brand part."""
	if "_" in key:
		prefix, rest = key.split("_", 1)
		if prefix and rest and prefix == brand_slug(prefix):
			return prefix, rest
	return None, key


def find_template(key):
	"""(doctype, name) of the one template whose record name matches ``key`` in any case."""
	matches = []
	for doctype in TEMPLATE_DOCTYPES:
		rows = frappe.db.sql(f"select name from `tab{doctype}` where lower(name) = lower(%s)", (key,))
		matches += [(doctype, row[0]) for row in rows]
	if len(matches) != 1:
		if matches:
			frappe.log_error(
				title="Spec sheet link matches more than one template",
				message=f"{key}: {matches}",
			)
		return None
	return matches[0]


def current_file(key):
	"""The file URL the link redirects to, or None (404)."""
	prefix, template_key = split_key(key)
	found = find_template(template_key)
	if not found and prefix:
		# A record name that itself contains an underscore.
		prefix, found = None, find_template(key)
	if not found:
		return None
	if prefix and brand_slug(brand_name(template_brand(*found))) != prefix:
		return None
	return frappe.db.get_value(*found, "spec_sheet") or None


def detach_older(template_doctype, template_id):
	"""Unattach the template's spec sheet files other than the current one (owner, 2026-11-03).

	The files stay in File Manager; they are only no longer listed on the template. Returns the
	file URLs that were unattached.
	"""
	current = frappe.db.get_value(template_doctype, template_id, "spec_sheet")
	files = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": template_doctype,
			"attached_to_name": template_id,
			"attached_to_field": "spec_sheet",
		},
		fields=["name", "file_url"],
	)
	older = files_to_detach(files, current)
	for row in older:
		frappe.db.set_value(
			"File",
			row.name,
			{"attached_to_doctype": None, "attached_to_name": None, "attached_to_field": None},
			update_modified=False,
		)
	return [row.file_url for row in older]


PRODUCT = "ilL-Webflow-Product"


def attach_to_product(template, file_url):
	"""Attach the current spec sheet to the linked Webflow Product too (owner, 2026-11-03).

	A second File record for the same file (Frappe stores the file once), attached to the
	product. The product's earlier spec sheet attachments are unattached, so only the current
	one is listed there as well; they stay in File Manager. Returns the File name or None.
	"""
	product = template.get("webflow_product")
	if not product or not frappe.db.exists(PRODUCT, product):
		return None
	attached = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": PRODUCT,
			"attached_to_name": product,
			"file_url": ["like", "%_Spec Sheet%"],
		},
		fields=["name", "file_url"],
	)
	for row in files_to_detach(attached, file_url):
		frappe.db.set_value(
			"File",
			row.name,
			{"attached_to_doctype": None, "attached_to_name": None, "attached_to_field": None},
			update_modified=False,
		)
	existing = next((row.name for row in attached if row.file_url == file_url), None)
	if existing:
		return existing
	source = (
		frappe.db.get_value("File", {"file_url": file_url}, ["file_name", "is_private"], as_dict=True) or {}
	)
	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_url": file_url,
			"file_name": source.get("file_name"),
			"is_private": source.get("is_private") or 0,
			"attached_to_doctype": PRODUCT,
			"attached_to_name": product,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def files_to_detach(files, current):
	"""Pure: every file except the one the template points at."""
	return [row for row in files if row.get("file_url") != current]


def absolute_location(url):
	"""Absolute, percent-encoded redirect target (file names have spaces and brackets)."""
	from urllib.parse import quote

	if url.startswith("/"):
		from frappe.utils import get_url

		url = get_url() + url
	return quote(url, safe=":/?#&=%@+,;~")


try:
	from frappe.website.page_renderers.base_renderer import BaseRenderer
except ImportError:  # outside a Frappe bench (unit tests)
	BaseRenderer = object


class SpecSheetRedirect(BaseRenderer):
	"""``/spec-sheets/<template>.pdf``: 302 to the template's current spec sheet, else 404."""

	def __init__(self, path=None, http_status_code=None):
		self.path = path
		self.http_status_code = http_status_code

	def can_render(self):
		return key_from_path(self.path) is not None

	def render(self):
		from werkzeug.wrappers import Response

		url = current_file(key_from_path(self.path))
		if not url:
			response = Response("Spec sheet not found.", status=404, mimetype="text/plain")
		else:
			response = Response(status=302)
			response.headers["Location"] = absolute_location(url)
		response.headers["Cache-Control"] = "no-store"
		return response
