"""Kit templates generated from kit web listings (Webflow Product merge, step 1)."""

import unittest

from test_services import ROOT, load_service


def plan(listing, profile=None, lens=None):
	with load_service(ROOT + ".web_listing_kits") as (module, _frappe):
		return module.plan_kit_template(listing, profile, lens)


LISTING = {
	"name": "kit-ca01",
	"product_name": "Castle [SF] Extrusion Kit",
	"series": "Castle",
	"profile_spec": "CH-CA01-BK",
	"kit_components": [
		{
			"component_type": "Profile",
			"component_spec_doctype": "ilL-Spec-Profile",
			"component_spec_name": "CH-CA01-BK",
			"quantity": 1,
		},
		{
			"component_type": "Lens",
			"component_spec_doctype": "ilL-Spec-Lens",
			"component_spec_name": "LNS-CA01-WH",
			"quantity": 1,
		},
		{
			"component_type": "Mounting Kit",
			"component_item": "ACC-CA01-MC",
			"quantity": 4,
			"custom_webflow_title": "Clips",
		},
	],
}
PROFILE = {"name": "CH-CA01-BK", "family": "CA01", "stock_length_mm": 2400}
LENS = {"name": "LNS-CA01-WH", "lens_appearance": "White", "stock_length_mm": 2400}


class KitTemplatePlan(unittest.TestCase):
	def test_values_come_from_the_listing_and_its_specs(self):
		values, notes = plan(LISTING, PROFILE, LENS)
		self.assertEqual(values["template_code"], "KIT-CA01")
		self.assertEqual(values["template_name"], "Castle [SF] Extrusion Kit")
		self.assertEqual(values["web_slug"], "kit-ca01")
		self.assertEqual(values["is_active"], 0)
		self.assertEqual(values["default_profile_spec"], "CH-CA01-BK")
		self.assertEqual(values["default_profile_family"], "CA01")
		self.assertEqual((values["profile_stock_length_mm"], values["lens_stock_length_mm"]), (2400, 2400))
		self.assertEqual(values["default_lens_spec"], "LNS-CA01-WH")
		self.assertEqual(values["allowed_options"][0]["lens_appearance"], "White")
		self.assertEqual(values["mounting_accessory_qty"], 4)
		self.assertEqual(values["kit_components"][2]["custom_webflow_title"], "Clips")
		self.assertNotIn("component_spec_name", values["kit_components"][2])
		self.assertFalse(any("stock length" in note for note in notes))

	def test_missing_specs_fall_back_to_the_existing_kit_defaults_and_say_so(self):
		values, notes = plan({"name": "kit-tr01", "product_name": "Triumph Kit"})
		self.assertEqual(values["default_profile_family"], "TR01")
		self.assertNotIn("default_profile_spec", values)
		self.assertNotIn("default_lens_spec", values)
		self.assertEqual((values["profile_stock_length_mm"], values["lens_stock_length_mm"]), (2000, 2000))
		self.assertEqual((values["solid_endcap_qty"], values["feed_through_endcap_qty"]), (2, 2))
		self.assertEqual(values["mounting_accessory_qty"], 1)
		self.assertEqual(values["kit_components"], [])
		for text in ("no profile spec", "no lens spec", "profile stock length assumed", "mounting accessory"):
			self.assertTrue(any(text in note for note in notes), text)


if __name__ == "__main__":
	unittest.main()
