# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Guest handling shared by authenticated portal page controllers.

A guest who opens a portal link (usually from a notification email) is sent to
``/login`` with the full path and query string in ``redirect-to``, so signing
in lands them on the page they asked for rather than the portal home.
"""

from urllib.parse import quote

import frappe


def current_path() -> str:
	"""The requested path plus query string, relative to the site."""
	request = getattr(frappe.local, "request", None) or getattr(frappe, "request", None)
	if request is None:
		return "/" + (getattr(frappe.local, "path", "") or "").lstrip("/")
	path = request.path or "/"
	query = request.query_string or b""
	if isinstance(query, bytes):
		query = query.decode("utf-8", "replace")
	return path + ("?" + query if query else "")


def login_url(path: str | None = None) -> str:
	# Slashes stay readable; "?", "&" and "=" of the page's own query are encoded.
	return "/login?redirect-to=" + quote(path or current_path(), safe="/")


def require_login() -> None:
	"""Redirect a guest to login and back to this page; no-op when signed in."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = login_url()
		raise frappe.Redirect
