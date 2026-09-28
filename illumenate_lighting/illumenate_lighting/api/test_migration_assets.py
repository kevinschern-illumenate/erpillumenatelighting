"""Installed-site checks for the September 2026 migration repair.

Run on a migrated test site with bench run-tests --module
illumenate_lighting.illumenate_lighting.api.test_migration_assets.
The local portal_unit suite checks packaging without Frappe; these tests check
real controller imports, installed records and Frappe link validation.
"""

import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.model.base_document import get_controller
from frappe.model.document import Document

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # Frappe v15
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from illumenate_lighting import portal_workspace


class TestMigrationAssets(IntegrationTestCase):
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
				card.save(ignore_permissions=True)
		workspace = frappe.get_doc("Workspace", "ilLumenate Lighting")
		# Exercise the complete pipeline, including mandatory/select/length
		# validation and Workspace.validate(), not just foreign-key checks.
		workspace.save(ignore_permissions=True)

	def test_legacy_pending_backups_pass_a_real_workspace_save(self):
		if not frappe.get_meta("Workspace").has_field("type"):
			self.skipTest("Workspace.type is a v16 field")
		for kind in ("absent", None, ""):
			with self.subTest(type=kind), tempfile.TemporaryDirectory() as temporary:
				directory = Path(temporary)
				site = frappe.get_doc("Workspace", "ilLumenate Lighting").as_dict()
				if kind == "absent":
					site.pop("type", None)
				else:
					site["type"] = kind
				blocks = json.loads(site["content"])
				blocks.append(
					{
						"id": "migration-test-site-block",
						"type": "header",
						"data": {"text": "Site customizations"},
					}
				)
				site["content"] = json.dumps(blocks)
				data = frappe.as_json(site).encode()
				name = hashlib.sha256(data).hexdigest() + ".json"
				(directory / name).write_bytes(data)
				(directory / "pending.json").write_text(json.dumps({"backup": name}), encoding="utf-8")
				frappe.db.set_value("Workspace", "ilLumenate Lighting", "type", None)
				with self.assertRaises(frappe.MandatoryError):
					frappe.get_doc("Workspace", "ilLumenate Lighting").save(ignore_permissions=True)
				with (
					patch.object(portal_workspace, "_directory", return_value=directory),
					patch.object(frappe.db, "after_commit") as after_commit,
				):
					portal_workspace.after_migrate()
					workspace = frappe.get_doc("Workspace", "ilLumenate Lighting")
					self.assertEqual(workspace.type, "Workspace")
					self.assertIn("Site customizations", workspace.content)
					self.assertTrue((directory / "pending.json").exists())
					self.assertEqual((directory / name).read_bytes(), data)
					after_commit.add.call_args.args[0]()
					self.assertFalse((directory / "pending.json").exists())

	def test_all_imported_assets_pass_framework_field_validation(self):
		module = Path(frappe.get_app_path("illumenate_lighting", "illumenate_lighting"))
		paths = list(Path(frappe.get_app_path("illumenate_lighting", "fixtures")).glob("*.json"))
		for folder in ("doctype", "workspace", "page", "report", "print_format"):
			paths.extend((module / folder).glob("*/*.json"))
		for path in paths:
			data = json.loads(path.read_text(encoding="utf-8"))
			for definition in data if isinstance(data, list) else [data]:
				with self.subTest(doctype=definition["doctype"], name=definition["name"]):
					doc = frappe.get_doc(definition["doctype"], definition["name"])
					doc._validate_mandatory()
					for row in [doc, *doc.get_all_children()]:
						row._validate_selects()
						row._validate_length()
						row._validate_data_fields()
						row._validate_code_fields()
