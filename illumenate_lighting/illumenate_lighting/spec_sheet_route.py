"""Stable spec sheet links (plan 4.7, Phase 4, D6, D19, D24).

Every template has one public link that never changes:
``https://<site>/spec-sheets/<template record name, lowercase>.pdf`` (for example
``/spec-sheets/kit-ra01.pdf``). It is a redirect, not a file: nothing is stored at
``/spec-sheets/``. The link answers with a temporary redirect (302, ``Cache-Control:
no-store``) to the file the template's Spec Sheet field points at, so a new spec sheet is
served as soon as it is registered, and the old one keeps being served until then.

- Lookup is case-insensitive across the six template doctypes. No match, or more than one,
  is a 404 (and is logged). ``template_link.validate_unique_name`` keeps names unique.
- The ``.pdf`` suffix is optional: ``/spec-sheets/kit-ra01`` works too.
- After a successful run, ``prune`` keeps the newest ``KEEP`` spec sheet files attached to
  the template and deletes older ones through their File documents. The file the template
  points at is never deleted, and nothing is pruned after a failed run.

Served by ``SpecSheetRedirect`` (hooks ``page_renderer``), which Frappe asks before its own
page and static-file handling.
"""

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_schema import TEMPLATE_DOCTYPES

PREFIX = "spec-sheets/"
SUFFIX = ".pdf"
KEEP = 2


def key_from_path(path):
	"""Pure: the template key in a request path, or None when the path is not a spec link."""
	path = (path or "").strip("/")
	if not path.lower().startswith(PREFIX):
		return None
	key = path[len(PREFIX) :]
	if key.lower().endswith(SUFFIX):
		key = key[: -len(SUFFIX)]
	return key if key and "/" not in key else None


def public_url(template_name):
	from frappe.utils import get_url

	return f"{get_url()}/{PREFIX}{template_name.lower()}{SUFFIX}"


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
	found = find_template(key)
	if not found:
		return None
	return frappe.db.get_value(*found, "spec_sheet") or None


def prune(template_doctype, template_id, keep=KEEP):
	"""Delete older spec sheet files of a template, keeping the newest ``keep`` and the current one.

	Only files attached to the template's Spec Sheet field are considered. Returns the deleted
	file URLs. Deleting goes through the File document, so a physical file another File
	still uses is kept.
	"""
	current = frappe.db.get_value(template_doctype, template_id, "spec_sheet")
	files = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": template_doctype,
			"attached_to_name": template_id,
			"attached_to_field": "spec_sheet",
		},
		fields=["name", "file_url", "creation"],
		order_by="creation desc",
	)
	deleted = []
	for row in files_to_prune(files, current, keep):
		frappe.delete_doc("File", row.name, ignore_permissions=True, force=True)
		deleted.append(row.file_url)
	return deleted


def files_to_prune(files, current, keep=KEEP):
	"""Pure: from files newest first, those beyond the newest ``keep``, never ``current``."""
	return [row for row in files[keep:] if row.get("file_url") != current]


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
