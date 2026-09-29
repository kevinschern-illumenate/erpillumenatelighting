"""Spec asset pack import: all-or-nothing validation, safe artwork, idempotent attachment."""

import hashlib
import io
import json
import types
import unittest
import zipfile
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".api.spec_sheets.asset_pack"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M0 0h10v10z"/></svg>'


def png(size=(4, 4), fmt="PNG"):
	from PIL import Image

	output = io.BytesIO()
	Image.new("RGB", size, "white").save(output, fmt, dpi=(300, 300))
	return output.getvalue()


def pack(files, targets=None, manifest=None, tamper=None):
	output = io.BytesIO()
	with zipfile.ZipFile(output, "w") as archive:
		assets = []
		for path, content in files.items():
			archive.writestr(path, (tamper or {}).get(path, content))
			assets.append(
				{
					"path": path,
					"sha256": hashlib.sha256(content).hexdigest(),
					"targets": (targets or {}).get(path)
					or [
						{
							"doctype": "ilL-Spec-Profile",
							"name": "SH01",
							"table": "spec_assets",
							"row": {"asset_role": "Cross Section", "title": "Cross Section"},
						}
					],
				}
			)
		archive.writestr(
			"assets_manifest.json",
			json.dumps(manifest or {"format": "ill-spec-asset-pack", "version": 1, "assets": assets}),
		)
	return output.getvalue()


class Doc(Record):
	def __getattr__(self, name):
		return self.get(name)

	def set(self, field, value):
		self[field] = value

	def append(self, table, row):
		self.setdefault(table, []).append(Record(row))


