"""Installed-site check that the D1 image resolver reads real columns (plan 5.4)."""

from frappe.tests import IntegrationTestCase

from illumenate_lighting.illumenate_lighting.api.product_projection import (
	HERO_LINKS,
	PRODUCT_DOCTYPE,
	TEMPLATE_IMAGE_FIELDS,
	_fields,
	resolve_product_images,
)

LEGACY_IMAGE = {"ilL-Tape-Neon-Template", "ilL-LED-Sheet-Template", "ilL-Extrusion-Kit-Template"}


class TestProductImages(IntegrationTestCase):
	def test_every_template_type_has_a_hero_image_and_only_real_fields_are_read(self):
		for _field, doctype in HERO_LINKS:
			with self.subTest(doctype=doctype):
				fields = _fields(doctype, TEMPLATE_IMAGE_FIELDS)
				self.assertIn("hero_image", fields)
				self.assertEqual("image" in fields, doctype in LEGACY_IMAGE)

	def test_queries_run_against_the_real_schema(self):
		for doctype in (PRODUCT_DOCTYPE, *(doctype for _field, doctype in HERO_LINKS)):
			with self.subTest(doctype=doctype):
				self.assertEqual(resolve_product_images(doctype, ["__no_such_record__"]), {})
