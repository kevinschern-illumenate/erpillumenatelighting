"""Installed-site checks for the September 2026 migration repair.

Run on a migrated test site with bench run-tests --module
illumenate_lighting.illumenate_lighting.api.test_migration_assets.
The local portal_unit suite checks packaging without Frappe; these tests check
real controller imports, installed records and Frappe link validation.
"""

import json
from pathlib import Path

import frappe
from frappe.model.base_document import get_controller
from frappe.model.document import Document
from frappe.tests.utils import FrappeTestCase


class TestMigrationAssets(FrappeTestCase):
	def test_shipped_doctypes_survive_orphan_cleanup(self):
		folder = Path(frappe.get_app_path("illumenate_lighting", "illumenate_lighting", "doctype"))
		for path in folder.glob("*/*.json"):
			name = json.loads(path.read_text(encoding="utf-8"))["name"]
			with self.subTest(doctype=name):
				self.assertTrue(frappe.db.exists("DocType", name))
				self.assertTrue(issubclass(get_controller(name), Document))

	def test_workspace_and_number_card_links_resolve(self):
		fixture = Path(frappe.get_app_path("illumenate_lighting", "fixtures", "number_card.json"))
		for definition in json.loads(fixture.read_text(encoding="utf-8")):
			with self.subTest(card=definition["name"]):
				card = frappe.get_doc("Number Card", definition["name"])
				card._validate_links()
				card.validate()
		workspace = frappe.get_doc("Workspace", "ilLumenate Lighting")
		workspace._validate_links()
