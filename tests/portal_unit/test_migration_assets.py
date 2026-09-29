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
SCHEMA_FILE = Path(__file__).parent / "fixtures/frappe_v16_migration_schema.json"


def read_json(path):
	return json.loads(path.read_text(encoding="utf-8"))


def fixture_records():
	# Match frappe.utils.fixtures.import_fixtures: app level, non-recursive.
	for path in sorted((APP / "fixtures").glob("*.json")):
		data = read_json(path)
		yield from data if isinstance(data, list) else [data]


def schema_errors(document, doctype, *, defaults=False, path=None):
	"""Check exported data against the owner's pinned Frappe schema.

	This is a static contract, not a replacement for Document.save(). Defaults
	are allowed for imports; existing Workspace saves must have actual values.
	"""
	schemas = read_json(SCHEMA_FILE)["schemas"]
	errors = []
	path = path or doctype
	if doctype not in schemas:
		return [f"{path}: missing test schema for {doctype}"]
	for name, field in schemas[doctype].items():
		value = document.get(name)
		if value in (None, "", []) and defaults:
			value = field.get("default", value)
		empty = value in (None, "", []) or (isinstance(value, str) and not value.strip())
		if empty:
			if field.get("reqd") and field["fieldtype"] != "Check":
				errors.append(f"{path}.{name}: mandatory")
			continue
		if field["fieldtype"] == "Select" and field.get("options"):
			if str(value).strip() not in field["options"].split("\n"):
				errors.append(f"{path}.{name}: invalid Select value {value!r}")
		if field["fieldtype"] in ("Data", "Link", "Dynamic Link", "Select"):
			if len(str(value)) > (field.get("length") or 140):
				errors.append(f"{path}.{name}: too long")
		if field["fieldtype"] in ("Table", "Table MultiSelect"):
			for index, row in enumerate(value):
				errors.extend(
					schema_errors(row, field["options"], defaults=defaults, path=f"{path}.{name}[{index}]")
				)
		if field["fieldtype"] == "Code" and field.get("options") == "JSON":
			try:
				json.loads(value)
			except (TypeError, ValueError):
				errors.append(f"{path}.{name}: invalid JSON")
	return errors


class MigrationAssets(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.schemas = {path: read_json(path) for path in (MODULE / "doctype").glob("*/*.json")}
		cls.by_name = {doc["name"]: doc for doc in cls.schemas.values()}

	def test_all_migration_assets_match_deployed_v16_field_constraints(self):
		paths = list((APP / "fixtures").glob("*.json"))
		for folder in ("doctype", "workspace", "page", "report", "print_format"):
			paths.extend((MODULE / folder).glob("*/*.json"))
		for path in paths:
			data = read_json(path)
			for doc in data if isinstance(data, list) else [data]:
				with self.subTest(asset=str(path), name=doc.get("name")):
					self.assertEqual(
						schema_errors(doc, doc["doctype"], defaults=doc["doctype"] != "Workspace"), []
					)

	def test_schema_contract_detects_the_reported_workspace_mandatory_error(self):
		workspace = read_json(WORKSPACE_FILE)
		workspace.pop("type")
		self.assertIn("Workspace.type: mandatory", schema_errors(workspace, "Workspace"))
		workspace["type"] = "workspace"
		self.assertIn(
			"Workspace.type: invalid Select value 'workspace'", schema_errors(workspace, "Workspace")
		)

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

	def test_single_settings_do_not_default_to_site_specific_link_records(self):
		# Frappe initializes Singles with a real save during install. Literal
		# accounting/master names are not guaranteed to exist on a new site.
		for doc in self.schemas.values():
			if not doc.get("issingle"):
				continue
			for field in doc["fields"]:
				if field["fieldtype"] in ("Link", "Dynamic Link"):
					with self.subTest(doctype=doc["name"], field=field["fieldname"]):
						self.assertFalse(field.get("default"))

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
				self.assertEqual(schema_errors(applied, "Workspace"), [])

			doc.save.side_effect = validate_links
			frappe.log_error = MagicMock()
			frappe.get_traceback = MagicMock(return_value="ValueError: Missing Number Card")
			# The failure is logged and rolled back instead of aborting the migration.
			module.after_migrate()
			frappe.db.rollback.assert_called_once_with(save_point=module.SAVEPOINT)
			self.assertIn("after_migrate", frappe.log_error.call_args.kwargs["title"])
			self.assertTrue(pending.exists())
			self.assertFalse((Path(temporary) / "last-merge.json").exists())
			available_cards.update(
				doc["name"] for doc in fixture_records() if doc["doctype"] == "Number Card"
			)
			module.after_migrate()
			self.assertTrue(pending.exists(), "Keep the backup pending until the enclosing migration commits")
			frappe.db.after_commit.add.call_args.args[0]()
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

	def test_old_workspace_snapshots_receive_type_without_overwriting_explicit_types(self):
		with load_service("illumenate_lighting.portal_workspace") as (module, _frappe):
			shipped = read_json(WORKSPACE_FILE)
			for legacy in ({}, {"type": None}, {"type": ""}):
				with self.subTest(legacy=legacy):
					self.assertEqual(module.merge_workspace(legacy, shipped)["type"], "Workspace")
			for kind in ("Workspace", "Link", "URL"):
				with self.subTest(kind=kind):
					self.assertEqual(module.merge_workspace({"type": kind}, shipped)["type"], kind)

	def test_hook_does_not_clear_backup_if_later_migration_work_rolls_back(self):
		with (
			load_service("illumenate_lighting.portal_workspace") as (module, frappe),
			tempfile.TemporaryDirectory() as temporary,
			patch.object(module, "_directory", return_value=Path(temporary)),
		):
			site = read_json(WORKSPACE_FILE)
			site.pop("type")
			frappe.get_doc.return_value.as_dict.return_value = site
			frappe.get_app_path = MagicMock(return_value=str(WORKSPACE_FILE))
			module.before_migrate()
			module.after_migrate()
			self.assertTrue((Path(temporary) / "pending.json").exists())
			self.assertFalse((Path(temporary) / "last-merge.json").exists())
			# Frappe discards after_commit callbacks on rollback. The pending file
			# must still point to the original snapshot for the next migration.
			frappe.db.after_commit.add.reset_mock()
			module.before_migrate()
			module.after_migrate()
			frappe.db.after_commit.add.call_args.args[0]()
			self.assertFalse((Path(temporary) / "pending.json").exists())

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
