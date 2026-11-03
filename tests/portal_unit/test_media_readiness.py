"""Media readiness warnings (plan 5.1): reported, never blocking."""

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".api.product_readiness"


def product(**values):
	row = Record(
		name="P",
		product_type="Fixture Template",
		fixture_template="F-1",
		dimensions_image="/files/dim.png",
		gallery_images=[],
	)
	row.update(values)
	return row


class MediaWarnings(unittest.TestCase):
	def warnings(self, item, hero="/files/hero.jpg", files=None):
		with load_service(MODULE) as (readiness, frappe):
			migration = types.ModuleType(ROOT + ".web_listing_migration")
			migration.template_link = lambda listing: (
				("ilL-Fixture-Template", listing.get("fixture_template")) if listing.get("fixture_template") else (None, None)
			)
			frappe.db.get_value = MagicMock(
				side_effect=lambda doctype, name, field: hero if doctype == "ilL-Fixture-Template" else (files or {}).get(name["file_url"])
			)
			frappe.get_doc = MagicMock(side_effect=lambda _doctype, name: Record(get_full_path=lambda: name))
			with patch.dict(sys.modules, {migration.__name__: migration}):
				return {(row["field"], row["message"]) for row in readiness.media_warnings(item)}

	def test_complete_media_has_no_warnings(self):
		self.assertEqual(self.warnings(product(gallery_images=[Record(idx=1, image="/files/a.jpg", alt_text="Slim profile")])), set())

	def test_missing_or_unusable_template_hero_is_a_warning(self):
		self.assertIn("hero_image", {f for f, _ in self.warnings(product(), hero=None)})
		self.assertIn(("hero_image", "Use a public image for the hero image"), self.warnings(product(), hero="/private/files/h.jpg"))
		self.assertIn(
			("hero_image", "Use a JPEG, PNG or WebP hero image instead of TIFF/BMP"),
			self.warnings(product(), hero="/files/hero.TIFF"),
		)

	def test_narrow_hero_image_is_a_warning(self):
		from PIL import Image

		with tempfile.TemporaryDirectory() as folder:
			small, large = Path(folder, "small.png"), Path(folder, "large.png")
			Image.new("RGB", (800, 10)).save(small)
			Image.new("RGB", (1600, 10)).save(large)
			files = {"/files/small.png": str(small), "/files/large.png": str(large)}
			self.assertIn(
				("hero_image", "Hero image is 800 px wide; use at least 1200 px"),
				self.warnings(product(), hero="/files/small.png", files=files),
			)
			self.assertEqual(self.warnings(product(), hero="/files/large.png", files=files), set())

	def test_gallery_rows_need_alt_text_and_public_urls(self):
		found = self.warnings(product(gallery_images=[Record(idx=2, image="/private/files/a.jpg", alt_text=" ")]))
		self.assertEqual(
			found,
			{
				("gallery_images row 2", "Use a public image for gallery images"),
				("gallery_images row 2", "Add alt text to this gallery image"),
			},
		)

	def test_dimensions_image_only_expected_for_linear_families(self):
		self.assertIn(("dimensions_image", "Add a dimensions image for this linear product"), self.warnings(product(dimensions_image=None)))
		self.assertEqual(self.warnings(product(product_type="Driver", fixture_template=None, dimensions_image=None)), set())


if __name__ == "__main__":
	unittest.main()
