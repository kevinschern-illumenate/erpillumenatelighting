"""The built-in starter library: valid catalogs, named for renaming, and in sync with the UI."""

import json
import tempfile
import unittest
from pathlib import Path

from tools.fixture_builder.__main__ import generate_all
from tools.fixture_builder.catalog_schema import PRODUCTS
from tools.fixture_builder.catalog_starters import OUTPUT, load_starters, problems, render


class StarterLibraryTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.starters = load_starters()

	def test_library_covers_every_buildable_product_type(self):
		types = {starter["product_type"] for starter in self.starters}
		self.assertTrue({"fixture", "tape", "neon", "extrusion-kit", "driver", "controller"} <= types)
		self.assertTrue(types <= set(PRODUCTS))

	def test_every_starter_validates_and_uses_the_starter_names(self):
		self.assertEqual(problems(self.starters), [])
		for starter in self.starters:
			with self.subTest(starter=starter["id"]):
				text = json.dumps(starter["catalog"]["records"])
				self.assertEqual(starter["code"], "DEMO")
				self.assertEqual(starter["catalog"]["series_name"], "Example Series")
				self.assertIn(starter["name"], text)
				self.assertNotIn("builder", starter["catalog"], "editor settings stay out of the draft")
				template = PRODUCTS[starter["product_type"]]["template"]
				self.assertTrue(starter["catalog"]["records"].get(template), "the starter has its template")
				for row in starter["catalog"]["records"][template]:
					self.assertEqual(row.get("product_status"), "Draft", "a new product starts as a draft")
				self.assertNotIn("/files/", text, "site files are not copied into starters")

	def test_every_starter_generates_an_import_package(self):
		for starter in self.starters:
			with self.subTest(starter=starter["id"]), tempfile.TemporaryDirectory() as output:
				files = generate_all(starter["catalog"], output)
				self.assertTrue(files)
				self.assertTrue((Path(output) / "manifest.json").exists())

	def test_existing_family_starter_links_components_instead_of_creating_them(self):
		packages = next(s for s in self.starters if s["id"] == "fixture-packages")
		records = packages["catalog"]["records"]
		for doctype in ("Item", "ilL-Spec-Profile", "ilL-Spec-Lens", "ilL-Spec-Accessory"):
			self.assertNotIn(doctype, records)
		self.assertTrue(
			any("CH-DEMO" in name for name in packages["catalog"]["external_links"]["ilL-Spec-Profile"])
		)

	def test_browser_library_is_current(self):
		self.assertEqual(OUTPUT.read_text(encoding="utf-8"), render(self.starters))


if __name__ == "__main__":
	unittest.main()
