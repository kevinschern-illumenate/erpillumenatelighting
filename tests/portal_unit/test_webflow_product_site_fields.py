"""Webflow Product saves on sites that lack the live site's own Custom Fields.

custom_compatible_power_supplies, custom_badge_images and the dark/206 certification
badge images were added on the live site in Customize Form. The app does not ship
them, so a fresh site (CI, a new bench) must save Webflow Products without them.
"""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


class Meta:
	def __init__(self, fields, options=None):
		self.fields = set(fields)
		self.options = options or {}

	def has_field(self, fieldname):
		return fieldname in self.fields

	def get_field(self, fieldname):
		return Record(options=self.options.get(fieldname))


CERT_LINK = "ilL-Child-Webflow-Certification-Link"


class SiteFields(unittest.TestCase):
	def product(self, product_fields=(), link_fields=(), cert_fields=("badge_image",)):
		document = types.ModuleType("frappe.model.document")
		document.Document = object
		model = types.ModuleType("frappe.model")
		model.document = document
		context = load_service(
			ROOT + ".doctype.ill_webflow_product.ill_webflow_product",
			{"frappe.model": model, "frappe.model.document": document},
		)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		metas = {CERT_LINK: Meta(link_fields), "ilL-Attribute-Certification": Meta(cert_fields)}
		frappe.get_meta = metas.__getitem__
		frappe.get_all.return_value = ["DRV-96W"]
		frappe.get_doc.return_value = Record(
			name="DRV-96W",
			input_protocols=[],
			input_voltage_min=120,
			input_voltage_max=277,
			input_voltage_type="VAC",
			voltage_output=24,
			max_wattage=96.0,
			location_rating="Dry",
			outputs_count=2,
		)
		frappe.db.get_value.return_value = Record(badge_image="/files/ul.png")

		doc = module.ilLWebflowProduct()
		doc.meta = Meta(product_fields, {"certifications": CERT_LINK})
		doc.tape_neon_template = "DEMO-TAPE"
		doc.target_brands = [Record(brand="illumenate", enabled=1)]
		doc.certifications = [Record(certification="UL")]
		doc.rows = {}
		doc.get = lambda key, default=None: getattr(doc, key, default)
		doc.append = lambda key, row: doc.rows.setdefault(key, []).append(row)
		return doc, frappe

	def test_a_site_without_the_fields_saves_without_touching_them(self):
		doc, frappe = self.product()
		doc.populate_compatible_power_supplies()
		doc.populate_certification_badges()
		self.assertEqual(doc.rows, {})
		frappe.get_all.assert_not_called()
		frappe.db.get_value.assert_not_called()
		self.assertNotIn("custom_badge_images", vars(doc.certifications[0]))

	def test_the_live_site_still_fills_them(self):
		doc, frappe = self.product(
			product_fields=["custom_compatible_power_supplies"],
			link_fields=["custom_badge_images"],
		)
		doc.populate_compatible_power_supplies()
		doc.populate_certification_badges()
		(row,) = doc.rows["custom_compatible_power_supplies"]
		self.assertEqual((row["part_number"], row["output_count"]), ("DRV-96W", 2))
		self.assertIn("illumenate_badge_light", doc.certifications[0].custom_badge_images)
		# Only the badge columns this site has are read.
		self.assertEqual(frappe.db.get_value.call_args.args[2], ["badge_image"])


if __name__ == "__main__":
	unittest.main()
