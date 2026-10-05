"""Audit DocType access contract; transaction tests live in api.test_catalog_import."""

import frappe
from frappe.tests import IntegrationTestCase

# This metadata test does not need ERPNext's transitive User fixtures.
IGNORE_TEST_RECORD_DEPENDENCIES = ["User"]


class TestilLCatalogImport(IntegrationTestCase):
	def test_audit_is_read_only_and_tracebacks_need_higher_permission(self):
		meta = frappe.get_meta("ilL-Catalog-Import")
		self.assertFalse(meta.allow_import)
		self.assertTrue(all(field.read_only for field in meta.fields))
		self.assertEqual(meta.get_field("error_detail").permlevel, 1)
		self.assertTrue(
			all(not permission.create and not permission.write for permission in meta.permissions)
		)
