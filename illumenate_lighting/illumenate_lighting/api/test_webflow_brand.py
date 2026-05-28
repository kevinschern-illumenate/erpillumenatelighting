# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""Tests for the per-brand Webflow architecture (webflow_brand,
webflow_export per-brand filtering, mark_webflow_synced, sync events)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from illumenate_lighting.illumenate_lighting.api import webflow_brand
from illumenate_lighting.illumenate_lighting.api.webflow_export import (
	get_webflow_products,
	mark_webflow_synced,
)
from illumenate_lighting.illumenate_lighting.api.webflow_attributes import (
	get_webflow_attributes,
)
from illumenate_lighting.illumenate_lighting.api.webflow_sync_events import (
	on_product_update,
)


def _ensure_brand(code: str, *, is_default: int = 0, is_active: int = 1,
                  include_configurator: int = 1) -> str:
	existing = frappe.db.get_value("ilL-Webflow-Brand", {"brand_code": code}, "name")
	if existing:
		return existing
	doc = frappe.new_doc("ilL-Webflow-Brand")
	doc.update({
		"brand_code": code,
		"brand_label": code,
		"is_default": is_default,
		"is_active": is_active,
		"sync_enabled": 1,
		"include_configurator_payload": include_configurator,
	})
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_product(name: str, *, target_brands: list[str], active: int = 1) -> str:
	if frappe.db.exists("ilL-Webflow-Product", name):
		frappe.delete_doc("ilL-Webflow-Product", name, force=1, ignore_permissions=True)
	doc = frappe.new_doc("ilL-Webflow-Product")
	doc.update({
		"product_name": name.replace("-", " ").title(),
		"product_slug": name,
		"product_type": "Component",
		"is_active": active,
		"is_configurable": 1,
	})
	for b in target_brands:
		doc.append("target_brands", {"brand": b, "enabled": 1})
	doc.insert(ignore_permissions=True)
	return doc.name


class TestWebflowBrandResolution(FrappeTestCase):
	def setUp(self):
		_ensure_brand("illumenate", is_default=1)
		_ensure_brand("test_brand_x", is_active=1)
		webflow_brand.clear_brand_cache()

	def test_resolve_brand_unknown_raises(self):
		with self.assertRaises(frappe.ValidationError):
			webflow_brand.resolve_brand("does_not_exist")

	def test_resolve_brand_inactive_raises(self):
		_ensure_brand("inactive_brand_y", is_active=0)
		webflow_brand.clear_brand_cache()
		with self.assertRaises(frappe.ValidationError):
			webflow_brand.resolve_brand("inactive_brand_y")

	def test_resolve_brand_inactive_allow_inactive(self):
		_ensure_brand("inactive_brand_z", is_active=0)
		webflow_brand.clear_brand_cache()
		brand = webflow_brand.resolve_brand("inactive_brand_z", allow_inactive=True)
		self.assertEqual(brand["brand_code"], "inactive_brand_z")

	def test_default_brand(self):
		self.assertEqual(webflow_brand.get_default_brand(), "illumenate")

	def test_list_active_brands(self):
		codes = webflow_brand.list_active_brands()
		self.assertIn("illumenate", codes)

	def test_cache_invalidation_on_save(self):
		# Cache populated...
		webflow_brand.list_active_brands()
		# Edit a brand and ensure cache is busted via the on_brand_update hook.
		brand_name = frappe.db.get_value("ilL-Webflow-Brand", {"brand_code": "test_brand_x"}, "name")
		doc = frappe.get_doc("ilL-Webflow-Brand", brand_name)
		doc.brand_label = "renamed-x"
		doc.save(ignore_permissions=True)
		# After save the cache should have been cleared by on_brand_update.
		brand = webflow_brand.resolve_brand("test_brand_x", allow_inactive=True)
		self.assertEqual(brand["brand_label"], "renamed-x")