class AssetPackImport(unittest.TestCase):
	def run_import(self, data, dry_run=False, docs=None, existing_files=None):
		docs = docs if docs is not None else {("ilL-Spec-Profile", "SH01"): Doc(spec_assets=[])}
		existing_files = existing_files if existing_files is not None else {}
		with load_service(MODULE) as (module, frappe):
			frappe.db.exists.side_effect = lambda doctype, name: (doctype, name) in docs
			frappe.db.get_value.side_effect = lambda doctype, filters, field: existing_files.get(
				filters["file_name"]
			)
			inserted = []

			def new_doc(values, name=None):
				if isinstance(values, dict):
					file = types.SimpleNamespace(**values)
					file.file_url = "/files/" + values["file_name"]
					file.insert = lambda: inserted.append(file) or file
					return file
				doc = docs[(values, name)]
				doc.save = MagicMock()
				return doc

			frappe.get_doc.side_effect = new_doc
			report = module.import_pack(data, dry_run=dry_run)
			return report, docs, inserted

	def test_valid_pack_creates_files_and_attaches_rows_once(self):
		data = pack(
			{"assets/SH01_cross.svg": SVG, "assets/hero.png": png()},
			targets={
				"assets/hero.png": [
					{
						"doctype": "ilL-Spec-Profile",
						"name": "SH01",
						"table": "spec_assets",
						"row": {"asset_role": "Product Photo"},
					},
					{"doctype": "ilL-Attribute-Environment Rating", "name": "Wet", "field": "spec_icon"},
				]
			},
		)
		docs = {
			("ilL-Spec-Profile", "SH01"): Doc(spec_assets=[]),
			("ilL-Attribute-Environment Rating", "Wet"): Doc(),
		}
		report, docs, inserted = self.run_import(data, docs=docs)
		self.assertEqual(report["errors"], [])
		self.assertEqual((report["files_created"], report["rows_added"], report["fields_set"]), (2, 2, 1))
		rows = docs[("ilL-Spec-Profile", "SH01")].spec_assets
		self.assertEqual([row["asset_role"] for row in rows], ["Cross Section", "Product Photo"])
		self.assertTrue(all(row["file"].startswith("/files/spec-") for row in rows))
		self.assertEqual(docs[("ilL-Attribute-Environment Rating", "Wet")].spec_icon, rows[1]["file"])
		self.assertTrue(all(file.is_private == 0 for file in inserted))

		existing = {file.file_name: file.file_url for file in inserted}
		again, docs, inserted = self.run_import(data, docs=docs, existing_files=existing)
		self.assertEqual(
			(again["files_created"], again["rows_added"], again["rows_updated"], again["fields_set"]),
			(0, 0, 0, 0),
		)
		self.assertEqual(inserted, [])

	def test_changed_artwork_replaces_the_matching_row(self):
		row = Record(asset_role="Cross Section", title="Cross Section", file="/files/spec-old-cross.svg")
		docs = {("ilL-Spec-Profile", "SH01"): Doc(spec_assets=[row])}
		report, docs, _inserted = self.run_import(pack({"assets/SH01_cross.svg": SVG}), docs=docs)
		self.assertEqual((report["rows_added"], report["rows_updated"]), (0, 1))
		self.assertNotEqual(
			docs[("ilL-Spec-Profile", "SH01")].spec_assets[0]["file"], "/files/spec-old-cross.svg"
		)

	def test_dry_run_and_any_error_write_nothing(self):
		report, docs, inserted = self.run_import(pack({"assets/a.svg": SVG}), dry_run=True)
		self.assertEqual(
			(report["errors"], inserted, docs[("ilL-Spec-Profile", "SH01")].spec_assets), ([], [], [])
		)
		bad = pack({"assets/a.svg": SVG, "assets/b.svg": SVG}, tamper={"assets/b.svg": SVG + b" "})
		report, docs, inserted = self.run_import(bad)
		self.assertIn("SHA-256", " ".join(report["errors"]))
		self.assertEqual((inserted, docs[("ilL-Spec-Profile", "SH01")].spec_assets), ([], []))

	def test_unsafe_or_unprintable_artwork_is_refused(self):
		cases = {
			"script.svg": b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
			"handler.svg": b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>',
			"remote.svg": b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><image xlink:href="https://x.test/a.png"/></svg>',
			"entity.svg": b'<!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg"/>',
			"styled.svg": b'<svg xmlns="http://www.w3.org/2000/svg"><style>@import url(https://x.test/a.css);</style></svg>',
			"drawing.ai": b"%PDF-1.7",
			"fake.png": b"not a png",
		}
		for name, content in cases.items():
			with self.subTest(name=name):
				report, _docs, inserted = self.run_import(pack({f"assets/{name}": content}))
				self.assertTrue(report["errors"], name)
				self.assertEqual(inserted, [])

	def test_targets_must_be_known_artwork_homes_that_exist(self):
		for target, message in (
			({"doctype": "User", "name": "Administrator", "field": "user_image"}, "no artwork field"),
			(
				{"doctype": "ilL-Spec-Profile", "name": "SH01", "table": "items", "row": {}},
				"no artwork table",
			),
			(
				{
					"doctype": "ilL-Spec-Profile",
					"name": "SH01",
					"table": "spec_assets",
					"row": {"asset_role": "Logo"},
				},
				"asset_role",
			),
			(
				{
					"doctype": "ilL-Spec-Profile",
					"name": "SH01",
					"table": "spec_assets",
					"row": {"asset_role": "Hero", "sha256": "x"},
				},
				"unknown row fields",
			),
			(
				{
					"doctype": "ilL-Spec-Profile",
					"name": "SH99",
					"table": "spec_assets",
					"row": {"asset_role": "Hero"},
				},
				"does not exist",
			),
		):
			with self.subTest(target=target):
				report, _docs, _inserted = self.run_import(
					pack({"assets/a.svg": SVG}, targets={"assets/a.svg": [target]})
				)
				self.assertIn(message, " ".join(report["errors"]))

	def test_tiff_photos_become_png_and_fpo_artwork_is_reported(self):
		fpo = b'<svg xmlns="http://www.w3.org/2000/svg"><path fill="#ec008c" d="M0 0h1v1z"/></svg>'
		report, _docs, inserted = self.run_import(
			pack({"assets/hero.tif": png(fmt="TIFF"), "assets/fpo.svg": fpo})
		)
		self.assertEqual(report["errors"], [])
		self.assertEqual(report["converted"], ["hero.tif"])
		self.assertEqual(report["fpo_placeholders"], ["fpo.svg"])
		self.assertTrue(inserted[0].file_name.endswith("-hero.png"))
		self.assertTrue(inserted[0].content.startswith(b"\x89PNG"))

	def test_broken_packs_are_reported_as_a_whole(self):
		with load_service(MODULE) as (module, _frappe):
			for data, message in (
				(b"not a zip", "not a zip"),
				(pack({"a.svg": SVG}, manifest={"format": "other", "version": 1, "assets": []}), "version 1"),
			):
				with self.subTest(message=message), self.assertRaisesRegex(module.PackError, message):
					module.read_pack(data)


if __name__ == "__main__":
	unittest.main()
