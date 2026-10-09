"""Webflow Product content copied onto templates (Webflow Product merge, step 3)."""

import unittest

from test_services import ROOT, load_service

FIXTURE = "ilL-Fixture-Template"
TAPE = "ilL-Tape-Neon-Template"
DRIVER = "ilL-Driver-Template"


def call(name, *args, **kwargs):
	with load_service(ROOT + ".web_listing_migration") as (module, _frappe):
		return getattr(module, name)(*args, **kwargs)


def listing(**values):
	return {
		"name": "ill-el01-sw",
		"product_name": "Elevate [SW]",
		"is_active": 1,
		"fixture_template": "ILL-EL01-SW",
		"product_category": "linear",
		"short_description": "Surface linear",
		"features": '["Dimmable"]',
		"min_length_mm": 300,
		"gallery_images": [
			{"name": "row1", "parent": "ill-el01-sw", "idx": 1, "image": "/files/a.jpg", "alt_text": "A"}
		],
		"compatible_products": [{"related_product": "ill-drv-01", "relationship_type": "Works With"}],
		"certifications": [{"certification": "UL"}, {"certification": "ETL"}],
		**values,
	}


def template(**values):
	return {"name": "ILL-EL01-SW", "template_name": "Elevate SW", "webflow_product": None, **values}


class PlanListing(unittest.TestCase):
	def test_copies_listing_into_empty_web_fields(self):
		values, tables, notes = call("plan_listing", listing(), template(), FIXTURE)
		self.assertEqual(
			values,
			{
				"web_slug": "ill-el01-sw",
				"web_listed": 1,
				"web_title": "Elevate [SW]",
				"web_category": "linear",
				"short_description": "Surface linear",
				"features": '["Dimmable"]',
				"min_length_mm": 300,
			},
		)
		self.assertEqual(tables["gallery_images"], [{"image": "/files/a.jpg", "alt_text": "A"}])
		self.assertEqual(tables["compatible_products"][0]["related_product"], "ill-drv-01")
		self.assertEqual(tables["certifications"], [{"certification": "ETL"}, {"certification": "UL"}])
		self.assertEqual(notes, [])

	def test_never_overwrites_a_template_value(self):
		values, tables, notes = call(
			"plan_listing",
			listing(),
			template(short_description="Kept", gallery_images=[{"image": "/files/b.jpg"}]),
			FIXTURE,
		)
		self.assertNotIn("short_description", values)
		self.assertNotIn("gallery_images", tables)
		self.assertTrue(any(note.startswith("short_description kept") for note in notes))
		self.assertTrue(any(note.startswith("gallery_images kept") for note in notes))

	def test_preexisting_fields_are_left_alone(self):
		values, tables, notes = call(
			"plan_listing",
			listing(fixture_template=None, tape_neon_template="NEON-UCH", warranty_years=5),
			template(warranty_years=3, certifications=[{"certification": "UL"}]),
			TAPE,
		)
		self.assertNotIn("warranty_years", values)
		self.assertNotIn("certifications", tables)
		self.assertIn("certifications kept; listing also has ETL", notes)

	def test_fields_the_template_type_lacks_are_reported(self):
		values, _tables, notes = call("plan_listing", listing(), template(), DRIVER)
		self.assertNotIn("min_length_mm", values)
		self.assertIn("min_length_mm not carried: ilL-Driver-Template has no such field", notes)

	def test_web_listed_can_be_forced_off(self):
		values, _tables, _notes = call("plan_listing", listing(), template(), FIXTURE, web_listed=0)
		self.assertEqual(values["web_listed"], 0)

	def test_title_matching_the_template_is_not_copied(self):
		values, _tables, _notes = call(
			"plan_listing", listing(product_name="Elevate SW"), template(), FIXTURE
		)
		self.assertNotIn("web_title", values)

	def test_backlink_to_another_listing_is_reported(self):
		_values, _tables, notes = call(
			"plan_listing", listing(), template(webflow_product="ill-el01-fs"), FIXTURE
		)
		self.assertIn("template's Webflow Product backlink points at ill-el01-fs", notes)


class Parity(unittest.TestCase):
	def test_migrated_template_matches_its_listing(self):
		source = listing()
		values, tables, _notes = call("plan_listing", source, template(), FIXTURE)
		migrated = {**template(), **values, **tables}
		self.assertEqual(call("parity_differences", source, migrated, FIXTURE), [])

	def test_kept_template_value_is_a_difference(self):
		source = listing()
		values, tables, _notes = call("plan_listing", source, template(short_description="Kept"), FIXTURE)
		migrated = {**template(short_description="Kept"), **values, **tables}
		self.assertEqual(call("parity_differences", source, migrated, FIXTURE), ["short_description"])


class TemplateLink(unittest.TestCase):
	def test_finds_the_one_link_set(self):
		self.assertEqual(
			call("template_link", {"kit_template": "KIT-CA01"}), ("ilL-Extrusion-Kit-Template", "KIT-CA01")
		)
		self.assertEqual(call("template_link", {"fixture_template": None}), (None, None))


if __name__ == "__main__":
	unittest.main()
