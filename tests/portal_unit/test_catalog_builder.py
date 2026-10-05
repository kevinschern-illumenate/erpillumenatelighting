"""Catalog Builder authorization, live references, and page boot options."""

import json
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime
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
	def test_unauthorized_users_cannot_read_or_copy_records(self):
		for access in (
			{"user": "Guest"},
			{"roles": ["Dealer"]},
			{"roles": []},
			{"roles": ["ilL Engineering"]},
			{"enabled": 0},
			{"user_type": "Website User"},
		):
			with self.subTest(access=access), catalog_service(API, **access) as (service, frappe):
				with patch.object(service, "live_reference") as live:
					with self.assertRaises(PermissionError):
						service.reference()
					with self.assertRaises(PermissionError):
						service.record("Item", "secret")
					live.assert_not_called()
					frappe.cache().get_value.assert_not_called()
					frappe.get_doc.assert_not_called()

	def test_cache_is_user_scoped_and_refresh_bypasses_it(self):
		for access in ({}, {"roles": ["System Manager"]}, {"user": "Administrator", "roles": []}):
			with self.subTest(access=access), catalog_service(API, **access) as (service, frappe):
				cache = frappe.cache()
				cache.get_value.return_value = None
				with patch.object(service, "live_reference", return_value={"source": "live"}) as live:
					self.assertEqual(service.reference.whitelist_options, {"methods": ["GET"]})
					self.assertEqual(service.reference(), {"source": "live"})
					cache.get_value.assert_called_once_with(service.CACHE_KEY, user=frappe.session.user)
					cache.set_value.assert_called_once_with(
						service.CACHE_KEY, {"source": "live"}, user=frappe.session.user, expires_in_sec=300
					)
					cache.get_value.return_value = {"source": "cached"}
					self.assertEqual(service.reference(), {"source": "cached"})
					live.assert_called_once()
					self.assertEqual(service.reference(refresh="1"), {"source": "live"})
					self.assertEqual(live.call_count, 2)

	def test_live_reference_requests_only_readable_summary_fields_and_rows(self):
		def field(name, kind="Data"):
			return {"fieldname": name, "fieldtype": kind}

		schema = {
			"doctypes": {
				"Item": {
					"fields": [
						field("item_code"),
						field("disabled", "Check"),
						field("description", "Text Editor"),
						field("rate", "Currency"),
						field("image", "Attach Image"),
						field("children", "Table"),
						field("removed"),
						field("restricted"),
					]
				},
				"ilL-Webflow-Product": {"fields": [field("title"), field("date", "Date")]},
				"Brand": {"fields": []},
				"Missing": {"fields": []},
				"Item Price": {"fields": []},
				"Child": {"istable": 1, "fields": []},
			}
		}
		with (
			catalog_service(API) as (service, frappe),
			patch.object(service, "cached_schema", return_value=schema),
		):
			frappe.utils.now_datetime = lambda: datetime(2026, 10, 5, 12, 34, 56)
			frappe.db.exists.side_effect = lambda dt, name: name != "Missing"
			frappe.has_permission.side_effect = lambda dt, permission: dt != "Brand"
			meta = MagicMock()
			meta.has_field.side_effect = lambda name: name != "removed"
			meta.get_permitted_fieldnames.return_value = ["item_code", "disabled", "removed", "title", "date"]
			frappe.get_meta = MagicMock(return_value=meta)
			frappe.get_list = MagicMock(
				side_effect=[
					[{"name": "ITEM-1", "item_code": "ITEM-1", "disabled": 0}],
					[{"name": "WEB-1", "title": "Example"}],
				]
			)
			data = service.live_reference()
			self.assertEqual(data["source"], "live")
			self.assertEqual(data["schema_version"], 1)
			self.assertEqual(data["exported_on"], "2026-10-05T12:34:56")
			self.assertEqual(data["skipped"], ["Brand", "Missing"])
			self.assertEqual(
				data["doctypes"]["Item"],
				{
					"source": "live",
					"exported_on": data["exported_on"],
					"records": {"ITEM-1": {"item_code": "ITEM-1"}},
				},
			)
			self.assertEqual(
				[call.args[0] for call in frappe.get_list.call_args_list], ["Item", "ilL-Webflow-Product"]
			)
			self.assertEqual(
				frappe.get_list.call_args_list[0].kwargs,
				{"fields": ["name", "item_code", "disabled"], "limit_page_length": 0, "order_by": "name asc"},
			)
			self.assertEqual(frappe.get_list.call_args_list[1].kwargs["fields"], ["name", "title"])
			frappe.get_all.assert_not_called()

	def test_record_rejects_non_catalog_prices_and_children(self):
		with catalog_service(API) as (service, frappe):
			for doctype in ("User", "Item Price", "Item Variant Attribute", "Unknown"):
				with self.subTest(doctype=doctype), self.assertRaises(frappe.ValidationError):
					service.record(doctype, "test")
			frappe.get_doc.assert_not_called()

	def test_record_requires_read_permission_before_serializing(self):
		with catalog_service(API) as (service, frappe):
			frappe.get_doc.return_value.check_permission.side_effect = PermissionError
			with self.assertRaises(PermissionError):
				service.record("Item", "secret")
			frappe.get_doc.return_value.as_dict.assert_not_called()

	def test_record_copies_children_after_field_permissions_and_strips_metadata(self):
		with catalog_service(API) as (service, frappe):
			doc = frappe.get_doc.return_value
			data = {
				"doctype": "Item",
				"name": "ITEM-1",
				"owner": "private",
				"item_code": "ITEM-1",
				"description": "Full description",
				"disabled": 0,
				"valuation_rate": 99,
				"supplier_items": [{"supplier": "private"}],
				"attributes": [
					{
						"name": "child-id",
						"idx": 1,
						"parent": "ITEM-1",
						"attribute": "Color",
						"attribute_value": "White",
					}
				],
				"brand": "restricted",
			}
			doc.apply_fieldlevel_read_permissions.side_effect = lambda: data.pop("brand")
			doc.as_dict.side_effect = lambda: data
			self.assertEqual(service.record.whitelist_options, {"methods": ["GET"]})
			self.assertEqual(
				service.record("Item", "ITEM-1"),
				{
					"item_code": "ITEM-1",
					"description": "Full description",
					"disabled": 0,
					"attributes": [{"attribute": "Color", "attribute_value": "White"}],
				},
			)
			doc.check_permission.assert_called_once_with("read")
			doc.apply_fieldlevel_read_permissions.assert_called_once()


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
