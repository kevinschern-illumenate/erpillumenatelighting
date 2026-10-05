"""Catalog Builder authorization, snapshot delivery, and page boot options."""

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

REPO = Path(__file__).resolve().parents[2]
API = ROOT + ".api.catalog_builder"
PAGE = "illumenate_lighting.templates.pages.catalog_builder"


@contextmanager
def catalog_service(module, user="publisher@example.com", roles=None, enabled=1, user_type="System User"):
	# Exercise the real capability checks using the same Frappe double as the caller.
	with (
		load_service(ROOT + ".portal.staff") as (staff, _),
		load_service(module, {ROOT + ".portal.staff": staff}) as (service, frappe),
		patch.object(staff, "frappe", frappe),
	):
		frappe.session.user = user
		frappe.get_roles.return_value = roles if roles is not None else ["ilL Catalog Publisher"]
		frappe.db.get_value.side_effect = lambda doctype, name, field: {
			"enabled": enabled,
			"user_type": user_type,
		}[field]
		frappe.local.flags = Record()
		frappe.Redirect = type("Redirect", (Exception,), {})
		frappe.sessions = SimpleNamespace(get_csrf_token=MagicMock(return_value="test-csrf"))
		yield service, frappe


class CatalogBuilderReference(unittest.TestCase):
	def test_unauthorized_users_cannot_read_the_snapshot(self):
		for access in (
			{"user": "Guest"},
			{"roles": ["Dealer"]},
			{"roles": []},
			{"roles": ["ilL Engineering"]},
			{"enabled": 0},
			{"user_type": "Website User"},
		):
			with self.subTest(access=access), catalog_service(API, **access) as (service, _):
				with patch.object(service, "SNAPSHOT") as snapshot:
					with self.assertRaises(PermissionError):
						service.reference()
					snapshot.is_file.assert_not_called()
					snapshot.read_text.assert_not_called()

	def test_catalog_staff_and_administrators_get_the_snapshot(self):
		payload = {
			"schema_version": 1,
			"exported_on": "2026-10-04",
			"doctypes": {"ilL-Attribute-Finish": {"source": "export", "records": {"White": {"code": "WH"}}}},
		}
		with tempfile.TemporaryDirectory() as directory:
			snapshot = Path(directory) / "reference.json"
			snapshot.write_text(json.dumps(payload), encoding="utf-8")
			for access in ({}, {"roles": ["System Manager"]}, {"user": "Administrator", "roles": []}):
				with self.subTest(access=access), catalog_service(API, **access) as (service, _):
					self.assertEqual(service.reference.whitelist_options, {"methods": ["GET"]})
					self.assertEqual(service.SNAPSHOT, REPO / "tools/yaml_builder_ui/src/erp-reference.json")
					with patch.object(service, "SNAPSHOT", snapshot):
						self.assertEqual(service.reference(), payload)

	def test_missing_snapshot_reports_unavailable(self):
		with tempfile.TemporaryDirectory() as directory, catalog_service(API) as (service, _):
			with patch.object(service, "SNAPSHOT", Path(directory) / "missing.json"):
				self.assertEqual(
					service.reference(),
					{"schema_version": 1, "exported_on": None, "doctypes": {}, "unavailable": True},
				)


class CatalogBuilderPage(unittest.TestCase):
	def test_guest_redirects_to_login_with_return_path(self):
		with catalog_service(PAGE, user="Guest") as (page, frappe):
			with self.assertRaises(frappe.Redirect):
				page.get_context({})
			self.assertEqual(frappe.local.flags.redirect_location, "/login?redirect-to=/catalog-builder")
			frappe.sessions.get_csrf_token.assert_not_called()

	def test_non_catalog_users_are_refused(self):
		for access in ({"roles": ["Dealer"]}, {"roles": []}, {"enabled": 0}, {"user_type": "Website User"}):
			with self.subTest(access=access), catalog_service(PAGE, **access) as (page, frappe):
				with self.assertRaises(PermissionError):
					page.get_context({})
				frappe.sessions.get_csrf_token.assert_not_called()

	def test_staff_page_has_uncached_boot_options_and_versioned_assets(self):
		for access in ({}, {"roles": ["System Manager"]}, {"user": "Administrator", "roles": []}):
			with self.subTest(access=access), catalog_service(PAGE, **access) as (page, frappe):
				self.assertEqual(
					page.BUNDLE, REPO / "illumenate_lighting/public/catalog_builder/catalog-builder.js"
				)
				with tempfile.TemporaryDirectory() as directory:
					bundle = Path(directory) / "bundle.js"
					bundle.write_text("// test bundle", encoding="utf-8")
					with patch.object(page, "BUNDLE", bundle):
						context = page.get_context({})
						self.assertEqual(context["asset_version"], int(bundle.stat().st_mtime))
				self.assertEqual(page.no_cache, 1)
				self.assertEqual(context["no_cache"], 1)
				self.assertEqual(
					context["assets"], "/assets/illumenate_lighting/catalog_builder/catalog-builder"
				)
				self.assertEqual(
					context["mount_options"],
					{
						"csrfToken": "test-csrf",
						"referenceUrl": "/api/method/" + API + ".reference",
						"user": frappe.session.user,
					},
				)

	def test_workspace_merge_preserves_site_edits_and_adds_one_builder_shortcut(self):
		shipped = json.loads(
			(
				REPO
				/ "illumenate_lighting/illumenate_lighting/workspace/illumenate_lighting/illumenate_lighting.json"
			).read_text()
		)
		site = {
			"shortcuts": [{"label": "My shortcut", "type": "URL", "url": "/mine"}],
			"content": json.dumps([{"id": "my_block", "type": "header", "data": {"text": "My workspace"}}]),
		}
		with load_service("illumenate_lighting.portal_workspace") as (workspace, _):
			merged = workspace.merge_workspace(site, shipped)
			self.assertEqual(workspace.merge_workspace(merged, shipped), merged)
		self.assertEqual(merged["shortcuts"][0], site["shortcuts"][0])
		self.assertEqual(json.loads(merged["content"])[0], json.loads(site["content"])[0])
		self.assertEqual(
			[row for row in merged["shortcuts"] if row["label"] == "Catalog Builder"],
			[{"label": "Catalog Builder", "type": "URL", "url": "/catalog-builder"}],
		)
		self.assertEqual(
			[row for row in json.loads(merged["content"]) if row["id"] == "ill_catalog_builder"],
			[
				{
					"id": "ill_catalog_builder",
					"type": "shortcut",
					"data": {"shortcut_name": "Catalog Builder", "col": 3},
				}
			],
		)
