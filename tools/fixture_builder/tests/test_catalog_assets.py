"""Local spec artwork in version 2 catalogs becomes an asset pack, never a CSV path."""

import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.fixture_builder.__main__ import generate_all
from tools.fixture_builder.catalog_examples import example_catalog

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M0 0h10v10z"/></svg>'


class CatalogAssetPack(unittest.TestCase):
	def setUp(self):
		self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
		(self.folder / "assets").mkdir()
		(self.folder / "assets" / "cross.svg").write_bytes(SVG)
		self.output = self.folder / "out"

	def catalog(self, *rows):
		config = example_catalog("fixture")
		config["records"]["ilL-Spec-Profile"][0]["spec_assets"] = list(rows)
		return config

	def test_local_artwork_moves_to_the_pack_and_uploaded_files_stay_in_the_csv(self):
		config = self.catalog(
			{"asset_role": "Cross Section", "title": "Cross Section", "file": "assets/cross.svg"},
			{"asset_role": "Product Photo", "file": "/files/already-uploaded.png"},
		)
		files = generate_all(config, self.output, asset_root=self.folder)
		self.assertIn("assets.zip", files)
		manifest = json.loads((self.output / "manifest.json").read_text())
		self.assertEqual(manifest["asset_pack"], {"file": "assets.zip", "assets": 1, "targets": 1})
		self.assertNotIn("assets.zip", [row["file"] for row in manifest["imports"]])
		with zipfile.ZipFile(files["assets.zip"]) as archive:
			pack = json.loads(archive.read("assets_manifest.json"))
			self.assertEqual(archive.read("assets/cross.svg"), SVG)
		(asset,) = pack["assets"]
		self.assertEqual(asset["path"], "assets/cross.svg")
		(target,) = asset["targets"]
		self.assertEqual(
			(target["doctype"], target["name"], target["table"]),
			("ilL-Spec-Profile", "CH-DEMO-WH", "spec_assets"),
		)
		self.assertEqual(target["row"]["asset_role"], "Cross Section")
		self.assertNotIn("file", target["row"])
		profile_csv = next(path for name, path in files.items() if name.endswith("ilL-Spec-Profile.csv"))
		text = Path(profile_csv).read_text(encoding="utf-8-sig")
		self.assertIn("/files/already-uploaded.png", text)
		self.assertNotIn("assets/cross.svg", text)
		self.assertIn("assets.zip", (self.output / "IMPORT.md").read_text())

	def test_same_output_twice_is_byte_identical(self):
		config = self.catalog({"asset_role": "Cross Section", "file": "assets/cross.svg"})
		first = Path(generate_all(config, self.output, asset_root=self.folder)["assets.zip"]).read_bytes()
		config = self.catalog({"asset_role": "Cross Section", "file": "assets/cross.svg"})
		second = Path(generate_all(config, self.output, asset_root=self.folder)["assets.zip"]).read_bytes()
		self.assertEqual(first, second)

	def test_catalogs_without_local_artwork_write_no_pack(self):
		files = generate_all(example_catalog("fixture"), self.output)
		self.assertNotIn("assets.zip", files)
		self.assertNotIn("asset_pack", json.loads((self.output / "manifest.json").read_text()))

	def test_bad_artwork_fails_before_any_file_is_written(self):
		(self.folder / "assets" / "clip.ai").write_bytes(b"%PDF-1.7")
		(self.folder / "assets" / "script.svg").write_bytes(
			b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
		)
		for value, message in (
			("assets/missing.svg", "does not exist"),
			("../outside.svg", "outside the catalog folder"),
			("assets/clip.ai", "must be SVG"),
			("assets/script.svg", "contains <script>"),
		):
			with self.subTest(value=value):
				config = self.catalog({"asset_role": "Cross Section", "file": value})
				with self.assertRaisesRegex(ValueError, message):
					generate_all(config, self.output, asset_root=self.folder)
				self.assertFalse(self.output.exists())
		with self.assertRaisesRegex(ValueError, "catalog file's folder"):
			generate_all(self.catalog({"asset_role": "Hero", "file": "assets/cross.svg"}), self.output)


if __name__ == "__main__":
	unittest.main()
