"""One canonical product image (plan 5.4, owner decision D1)."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.product_projection import (
	choose_images,
	images_list,
	project_product,
)

# Fields each DocType really has; Fixture, Driver and Controller templates have no legacy image.
FIELDS = {
	"ilL-Fixture-Template": {"template_name", "hero_image", "webflow_product"},
	"ilL-Tape-Neon-Template": {"template_name", "hero_image", "image", "webflow_product"},
	"ilL-Extrusion-Kit-Template": {"template_name", "hero_image", "image", "webflow_product"},
	"ilL-Webflow-Product": {
		"product_name",
		"featured_image",
		"fixture_template",
		"tape_neon_template",
		"kit_template",
		"driver_template",
		"controller_template",
		"led_sheet_template",
	},
}


def database(frappe, tables):
	"""get_all/get_meta doubles: "in" filters apply and rows carry only the requested fields."""
	frappe.get_meta = lambda doctype: MagicMock(has_field=lambda field: field in FIELDS.get(doctype, ()))

	def get_all(doctype, filters=None, fields=None, **_kw):
		rows = tables.get(doctype, [])
		for key, condition in (filters or {}).items():
			if isinstance(condition, list):
				rows = [r for r in rows if r.get(key) in condition[1]]
		return [Record({key: value for key, value in row.items() if key in fields}) for row in rows]

	frappe.get_all = MagicMock(side_effect=get_all)


class Precedence(unittest.TestCase):
	gallery = ({"image": "/files/g1.jpg", "alt_text": "Gallery one"}, {"image": "/files/g2.jpg"})

	def test_each_level_wins_only_when_the_ones_above_are_empty(self):
		cases = [
			({"hero": "/h.jpg", "featured": "/f.jpg", "gallery": self.gallery, "legacy": "/l.jpg"}, "/h.jpg", "template_hero"),
			({"featured": "/f.jpg", "gallery": self.gallery, "legacy": "/l.jpg"}, "/f.jpg", "featured_image"),
			({"gallery": self.gallery, "legacy": "/l.jpg"}, "/files/g1.jpg", "gallery"),
			({"legacy": "/l.jpg"}, "/l.jpg", "template_image"),
			({}, None, None),
		]
		for kwargs, primary, source in cases:
			with self.subTest(source=source):
				images = choose_images(alt="Slim", **kwargs)
				self.assertEqual((images["primary"], images["primary_source"]), (primary, source))

	def test_gallery_holds_the_other_images_once_and_never_the_primary(self):
		images = choose_images(
			hero="/files/g2.jpg", featured="/files/g1.jpg", gallery=self.gallery, legacy="/l.jpg", alt="Slim"
		)
		self.assertEqual(
			images["gallery"],
			[{"image": "/files/g1.jpg", "alt_text": "Gallery one"}, {"image": "/l.jpg", "alt_text": "Slim"}],
		)
		self.assertEqual([i["image"] for i in images_list(images)], ["/files/g2.jpg", "/files/g1.jpg", "/l.jpg"])

	def test_alt_text_prefers_the_hero_alt_then_the_gallery_row_then_the_name(self):
		self.assertEqual(choose_images(hero="/h.jpg", hero_alt="Front", alt="Slim")["primary_alt"], "Front")
		self.assertEqual(choose_images(hero="/h.jpg", alt="Slim")["primary_alt"], "Slim")
		self.assertEqual(choose_images(gallery=self.gallery, alt="Slim")["primary_alt"], "Gallery one")
		self.assertEqual(images_list(None), [])
		self.assertEqual(images_list(choose_images()), [])


class Resolver(unittest.TestCase):
	def tables(self):
		return {
			"ilL-Fixture-Template": [
				Record(name="F-HERO", template_name="Hero Fixture", hero_image="/hero.jpg", webflow_product="p-hero"),
				Record(name="F-GAL", template_name="Gallery Fixture", hero_image=None, webflow_product="p-gal"),
				Record(name="F-NONE", template_name="Bare Fixture", hero_image=None, webflow_product=None),
			],
			"ilL-Tape-Neon-Template": [
				Record(name="T-OLD", template_name="Old Tape", hero_image=None, image="/legacy.jpg", webflow_product=None),
			],
			"ilL-Extrusion-Kit-Template": [
				Record(name="K1", template_name="Kit", hero_image="/kit-hero.jpg", image="/kit.jpg", webflow_product="p-kit"),
			],
			"ilL-Webflow-Product": [
				Record(name="p-hero", product_name="Hero", featured_image="/featured.jpg", fixture_template="F-HERO"),
				Record(name="p-gal", product_name="Gal", featured_image=None, fixture_template="F-GAL"),
				# A product linking a kit and a fixture reads the kit first, like set_dynamic_hero_image.
				Record(name="p-kit", product_name="Kit", featured_image=None, kit_template="K1", fixture_template="F-HERO"),
				Record(name="p-old", product_name="Old", featured_image=None, tape_neon_template="T-OLD"),
			],
			"ilL-Child-Webflow-Gallery-Image": [
				Record(parent="p-hero", image="/featured.jpg", alt_text="Front", idx=1),
				Record(parent="p-hero", image="/side.jpg", alt_text="Side", idx=2),
				Record(parent="p-gal", image="/g1.jpg", alt_text="One", idx=1),
				Record(parent="p-gal", image=None, alt_text="Empty row", idx=2),
			],
		}

	def test_templates_follow_d1_and_only_read_fields_the_doctype_has(self):
		with load_service(ROOT + ".api.product_projection") as (service, frappe):
			database(frappe, self.tables())
			fixtures = service.resolve_product_images("ilL-Fixture-Template", ["F-HERO", "F-GAL", "F-NONE", "GONE", None, "F-HERO"])
			tape = service.resolve_product_images("ilL-Tape-Neon-Template", ["T-OLD"])
			fixture_fields = frappe.get_all.call_args_list[0].kwargs["fields"]
		self.assertNotIn("image", fixture_fields)
		self.assertEqual(set(fixtures), {"F-HERO", "F-GAL", "F-NONE"})
		self.assertEqual(fixtures["F-HERO"]["primary"], "/hero.jpg")
		self.assertEqual(fixtures["F-HERO"]["primary_alt"], "Hero Fixture")
		self.assertEqual([g["image"] for g in fixtures["F-HERO"]["gallery"]], ["/featured.jpg", "/side.jpg"])
		self.assertEqual((fixtures["F-GAL"]["primary"], fixtures["F-GAL"]["primary_source"]), ("/g1.jpg", "gallery"))
		self.assertEqual(fixtures["F-GAL"]["gallery"], [])
		self.assertEqual(fixtures["F-NONE"]["primary"], None)
		self.assertEqual((tape["T-OLD"]["primary"], tape["T-OLD"]["primary_source"]), ("/legacy.jpg", "template_image"))

	def test_products_take_the_linked_template_hero(self):
		with load_service(ROOT + ".api.product_projection") as (service, frappe):
			database(frappe, self.tables())
			products = service.resolve_product_images("ilL-Webflow-Product", ["p-hero", "p-gal", "p-kit", "p-old"])
			self.assertEqual(service.resolve_product_images("ilL-Webflow-Product", []), {})
		self.assertEqual(products["p-hero"]["primary"], "/hero.jpg")
		self.assertEqual(products["p-gal"]["primary"], "/g1.jpg")
		self.assertEqual(products["p-kit"]["primary"], "/kit-hero.jpg")
		self.assertEqual([g["image"] for g in products["p-kit"]["gallery"]], ["/kit.jpg"])
		self.assertEqual(products["p-old"]["primary"], "/legacy.jpg")

	def test_resolving_never_writes(self):
		with load_service(ROOT + ".api.product_projection") as (service, frappe):
			database(frappe, self.tables())
			service.resolve_product_images("ilL-Fixture-Template", ["F-GAL"])
			service.resolve_product_images("ilL-Webflow-Product", ["p-gal"])
		frappe.db.set_value.assert_not_called()
		frappe.get_doc.assert_not_called()

	def test_pickers_get_the_resolved_image_first_in_their_gallery(self):
		import json

		with load_service("illumenate_lighting.templates.pages.configure") as (page, frappe):
			database(frappe, self.tables())
			templates = page.attach_images(
				"ilL-Fixture-Template", [Record(name="F-HERO"), Record(name="F-NONE"), Record(name="GONE")]
			)
		hero, bare, gone = templates
		self.assertEqual((hero.image, hero.image_alt), ("/hero.jpg", "Hero Fixture"))
		self.assertEqual([g["image"] for g in json.loads(hero.gallery_json)], ["/hero.jpg", "/featured.jpg", "/side.jpg"])
		self.assertEqual(hero.gallery, json.loads(hero.gallery_json))
		for template in (bare, gone):
			self.assertEqual((template.image, template.gallery_json, template.gallery), (None, "[]", []))


class Projection(unittest.TestCase):
	product = {
		"name": "p",
		"product_name": "Slim",
		"product_type": "Fixture Template",
		"is_active": 1,
		"featured_image": "/featured.jpg",
		"hero_image": "/hero.jpg",
		"gallery_images": [{"image": "/b.jpg", "display_order": 2}, {"image": "/a.jpg", "display_order": 1}],
	}

	def test_without_resolved_images_the_product_hero_copy_leads(self):
		result = project_product(self.product)
		self.assertEqual((result["image"], result["image_source"], result["image_alt"]), ("/hero.jpg", "template_hero", "Slim"))
		self.assertEqual([g["image"] for g in result["gallery"]], ["/hero.jpg", "/a.jpg", "/b.jpg", "/featured.jpg"])
		self.assertEqual([g["display_order"] for g in result["gallery"]], [0, 1, 2, 3])
		self.assertEqual(result["featured_image"], "/featured.jpg")

	def test_resolved_images_are_used_as_given(self):
		images = choose_images(hero="/live-hero.jpg", hero_alt="Live", alt="Slim")
		result = project_product(self.product, images=images)
		self.assertEqual((result["image"], result["image_alt"]), ("/live-hero.jpg", "Live"))
		self.assertEqual(result["gallery"], [{"image": "/live-hero.jpg", "alt_text": "Live", "display_order": 0}])

	def test_a_product_with_no_images_has_an_empty_gallery(self):
		result = project_product({"name": "p", "product_type": "Fixture Template"})
		self.assertEqual((result["image"], result["gallery"]), (None, []))


if __name__ == "__main__":
	unittest.main()
