"""Readers take a migrated listing's web content from its template (Webflow Product merge, step 4)."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, load_service

PRODUCT = "ilL-Webflow-Product"
FIXTURE = "ilL-Fixture-Template"


class Row(dict):
	def __getattr__(self, key):
		return self.get(key)

	def as_dict(self):
		return dict(self)


class Doc(Row):
	def __init__(self, before=None, **values):
		super().__init__(values)
		self.before = before

	def get(self, key, default=None):
		value = super().get(key, default)
		return [Row(row) for row in value] if isinstance(value, list) else value

	def as_dict(self):
		return {key: self.get(key) for key in self}

	def get_doc_before_save(self):
		return self.before


def product(**values):
	return Doc(
		**{
			"name": "ill-el01-sw",
			"product_name": "Elevate [SW]",
			"product_type": "Linear Fixture",
			"is_active": 1,
			"fixture_template": "ILL-EL01-SW",
			"product_category": "linear",
			"short_description": "Old copy",
			"gallery_images": [{"image": "/files/old.jpg"}],
			"attribute_links": [{"attribute_name": "3000K"}],
			**values,
		}
	)


def template(**values):
	return Doc(
		**{
			"name": "ILL-EL01-SW",
			"template_name": "Elevate SW",
			"web_slug": "ill-el01-sw",
			"web_title": "Elevate [SW]",
			"web_category": "linear",
			"short_description": "Template copy",
			"gallery_images": [{"image": "/files/new.jpg"}],
			"attribute_links": [],
			**values,
		}
	)


def listing(source, migrated=True, **template_values):
	with load_service(ROOT + ".web_listing_source") as (module, frappe):
		module.listing_for = MagicMock(
			return_value=(FIXTURE, "ILL-EL01-SW") if migrated else (PRODUCT, source.name)
		)
		frappe.get_doc.return_value = template(**template_values)
		return module.Listing(source)


class Reading(unittest.TestCase):
	def test_migrated_listing_reads_web_content_from_the_template(self):
		view = listing(product())
		self.assertEqual(view.get("short_description"), "Template copy")
		self.assertEqual(view.gallery_images[0].image, "/files/new.jpg")

	def test_identity_and_computed_tables_stay_on_the_webflow_product(self):
		view = listing(product())
		self.assertEqual(view.product_type, "Linear Fixture")
		self.assertEqual(view.fixture_template, "ILL-EL01-SW")
		self.assertEqual(view.attribute_links[0].attribute_name, "3000K")
		self.assertEqual(view.source.name, "ill-el01-sw")

	def test_title_falls_back_to_the_template_name(self):
		self.assertEqual(listing(product(), web_title=None).product_name, "Elevate SW")

	def test_unmigrated_listing_reads_the_webflow_product(self):
		view = listing(product(), migrated=False)
		self.assertEqual(view.short_description, "Old copy")
		self.assertEqual(view.as_dict()["gallery_images"], [{"image": "/files/old.jpg"}])

	def test_legacy_read_switch_sends_readers_back_to_the_webflow_product(self):
		with load_service(ROOT + ".web_listing_source") as (module, frappe):
			module.listing_for = MagicMock(return_value=(FIXTURE, "ILL-EL01-SW"))
			frappe.conf["web_listing_legacy_read"] = 1
			view = module.Listing(product())
		self.assertIsNone(view.template)
		self.assertEqual(view.short_description, "Old copy")

	def test_overlay_replaces_only_the_fields_present(self):
		data = listing(product()).overlay(
			{"name": "ill-el01-sw", "product_name": "x", "short_description": "x"}
		)
		self.assertEqual(
			data,
			{"name": "ill-el01-sw", "product_name": "Elevate [SW]", "short_description": "Template copy"},
		)

	def test_as_dict_carries_template_tables(self):
		data = listing(product()).as_dict()
		self.assertEqual(data["gallery_images"], [{"image": "/files/new.jpg"}])
		self.assertEqual(data["product_category"], "linear")


def mirror(source, **template_values):
	with load_service(ROOT + ".web_listing_source") as (module, frappe):
		module.listing_for = MagicMock(return_value=(FIXTURE, "ILL-EL01-SW"))
		frappe.get_doc.side_effect = lambda value, *args: (
			template(**template_values) if isinstance(value, str) else MagicMock()
		)
		changed = module.mirror_to_template(source)
		return changed, frappe


class Mirroring(unittest.TestCase):
	def test_an_edit_reaches_a_template_that_still_matched(self):
		before = product(short_description="Template copy")
		changed, frappe = mirror(product(before=before, short_description="New copy"))
		self.assertEqual(changed, ["short_description"])
		frappe.db.set_value.assert_called_once_with(
			FIXTURE, "ILL-EL01-SW", {"short_description": "New copy"}, update_modified=False
		)

	def test_a_value_kept_on_the_template_is_not_overwritten(self):
		before = product(short_description="Something else")
		changed, frappe = mirror(product(before=before, short_description="New copy"))
		self.assertEqual(changed, [])
		frappe.db.set_value.assert_not_called()

	def test_a_new_compatibility_row_is_mirrored(self):
		rows = [{"related_product": "ill-sh02-sw", "relationship_type": "Alternative To"}]
		added = [*rows, {"related_product": "ill-sh03-tw", "relationship_type": "Alternative To"}]
		before = product(compatible_products=rows)
		changed, frappe = mirror(product(before=before, compatible_products=added), compatible_products=rows)
		self.assertEqual(changed, ["compatible_products"])
		frappe.db.delete.assert_called_once_with(
			"ilL-Child-Webflow-Compatibility",
			{"parent": "ILL-EL01-SW", "parenttype": FIXTURE, "parentfield": "compatible_products"},
		)
		self.assertEqual(frappe.get_doc.call_count, 3)  # the template, then two rows

	def test_a_renamed_product_updates_the_web_title(self):
		before = product()
		changed, frappe = mirror(product(before=before, product_name="Elevate SW"))
		self.assertEqual(changed, ["web_title"])
		frappe.db.set_value.assert_called_once_with(
			FIXTURE, "ILL-EL01-SW", {"web_title": None}, update_modified=False
		)

	def test_a_new_product_is_left_alone(self):
		changed, frappe = mirror(product(before=None, short_description="New copy"))
		self.assertEqual(changed, [])
		frappe.get_doc.assert_not_called()


class PayloadParity(unittest.TestCase):
	def test_reports_keys_that_differ_between_the_two_reads(self):
		with load_service(ROOT + ".web_listing_source") as (module, frappe):
			frappe.only_for = MagicMock()
			module.listing_for = MagicMock(side_effect=[(FIXTURE, "A"), (PRODUCT, "ill-b")])
			frappe.get_all.side_effect = [["ill-a", "ill-b"], ["illumenate"]]
			module._export = MagicMock(
				side_effect=lambda name, brand: (
					{"short_description": "Old", "name": name}
					if getattr(frappe.flags, "web_listing_legacy_read", None)
					else {"short_description": "New", "name": name}
				)
			)
			report = module.payload_parity()
		self.assertEqual(
			report, [{"listing": "ill-a", "brand": "illumenate", "differences": ["short_description"]}]
		)


if __name__ == "__main__":
	unittest.main()
