"""Gallery list doctypes, child doctypes and seed patch (no Frappe needed)."""

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from illumenate_lighting.illumenate_lighting.api import gallery_schema as schema

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "illumenate_lighting"
DOCTYPES = APP / "illumenate_lighting" / "doctype"
NEW = {
	"ilL-Gallery-Application": "ill_gallery_application",
	"ilL-Design-Service": "ill_design_service",
	"ilL-Child-Gallery-Application": "ill_child_gallery_application",
	"ilL-Child-Gallery-Service": "ill_child_gallery_service",
	"ilL-Child-Gallery-Credit": "ill_child_gallery_credit",
	"ilL-Child-Gallery-Product": "ill_child_gallery_product",
}
# The ten new doctypes of the Global Constraints.
ALL_GALLERY_DOCTYPES = {
	**NEW,
	"ilL-Webflow-Gallery": "ill_webflow_gallery",
	"ilL-Gallery-Publication": "ill_gallery_publication",
	"ilL-Gallery-Publish-Job": "ill_gallery_publish_job",
	"ilL-Child-Gallery-Custom-Item": "ill_child_gallery_custom_item",
}


def load_doctype(folder):
	return json.loads((DOCTYPES / folder / f"{folder}.json").read_text())


class GallerySchemaTest(unittest.TestCase):
	def test_counts_match_spec(self):
		self.assertEqual(len(schema.GALLERY_TYPES), 16)
		self.assertEqual(len(schema.APPLICATIONS), 20)
		self.assertEqual(len(schema.DESIGN_SERVICES), 8)
		self.assertEqual(len(schema.CREDIT_TYPES), 6)

	def test_credit_fields_map(self):
		self.assertEqual(schema.CREDIT_FIELDS["Integrator"], ("client-integrator", "client-website"))
		self.assertEqual(schema.CREDIT_FIELDS["Photographer"], ("photo-credit", "photographer-website"))
		self.assertEqual(set(schema.CREDIT_FIELDS), set(schema.CREDIT_TYPES))

	def test_slug_re(self):
		for good in ("ode-wellness", "a1"):
			self.assertTrue(schema.SLUG_RE.fullmatch(good), good)
		for bad in ("Ode", "a b", "a_b", ""):
			self.assertFalse(schema.SLUG_RE.fullmatch(bad), bad)

	def test_doctype_json_valid(self):
		for name, folder in NEW.items():
			doc = load_doctype(folder)
			self.assertEqual(doc["name"], name)
			self.assertEqual(doc["module"], "ilLumenate Lighting")
			self.assertTrue((DOCTYPES / folder / "__init__.py").exists())
			if "Child" in name:
				self.assertEqual(doc["istable"], 1, name)
		fields = {f["fieldname"]: f for f in load_doctype("ill_child_gallery_product")["fields"]}
		self.assertEqual(fields["series"]["reqd"], 1)
		self.assertEqual(fields["series"]["options"], "ilL-Attribute-Series")
		credit = {f["fieldname"]: f for f in load_doctype("ill_child_gallery_credit")["fields"]}
		self.assertEqual(credit["credit_type"]["options"], "\n".join(schema.CREDIT_TYPES))
		kind = {f["fieldname"]: f for f in load_doctype("ill_webflow_brand_collection")["fields"]}
		self.assertIn("Galleries", kind["collection_kind"]["options"].split("\n"))

	def test_every_gallery_doctype_has_a_controller(self):
		"""Frappe imports `<folder>/<folder>.py` for every doctype; a missing one fails load and migrate."""
		for name, folder in ALL_GALLERY_DOCTYPES.items():
			with self.subTest(name):
				self.assertEqual(load_doctype(folder)["name"], name)
				self.assertTrue((DOCTYPES / folder / "__init__.py").exists())
				controller = DOCTYPES / folder / f"{folder}.py"
				self.assertTrue(controller.exists(), f"{controller} is missing")
				class_name = name.replace("-", "")
				self.assertIn(f"class {class_name}(Document)", controller.read_text())

	def test_gallery_cannot_be_renamed_and_attachments_default_public(self):
		gallery = load_doctype("ill_webflow_gallery")
		# A rename skips the slug lock and orphans the publication scope key (spec 5.1).
		self.assertEqual(gallery.get("allow_rename", 0), 0)
		self.assertEqual(gallery.get("make_attachments_public"), 1)
		sync = {f["fieldname"]: f for f in gallery["fields"]}["sync_targets"]
		self.assertNotIn("Maintained by the sync", sync.get("description") or "")

	def test_list_doctypes_autoname(self):
		app = load_doctype("ill_gallery_application")
		self.assertEqual(app["autoname"], "field:application_name")
		self.assertEqual(load_doctype("ill_design_service")["autoname"], "field:service_name")


def load_patch(frappe):
	sys.modules["frappe"] = frappe
	spec = importlib.util.spec_from_file_location(
		"seed_gallery_lists", APP / "patches" / "seed_gallery_lists.py"
	)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


class SeedPatchTest(unittest.TestCase):
	def test_seed_patch_idempotent(self):
		existing = set()
		inserted = []

		def exists(doctype, name=None):
			key = (doctype, name if isinstance(name, str) else tuple(sorted(name.items())))
			return key in existing

		def get_doc(values):
			doc = MagicMock()

			def insert(**kwargs):
				inserted.append(values)
				name = values.get("application_name") or values.get("service_name")
				if name:
					existing.add((values["doctype"], name))
				else:
					existing.add((values["doctype"], tuple(sorted({"series_name": values["series_name"]}.items()))))

			doc.insert = insert
			return doc

		frappe = types.ModuleType("frappe")
		frappe.db = types.SimpleNamespace(exists=exists)
		frappe.get_doc = get_doc
		saved = sys.modules.get("frappe")
		try:
			patch = load_patch(frappe)
			patch.execute()
			first = len(inserted)
			self.assertEqual(first, 20 + 8 + 1)
			patch.execute()
			self.assertEqual(len(inserted), first)
			custom = [v for v in inserted if v["doctype"] == "ilL-Attribute-Series"][0]
			self.assertEqual((custom["series_name"], custom["code"], custom["is_active"]), ("Custom", "CUSTOM", 1))
		finally:
			if saved is None:
				sys.modules.pop("frappe", None)
			else:
				sys.modules["frappe"] = saved


if __name__ == "__main__":
	unittest.main()
