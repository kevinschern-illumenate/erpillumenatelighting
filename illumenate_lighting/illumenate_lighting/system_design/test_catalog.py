# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Installed-site checks for the design catalog snapshot (WP-2.1): queries, storage, cache and endpoint."""

import frappe
from frappe.tests import IntegrationTestCase

from illumenate_lighting.illumenate_lighting.system_design import api, catalog


class TestDesignCatalog(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_snapshot_is_stored_cached_and_reused(self):
		catalog.invalidate()
		first = catalog.current_snapshot_hash()
		self.assertEqual(len(first), 64)
		self.assertTrue(frappe.db.exists(catalog.SNAPSHOT_DOCTYPE, first))
		self.assertEqual(catalog.current_snapshot_hash(), first)
		catalog.invalidate()
		self.assertEqual(catalog.build_snapshot(), first)
		frappe.cache().delete_value(catalog.CACHE_PREFIX + first)
		payload = catalog.get_snapshot(first)
		self.assertEqual(payload["engine_contract_version"], catalog.ENGINE_CONTRACT_VERSION)
		self.assertEqual(catalog.forbidden_keys(payload), set())
		stored = frappe.get_doc(catalog.SNAPSHOT_DOCTYPE, first)
		self.assertEqual(stored.item_count, len(payload["items"]))

	def test_endpoint(self):
		response = api.get_catalog()
		self.assertTrue(response["success"], response)
		self.assertEqual(response["data"]["hash"], catalog.current_snapshot_hash())
		self.assertEqual(api.get_catalog(hash="0" * 64)["code"], "NOT_FOUND")
		self.assertTrue(api.get_catalog_for_desktop()["success"])
		frappe.set_user("Guest")
		self.assertEqual(api.get_catalog()["code"], "FORBIDDEN")
