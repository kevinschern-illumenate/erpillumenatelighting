"""The /portal/configure product-type cards: photos, destinations, and which cards show."""

import importlib.util
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

ART = "/assets/illumenate_lighting/product_finder/options/finish-silver.webp"
ALIASES = {"Fixture Template": "Linear Fixture"}


def option(value, label=None, **extra):
	href = (
		"/portal/products?type=Accessory%2CComponent"
		if extra.get("routesTo")
		else "/portal/configure?category=" + value
	)
	return {"value": value, "label": label or value, "href": href, **extra}


def listing(name, product_type, configurable=1, linked=1):
	return Record(
		name=name,
		product_name=name.title(),
		product_type=product_type,
		is_configurable=configurable,
		linked=linked,
	)


class Chooser(unittest.TestCase):
	def run_cards(
		self,
		options,
		*,
		listings=(),
		images=None,
		items=(),
		templates=1,
		blocked=(),
		pricing=True,
		query=None,
	):
		images = images or {}
		extras = {
			ROOT + ".api.configuration_contract": types.SimpleNamespace(FAMILY_ALIASES=ALIASES),
			ROOT + ".portal.rollout": types.SimpleNamespace(available=lambda family: family not in blocked),
			ROOT + ".portal_listing": types.SimpleNamespace(
				LINK_FIELDS={"fixture_template": "ilL-Fixture-Template"},
				portal_condition=lambda: "1=1",
				template_filters=lambda: {"product_status": ["in", ["Active"]]},
			),
			ROOT + ".api.product_projection": types.SimpleNamespace(
				resolve_product_images=lambda doctype, names: {
					n: {"primary": images[n], "primary_alt": n + " photo"} for n in names if n in images
				},
				safe_document_url=lambda url: (
					url if url and (url.startswith("/files/") or url.startswith("https://")) else None
				),
			),
		}
		with load_service(ROOT + ".portal.product_chooser", extras) as (module, frappe):
			frappe.db.sql.return_value = list(listings)
			frappe.db.count.return_value = templates
			frappe.get_all.return_value = [Record(row) for row in items]
			return module.cards(options, query or {}, pricing), frappe

	def test_bundled_art_gives_way_to_a_product_photo_from_the_family(self):
		cards, _ = self.run_cards(
			[option("Extrusion Kit", image=ART)],
			listings=[listing("kit-a", "Extrusion Kit")],
			images={"kit-a": "/files/kit-a.png"},
		)
		self.assertEqual(cards[0]["image"], "/files/kit-a.png")
		self.assertEqual(cards[0]["image_alt"], "kit-a photo")

	def test_an_image_staff_uploaded_to_the_option_wins(self):
		cards, _ = self.run_cards(
			[option("Extrusion Kit", image="/files/chosen.jpg")],
			listings=[listing("kit-a", "Extrusion Kit")],
			images={"kit-a": "/files/kit-a.png"},
		)
		self.assertEqual(cards[0]["image"], "/files/chosen.jpg")

	def test_linear_fixture_photo_comes_from_fixture_template_listings(self):
		cards, _ = self.run_cards(
			[option("Linear Fixture")],
			listings=[listing("ra01", "Fixture Template")],
			images={"ra01": "/files/RA01_LIT.jpg"},
		)
		self.assertEqual(cards[0]["image"], "/files/RA01_LIT.jpg")

	def test_still_local_photos_of_configurable_products_are_preferred(self):
		cards, _ = self.run_cards(
			[option("LED Neon")],
			listings=[
				listing("a", "LED Neon"),
				listing("b", "LED Neon"),
				listing("c", "LED Neon", configurable=0),
				listing("d", "LED Neon"),
			],
			images={
				"a": "/files/A_Hero_Animated_Final.webp",
				"b": "https://cdn.example.com/b.jpg",
				"c": "/files/c.jpg",
				"d": "/files/d.jpg",
			},
		)
		self.assertEqual(cards[0]["image"], "/files/d.jpg")

	def test_our_own_products_are_preferred_over_standalone_listings(self):
		cards, frappe = self.run_cards(
			[option("Controller")],
			listings=[listing("advatek", "Controller", 0, linked=0), listing("dmx", "Controller", 0)],
			images={"advatek": "/files/advatek.jpg", "dmx": "/files/dmx.png"},
		)
		self.assertEqual(cards[0]["image"], "/files/dmx.png")
		self.assertIn("ifnull(fixture_template, '') != ''", frappe.db.sql.call_args.args[0])

	def test_item_photos_stand_in_when_no_listing_has_one(self):
		cards, frappe = self.run_cards(
			[option("Driver")],
			listings=[listing("ps", "Driver")],
			items=[{"item_group": "Power Supplies", "item_name": "Flora Power", "image": "/files/flora.png"}],
		)
		self.assertEqual(cards[0]["image"], "/files/flora.png")
		self.assertEqual(cards[0]["image_alt"], "Flora Power")
		self.assertIn("Power Supplies", frappe.get_all.call_args.kwargs["filters"]["item_group"][1])

	def test_family_with_nothing_to_configure_leads_to_its_catalog_listings(self):
		cards, _ = self.run_cards(
			[option("Controller")],
			listings=[listing("dmx", "Controller", configurable=0)],
			query={"schedule": "S-1"},
		)
		self.assertEqual(cards[0]["href"], "/portal/products?schedule=S-1&type=Controller")
		self.assertEqual(cards[0]["badge"], "Browse catalog")
		self.assertEqual(cards[0]["routesTo"], "catalog")

	def test_family_with_nothing_to_configure_or_list_is_left_out(self):
		cards, _ = self.run_cards([option("Driver"), option("LED Tape")], templates=0)
		self.assertEqual([c["value"] for c in cards], ["LED Tape"])

	def test_schedule_editors_never_get_a_catalog_card(self):
		cards, _ = self.run_cards(
			[option("Controller"), option("accessories", routesTo="catalog"), option("LED Tape")],
			listings=[listing("dmx", "Controller", configurable=0), listing("clip", "Accessory")],
			pricing=False,
		)
		self.assertEqual([c["value"] for c in cards], ["LED Tape"])

	def test_catalog_card_shows_only_when_the_catalog_has_listings(self):
		empty, _ = self.run_cards([option("accessories", routesTo="catalog")])
		stocked, _ = self.run_cards(
			[option("accessories", routesTo="catalog")],
			listings=[listing("clip", "Accessory")],
			images={"clip": "/files/clip.jpg"},
		)
		self.assertEqual(empty, [])
		self.assertEqual(stocked[0]["image"], "/files/clip.jpg")

	def test_families_not_rolled_out_to_the_user_are_left_out(self):
		cards, _ = self.run_cards([option("LED Sheet"), option("LED Neon")], blocked=("LED Sheet",))
		self.assertEqual([c["value"] for c in cards], ["LED Neon"])

	def test_swatch_must_be_a_plain_css_colour(self):
		cards, _ = self.run_cards(
			[
				option("LED Tape", color="#fff6e0"),
				option("LED Neon", color="linear-gradient(135deg, #ff4081 0%, #40c4ff 100%)"),
				option("COB Tape", color="red; background-image: url(x)"),
			]
		)
		self.assertEqual(
			[c["swatch"] for c in cards], ["#fff6e0", "linear-gradient(135deg, #ff4081 0%, #40c4ff 100%)", ""]
		)
		self.assertTrue(all(c["image"] is None for c in cards))


