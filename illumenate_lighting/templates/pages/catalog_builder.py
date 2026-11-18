"""Catalog Builder: the YAML builder for catalog staff, on this site."""

from pathlib import Path

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.web_guard import require_login

no_cache = 1
ASSETS = "/assets/illumenate_lighting/catalog_builder/catalog-builder"
BUNDLE = Path(__file__).resolve().parents[2] / "public/catalog_builder/catalog-builder.js"


def get_context(context):
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	require_login()
	if not allowed("catalog"):
		frappe.throw(_("Catalog staff access is required"), frappe.PermissionError)
	version = int(BUNDLE.stat().st_mtime) if BUNDLE.exists() else 0
	# ?embed=1: shown inside the Command Center's Catalog tab, which supplies the page title.
	embedded = str(frappe.form_dict.get("embed") or "").strip().lower() in ("1", "true", "yes")
	mount_options = {
		"csrfToken": frappe.sessions.get_csrf_token(),
		"referenceUrl": "/api/method/illumenate_lighting.illumenate_lighting.api.catalog_builder.reference",
		"user": frappe.session.user,
	}
	if embedded:
		mount_options["embedded"] = True
	context.update(
		{
			"title": "Catalog Builder",
			"no_cache": 1,
			"assets": ASSETS,
			"asset_version": version,
			"embedded": embedded,
			"mount_options": mount_options,
		}
	)
	return context
