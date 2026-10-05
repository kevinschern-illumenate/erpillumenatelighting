"""Catalog Builder: the YAML builder for catalog staff, on this site."""

from pathlib import Path

import frappe
from frappe import _

no_cache = 1
ASSETS = "/assets/illumenate_lighting/catalog_builder/catalog-builder"
BUNDLE = Path(__file__).resolve().parents[2] / "public/catalog_builder/catalog-builder.js"


def get_context(context):
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/catalog-builder"
		raise frappe.Redirect
	if not allowed("catalog"):
		frappe.throw(_("Catalog staff access is required"), frappe.PermissionError)
	version = int(BUNDLE.stat().st_mtime) if BUNDLE.exists() else 0
	context.update(
		{
			"title": "Catalog Builder",
			"no_cache": 1,
			"assets": ASSETS,
			"asset_version": version,
			"mount_options": {
				"csrfToken": frappe.sessions.get_csrf_token(),
				"referenceUrl": "/api/method/illumenate_lighting.illumenate_lighting.api.catalog_builder.reference",
				"user": frappe.session.user,
			},
		}
	)
	return context