class TestWebflowExportPerBrand(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		_ensure_brand("illumenate", is_default=1)
		_ensure_brand("brand_206_test", is_active=1, include_configurator=0)
		webflow_brand.clear_brand_cache()

	def setUp(self):
		_make_product("test-prod-illumenate-only", target_brands=["illumenate"])
		_make_product("test-prod-multi", target_brands=["illumenate", "brand_206_test"])
		_make_product("test-prod-206-only", target_brands=["brand_206_test"])

	def tearDown(self):
		for n in ["test-prod-illumenate-only", "test-prod-multi", "test-prod-206-only"]:
			if frappe.db.exists("ilL-Webflow-Product", n):
				frappe.delete_doc("ilL-Webflow-Product", n, force=1, ignore_permissions=True)

	def test_filtered_to_target_brand(self):
		out = get_webflow_products(brand="brand_206_test", limit=100)
		names = {p["name"] for p in out["products"]}
		self.assertIn("test-prod-multi", names)
		self.assertIn("test-prod-206-only", names)
		self.assertNotIn("test-prod-illumenate-only", names)
		self.assertEqual(out["brand"], "brand_206_test")

	def test_configurator_stripped_for_206(self):
		out = get_webflow_products(brand="brand_206_test", limit=100)
		for p in out["products"]:
			self.assertEqual(p.get("is_configurable"), 0)
			self.assertEqual(p.get("configurator_options"), [])
			self.assertIsNone(p.get("min_length_mm"))


class TestMarkWebflowSyncedPerBrand(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		_ensure_brand("illumenate", is_default=1)
		_ensure_brand("brand_206_test", is_active=1)
		webflow_brand.clear_brand_cache()

	def setUp(self):
		_make_product("test-prod-marker", target_brands=["illumenate", "brand_206_test"])

	def tearDown(self):
		if frappe.db.exists("ilL-Webflow-Product", "test-prod-marker"):
			frappe.delete_doc("ilL-Webflow-Product", "test-prod-marker", force=1, ignore_permissions=True)

	def test_mark_synced_writes_only_to_named_brand(self):
		mark_webflow_synced(
			product_slug="test-prod-marker",
			webflow_item_id="wf-id-206",
			webflow_collection_slug="products",
			brand="brand_206_test",
		)
		rows = frappe.get_all(
			"ilL-Child-Webflow-Sync-State",
			filters={"parent": "test-prod-marker"},
			fields=["brand", "webflow_item_id", "sync_status"],
		)
		by_brand = {r["brand"]: r for r in rows}
		self.assertEqual(by_brand["brand_206_test"]["webflow_item_id"], "wf-id-206")
		self.assertEqual(by_brand["brand_206_test"]["sync_status"], "Synced")
		# illumenate row was untouched (or never created — both pass the test).
		other = by_brand.get("illumenate")
		if other:
			self.assertNotEqual(other["webflow_item_id"], "wf-id-206")


class TestWebflowSyncEvents(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		_ensure_brand("illumenate", is_default=1)
		_ensure_brand("brand_206_test", is_active=1)
		webflow_brand.clear_brand_cache()

	def setUp(self):
		_make_product("test-prod-event-multi", target_brands=["illumenate", "brand_206_test"])
		_make_product("test-prod-event-single", target_brands=["illumenate"])

	def tearDown(self):
		for n in ["test-prod-event-multi", "test-prod-event-single"]:
			if frappe.db.exists("ilL-Webflow-Product", n):
				frappe.delete_doc("ilL-Webflow-Product", n, force=1, ignore_permissions=True)

	def test_multi_brand_targeted_flips_both(self):
		doc = frappe.get_doc("ilL-Webflow-Product", "test-prod-event-multi")
		on_product_update(doc, "on_update")
		rows = frappe.get_all(
			"ilL-Child-Webflow-Sync-State",
			filters={"parent": "test-prod-event-multi"},
			fields=["brand", "sync_status"],
		)
		by_brand = {r["brand"]: r["sync_status"] for r in rows}
		self.assertEqual(by_brand.get("illumenate"), "Pending")
		self.assertEqual(by_brand.get("brand_206_test"), "Pending")

	def test_single_brand_targeted_flips_only_one(self):
		doc = frappe.get_doc("ilL-Webflow-Product", "test-prod-event-single")
		on_product_update(doc, "on_update")
		rows = frappe.get_all(
			"ilL-Child-Webflow-Sync-State",
			filters={"parent": "test-prod-event-single"},
			fields=["brand", "sync_status"],
		)
		by_brand = {r["brand"]: r["sync_status"] for r in rows}
		self.assertEqual(by_brand.get("illumenate"), "Pending")
		self.assertNotIn("brand_206_test", by_brand)


class TestWebflowAttributesPerBrandSyncFilter(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		_ensure_brand("illumenate", is_default=1)
		_ensure_brand("brand_206_test", is_active=1)
		webflow_brand.clear_brand_cache()

	def setUp(self):
		self.created = []
		for slug in [
			"test-cct-per-brand-pending",
			"test-cct-legacy-pending",
			"test-cct-per-brand-synced-legacy-pending",
			"test-cct-both-pending",
		]:
			if frappe.db.exists("ilL-Attribute-CCT", slug):
				frappe.delete_doc("ilL-Attribute-CCT", slug, force=1, ignore_permissions=True)

	def tearDown(self):
		for name in self.created:
			if frappe.db.exists("ilL-Attribute-CCT", name):
				frappe.delete_doc("ilL-Attribute-CCT", name, force=1, ignore_permissions=True)

	def _make_cct(self, cct_name: str, legacy_status: str) -> str:
		doc = frappe.new_doc("ilL-Attribute-CCT")
		doc.update({
			"cct_name": cct_name,
			"code": cct_name[-4:].upper(),
			"kelvin": 3000,
			"is_active": 1,
		})
		doc.insert(ignore_permissions=True)
		if frappe.get_meta("ilL-Attribute-CCT").has_field("webflow_sync_status"):
			frappe.db.set_value("ilL-Attribute-CCT", doc.name, "webflow_sync_status", legacy_status)
		self.created.append(doc.name)
		return doc.name

	def _set_brand_sync(self, doc_name: str, status: str):
		row = frappe.db.get_value(
			"ilL-Child-Webflow-Sync-State",
			{
				"parenttype": "ilL-Attribute-CCT",
				"parent": doc_name,
				"brand": "brand_206_test",
			},
			"name",
		)
		if row:
			frappe.db.set_value("ilL-Child-Webflow-Sync-State", row, "sync_status", status)
			return
		parent = frappe.get_doc("ilL-Attribute-CCT", doc_name)
		parent.append(
			"webflow_sync_targets",
			{"brand": "brand_206_test", "sync_status": status},
		)
		parent.save(ignore_permissions=True)

	def test_needs_sync_prefers_per_brand_with_legacy_fallback(self):
		meta = frappe.get_meta("ilL-Attribute-CCT")
		if not meta.has_field("webflow_sync_status") or not meta.has_field("webflow_sync_targets"):
			self.skipTest("CCT doctype missing webflow sync fields required for migration tests")

		per_brand_pending = self._make_cct("test-cct-per-brand-pending", "Synced")
		legacy_pending = self._make_cct("test-cct-legacy-pending", "Pending")
		per_brand_synced_legacy_pending = self._make_cct(
			"test-cct-per-brand-synced-legacy-pending", "Pending"
		)
		both_pending = self._make_cct("test-cct-both-pending", "Pending")

		self._set_brand_sync(per_brand_pending, "Pending")
		self._set_brand_sync(per_brand_synced_legacy_pending, "Synced")
		self._set_brand_sync(both_pending, "Pending")
		frappe.db.commit()

		out = get_webflow_attributes(
			attribute_type="cct",
			sync_status="needs_sync",
			brand="brand_206_test",
			limit=200,
		)
		names = [a["name"] for a in out["attributes"]]
		name_set = set(names)

		self.assertIn(per_brand_pending, name_set)
		self.assertIn(legacy_pending, name_set)
		self.assertIn(both_pending, name_set)
		self.assertNotIn(per_brand_synced_legacy_pending, name_set)
		self.assertEqual(names.count(both_pending), 1)
