"""Migration asset contracts, checked without a running Frappe site.

Frappe discovers fixtures at app/fixtures and resolves controller class names
case-sensitively. A wrong class name can cause v16 orphan cleanup to remove an
otherwise valid DocType. These checks cover the complete shipped schema.
"""

import ast
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from test_services import load_service

APP = Path(__file__).resolve().parents[2] / "illumenate_lighting"
MODULE = APP / "illumenate_lighting"
WORKSPACE_FILE = MODULE / "workspace/illumenate_lighting/illumenate_lighting.json"


def read_json(path):
	return json.loads(path.read_text(encoding="utf-8"))


def fixture_records():
	# Match frappe.utils.fixtures.import_fixtures: app level, non-recursive.
	for path in sorted((APP / "fixtures").glob("*.json")):
		data = read_json(path)
		yield from data if isinstance(data, list) else [data]


class MigrationAssets(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.schemas = {path: read_json(path) for path in (MODULE / "doctype").glob("*/*.json")}
		cls.by_name = {doc["name"]: doc for doc in cls.schemas.values()}

	def test_every_standard_doctype_has_the_exact_controller_class(self):
		for path, doc in self.schemas.items():
			with self.subTest(doctype=doc["name"]):
				controller = ast.parse(path.with_suffix(".py").read_text(encoding="utf-8"))
				classes = {node.name for node in controller.body if isinstance(node, ast.ClassDef)}
				# frappe.model.base_document.import_controller preserves capitalization.
				expected = doc["name"].replace(" ", "").replace("-", "")
				self.assertIn(expected, classes)

	def test_schema_paths_and_modules_are_discoverable(self):
		modules = (APP / "modules.txt").read_text(encoding="utf-8").splitlines()
		for path, doc in self.schemas.items():
			with self.subTest(doctype=doc["name"]):
				self.assertEqual(path.stem, doc["name"].lower().replace(" ", "_").replace("-", "_"))
				self.assertEqual(path.parent.name, path.stem)
				self.assertTrue((path.parent / "__init__.py").is_file())
				self.assertIn(doc["module"], modules)

	def test_child_tables_and_app_links_resolve(self):
		for doc in self.schemas.values():
			for field in doc["fields"]:
				with self.subTest(doctype=doc["name"], field=field["fieldname"]):
					target = field.get("options", "")
					if field["fieldtype"] in ("Table", "Table MultiSelect"):
						self.assertIn(target, self.by_name)
						self.assertTrue(self.by_name[target].get("istable"))
					elif field["fieldtype"] == "Link" and target.startswith(("ilL-", "ILL ")):
						self.assertIn(target, self.by_name)

	def test_workspace_destinations_are_shipped(self):
		available = {("DocType", name) for name in self.by_name}
		for kind in ("page", "report", "workspace", "dashboard_chart", "custom_html_block"):
			for path in (MODULE / kind).glob("*/*.json"):
				doc = read_json(path)
				available.add((doc["doctype"], doc["name"]))
		available.update((doc["doctype"], doc["name"]) for doc in fixture_records())
		workspace = read_json(WORKSPACE_FILE)
		for field, type_field in (("shortcuts", "type"), ("links", "link_type")):
			for row in workspace.get(field, []):
				if row.get("link_to") and row.get(type_field) != "URL":
					with self.subTest(field=field, target=row["link_to"]):
						self.assertIn((row[type_field], row["link_to"]), available)
		for field, target_type, name_field in (
			("number_cards", "Number Card", "number_card_name"),
			("charts", "Dashboard Chart", "chart_name"),
			("quick_lists", "DocType", "document_type"),
			("custom_blocks", "Custom HTML Block", "custom_block_name"),
		):
			for row in workspace.get(field, []):
				with self.subTest(field=field, target=row[name_field]):
					self.assertIn((target_type, row[name_field]), available)

	def test_all_six_number_cards_are_loaded_from_the_app_fixture_directory(self):
		cards = {doc["name"]: doc for doc in fixture_records() if doc["doctype"] == "Number Card"}
		workspace_cards = {row["number_card_name"] for row in read_json(WORKSPACE_FILE)["number_cards"]}
		self.assertEqual(len(workspace_cards), 6)
		self.assertTrue(workspace_cards <= cards.keys())
		for name in workspace_cards:
			with self.subTest(card=name):
				card = cards[name]
				self.assertEqual(card["type"], "Document Type")
				self.assertIn(
					card["document_type"],
					("Quotation", "Sales Order", "Sales Invoice", "Purchase Order", "Purchase Invoice"),
				)
				self.assertIsInstance(json.loads(card["filters_json"]), list)
				if card["function"] != "Count":
					self.assertTrue(card["aggregate_function_based_on"])


class WorkspaceMigrationRetry(unittest.TestCase):
	def test_failed_restore_retains_original_backup_and_succeeds_after_fixture_sync(self):
		with (
			load_service("illumenate_lighting.portal_workspace") as (module, frappe),
			tempfile.TemporaryDirectory() as temporary,
			patch.object(module, "_directory", return_value=Path(temporary)),
		):
			shipped = read_json(WORKSPACE_FILE)
			site = copy.deepcopy(shipped)
			site["content"] = json.dumps(
				[{"id": "site-block", "type": "header", "data": {"text": "Our process"}}]
			)
			site["shortcuts"].append({"label": "Our customers", "type": "DocType", "link_to": "Customer"})
			site["number_cards"].append({"label": "Site card", "number_card_name": "Site card"})
			doc = MagicMock()
			doc.as_dict.return_value = site
			frappe.get_doc.return_value = doc
			frappe.get_app_path = MagicMock(return_value=str(WORKSPACE_FILE))
			frappe.db.exists.return_value = True
			module.before_migrate()
			pending = Path(temporary) / "pending.json"
			backup = Path(temporary) / read_json(pending)["backup"]
			original = backup.read_bytes()
			# A failed migration has already imported the exported Workspace.
			doc.as_dict.return_value = shipped
			module.before_migrate()
			self.assertEqual(backup.read_bytes(), original)

			applied = {}
			doc.set.side_effect = applied.__setitem__
			available_cards = {"Site card"}

			def validate_links(**kwargs):
				for row in applied["number_cards"]:
					if row["number_card_name"] not in available_cards:
						raise ValueError("Missing Number Card")

			doc.save.side_effect = validate_links
			with self.assertRaisesRegex(ValueError, "Missing Number Card"):
				module.after_migrate()
			self.assertTrue(pending.exists())
			self.assertFalse((Path(temporary) / "last-merge.json").exists())
			available_cards.update(
				doc["name"] for doc in fixture_records() if doc["doctype"] == "Number Card"
			)
			module.after_migrate()
			self.assertFalse(pending.exists())
			self.assertEqual(backup.read_bytes(), original)
			self.assertEqual(read_json(Path(temporary) / "last-merge.json")["backup"], backup.name)
			self.assertIn(site["shortcuts"][-1], applied["shortcuts"])
			self.assertEqual(json.loads(applied["content"])[0]["data"]["text"], "Our process")
			self.assertEqual(len(applied["number_cards"]), 7)
			doc.save.assert_called_with(ignore_permissions=True)
			# Once the pending merge is consumed, another hook call is a no-op.
			doc.save.reset_mock()
			module.after_migrate()
			doc.save.assert_not_called()

	def test_fresh_site_without_pending_workspace_backup_is_a_noop(self):
		with (
			load_service("illumenate_lighting.portal_workspace") as (module, frappe),
			tempfile.TemporaryDirectory() as temporary,
			patch.object(module, "_directory", return_value=Path(temporary)),
		):
			frappe.db.exists.return_value = False
			module.before_migrate()
			module.after_migrate()
			frappe.get_doc.assert_not_called()
