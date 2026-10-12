"""Product data copied from Webflow Products onto their templates (Webflow Product merge)."""

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
		"short_description": "Surface linear",
		"min_length_mm": 300,
		"beam_angle": 120,
		"feed_lengths": [
			{"name": "row1", "parent": "ill-el01-sw", "idx": 1, "step": 9, "label": "6 ft", "code": "06"}
		],
		"gallery_images": [{"image": "/files/a.jpg"}],
		**values,
	}


def template(**values):
	return {"name": "ILL-EL01-SW", "template_name": "Elevate SW", "webflow_product": None, **values}


class PlanListing(unittest.TestCase):
	def test_copies_product_data_and_sets_the_backlink(self):
		values, tables, notes = call("plan_listing", listing(), template(), FIXTURE)
		self.assertEqual(values, {"webflow_product": "ill-el01-sw", "min_length_mm": 300, "beam_angle": 120})
		self.assertEqual(tables, {"feed_lengths": [{"step": 9, "label": "6 ft", "code": "06"}]})
		self.assertEqual(notes, [])

	def test_marketing_content_stays_on_the_webflow_product(self):
		values, tables, _notes = call("plan_listing", listing(), template(), FIXTURE)
		self.assertNotIn("short_description", values)
		self.assertNotIn("gallery_images", tables)

	def test_never_overwrites_a_template_value(self):
		values, tables, notes = call(
			"plan_listing",
			listing(),
			template(min_length_mm=200, feed_lengths=[{"step": 9, "label": "8 ft", "code": "08"}]),
			FIXTURE,
		)
		self.assertNotIn("min_length_mm", values)
		self.assertNotIn("feed_lengths", tables)
		self.assertIn("min_length_mm kept as 200; listing has 300", notes)
		self.assertTrue(any(note.startswith("feed_lengths kept") for note in notes))

	def test_preexisting_fields_are_left_alone(self):
		values, _tables, notes = call(
			"plan_listing",
			listing(fixture_template=None, tape_neon_template="NEON-UCH", warranty_years=5),
			template(warranty_years=3),
			TAPE,
		)
		self.assertNotIn("warranty_years", values)
		self.assertIn("warranty_years kept as 3; listing has 5", notes)

	def test_fields_the_template_type_lacks_are_reported(self):
		values, _tables, notes = call("plan_listing", listing(), template(), DRIVER)
		self.assertNotIn("min_length_mm", values)
		self.assertIn("min_length_mm not carried: ilL-Driver-Template has no such field", notes)

	def test_backlink_to_another_listing_is_reported(self):
		values, _tables, notes = call(
			"plan_listing", listing(), template(webflow_product="ill-el01-fs"), FIXTURE
		)
		self.assertNotIn("webflow_product", values)
		self.assertIn("template's Webflow Product backlink points at ill-el01-fs", notes)


class Carried(unittest.TestCase):
	def test_each_template_type_holds_its_own_product_data(self):
		self.assertEqual(call("carried", DRIVER), ["warranty_years"])
		self.assertIn("feed_lengths", call("carried", FIXTURE))
		self.assertIn("warranty_years", call("carried", TAPE))  # its own, older field


class Parity(unittest.TestCase):
	def test_migrated_template_matches_its_listing(self):
		source = listing()
		values, tables, _notes = call("plan_listing", source, template(), FIXTURE)
		migrated = {**template(), **values, **tables}
		self.assertEqual(call("parity_differences", source, migrated, FIXTURE), [])

	def test_kept_template_value_is_a_difference(self):
		source = listing()
		values, tables, _notes = call("plan_listing", source, template(min_length_mm=200), FIXTURE)
		migrated = {**template(min_length_mm=200), **values, **tables}
		self.assertEqual(call("parity_differences", source, migrated, FIXTURE), ["min_length_mm"])


class TemplateLink(unittest.TestCase):
	def test_finds_the_one_link_set(self):
		self.assertEqual(
			call("template_link", {"kit_template": "KIT-CA01"}), ("ilL-Extrusion-Kit-Template", "KIT-CA01")
		)
		self.assertEqual(call("template_link", {"fixture_template": None}), (None, None))

	def test_a_template_holds_the_data_once_its_backlink_points_back(self):
		with load_service(ROOT + ".web_listing_migration") as (module, frappe):
			frappe.db.get_value.side_effect = [{"fixture_template": "ILL-EL01-SW"}, "ill-el01-sw"]
			self.assertEqual(module.template_for("ill-el01-sw"), (FIXTURE, "ILL-EL01-SW"))
			frappe.db.get_value.side_effect = [{"fixture_template": "ILL-EL01-SW"}, None]
			self.assertEqual(module.template_for("ill-el01-sw"), (None, None))


class Write(unittest.TestCase):
	def test_tables_only_top_up_skips_the_scalar_update(self):
		with load_service(ROOT + ".web_listing_migration") as (module, frappe):
			module._write(FIXTURE, "ILL-EL01-SW", {}, {"feed_lengths": [{"code": "06"}]})
			frappe.db.set_value.assert_not_called()
			frappe.get_doc.assert_called_once()
			self.assertEqual(frappe.get_doc.call_args[0][0]["doctype"], "ilL-Child-Webflow-Feed-Length")


if __name__ == "__main__":
	unittest.main()
