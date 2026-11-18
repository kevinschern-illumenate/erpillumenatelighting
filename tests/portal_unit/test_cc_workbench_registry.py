"""Command Center Workbench registry (v8): every app doctype has a home, or is deliberately left out.

The gateway (a Server Script, so not importable) declares ILL_GROUPS, SETTINGS, EXCLUDED, READ_ONLY and
CREATE_VIA_BUILDER as literals inside main(). This test reads them from the source with ast and checks
them against the shipped doctype JSON, so a new doctype can't silently go missing from the Workbench.
"""

import ast
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GATEWAY = REPO / "illumenate_lighting/command_center/ss/cc_gateway.py"
DOCTYPES = REPO / "illumenate_lighting/illumenate_lighting/doctype"
# standard ERPNext doctypes the gateway may name in these lists
STANDARD = {"Item"}


def gateway_literals():
	tree = ast.parse(GATEWAY.read_text(encoding="utf-8"))
	main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
	found = {}
	for node in main.body:
		if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
			name = node.targets[0].id
			if name in ("ILL_GROUPS", "SETTINGS", "EXCLUDED", "READ_ONLY", "CREATE_VIA_BUILDER", "ALLOWED"):
				found[name] = ast.literal_eval(node.value)
	return found


def app_doctypes():
	out = {}
	for path in DOCTYPES.glob("*/*.json"):
		doc = json.loads(path.read_text(encoding="utf-8"))
		if doc.get("doctype") == "DocType":
			out[doc["name"]] = doc
	return out


class WorkbenchRegistry(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.g = gateway_literals()
		cls.docs = app_doctypes()
		cls.grouped = {}
		for key, _label, _role, names in cls.g["ILL_GROUPS"]:
			for name in names:
				cls.grouped.setdefault(name, []).append(key)
		# CREATE_VIA_BUILDER is extended in main() from the structural groups; mirror that here
		cls.builder = set(cls.g["CREATE_VIA_BUILDER"])
		for key, _label, _role, names in cls.g["ILL_GROUPS"]:
			if key in ("ill_templates", "ill_specs", "ill_rels", "ill_submittals"):
				cls.builder.update(names)

	def test_every_listable_app_doctype_is_grouped_or_excluded(self):
		listable = {n for n, d in self.docs.items() if not d.get("istable") and not d.get("issingle")}
		missing = sorted(listable - set(self.grouped) - set(self.g["EXCLUDED"]))
		self.assertEqual(missing, [], "add these to an ILL_GROUPS group in cc_gateway.py, or to EXCLUDED")

	def test_each_doctype_is_in_exactly_one_group(self):
		self.assertEqual({n: k for n, k in self.grouped.items() if len(k) > 1}, {})

	def test_groups_only_name_shipped_listable_doctypes(self):
		for name in self.grouped:
			with self.subTest(doctype=name):
				self.assertIn(name, self.docs)
				self.assertFalse(self.docs[name].get("istable"), "child tables are never listed")
				self.assertFalse(self.docs[name].get("issingle"), "singles go in SETTINGS")

	def test_group_keys_are_prefixed_and_unique(self):
		keys = [g[0] for g in self.g["ILL_GROUPS"]]
		self.assertEqual(len(keys), len(set(keys)))
		self.assertTrue(all(k.startswith("ill_") for k in keys))

	def test_singles_are_settings_links_or_excluded(self):
		singles = {n for n, d in self.docs.items() if d.get("issingle")}
		self.assertEqual(sorted(singles - set(self.g["SETTINGS"]) - set(self.g["EXCLUDED"])), [])
		for name in self.g["SETTINGS"]:
			self.assertIn(name, singles)

	def test_session_tokens_and_credentials_are_excluded(self):
		for name in ("ilL-Webflow-Session", "ilL-Webflow-Settings", "ilL-QBO-Settings"):
			self.assertIn(name, self.g["EXCLUDED"])
			self.assertNotIn(name, self.grouped)
			self.assertNotIn(name, self.g["SETTINGS"])
			self.assertNotIn(name, self.g["ALLOWED"])

	def test_read_only_and_builder_doctypes_exist(self):
		for name in [*self.g["READ_ONLY"], *self.builder]:
			with self.subTest(doctype=name):
				self.assertTrue(name in self.docs or name in STANDARD)
		self.assertEqual(set(self.g["READ_ONLY"]) & self.builder, set())

	def test_builder_doctypes_are_known_to_the_catalog_builder(self):
		schema = json.loads(
			(REPO / "tools/yaml_builder_ui/src/catalog-schema.json").read_text(encoding="utf-8")
		)
		self.assertEqual(sorted(self.builder - set(schema["doctypes"])), [])

	def test_required_child_tables_are_created_in_the_builder(self):
		for name in self.grouped:
			doc = self.docs[name]
			if any(f["fieldtype"] == "Table" and f.get("reqd") for f in doc["fields"]):
				with self.subTest(doctype=name):
					self.assertIn(name, self.builder)


if __name__ == "__main__":
	unittest.main()