class CobTapeFinderOption(unittest.TestCase):
	def load(self):
		import sys

		stub = types.ModuleType("frappe")
		content = types.SimpleNamespace(QUESTION="ilL-Finder-Question")
		modules = {"frappe": stub, ROOT + ".portal.product_finder.content": content}
		saved = {k: sys.modules.get(k) for k in modules}
		sys.modules.update(modules)
		try:
			spec = importlib.util.spec_from_file_location(
				"cob_patch", "illumenate_lighting/patches/add_cob_tape_finder_option.py"
			)
			module = importlib.util.module_from_spec(spec)
			spec.loader.exec_module(module)
		finally:
			for k, v in saved.items():
				if v is None:
					sys.modules.pop(k, None)
				else:
					sys.modules[k] = v
		return module

	def doc(self, values):
		rows = [Record(value=v, idx=i) for i, v in enumerate(values, start=1)]
		doc = MagicMock()
		doc.get.side_effect = lambda key: rows if key == "options" else None

		def append(key, value):
			row = Record(value)
			rows.append(row)
			return row

		def set_rows(key, value):
			rows[:] = value

		doc.append.side_effect = append
		doc.set.side_effect = set_rows
		return doc, rows

	def test_seed_option_is_the_shipped_cob_tape_row(self):
		row = self.load().seed_option()
		self.assertEqual(row["value"], "COB Tape")
		self.assertTrue(row["description"])

	def test_adds_cob_tape_after_led_tape(self):
		module = self.load()
		doc, rows = self.doc(["Linear Fixture", "LED Tape", "LED Neon"])
		self.assertTrue(module.add_option(doc, {"value": "COB Tape", "label": "COB Tape"}))
		self.assertEqual([r["value"] for r in rows], ["Linear Fixture", "LED Tape", "COB Tape", "LED Neon"])
		self.assertEqual([r.idx for r in rows], [1, 2, 3, 4])

	def test_existing_row_is_left_alone(self):
		module = self.load()
		doc, _rows = self.doc(["LED Tape", "COB Tape"])
		self.assertFalse(module.add_option(doc, {"value": "COB Tape"}))
		doc.append.assert_not_called()


if __name__ == "__main__":
	unittest.main()
