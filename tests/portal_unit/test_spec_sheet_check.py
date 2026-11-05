"""What a template needs before its spec sheet is generated (owner, 2026-11-03)."""

import unittest

from test_services import ROOT, Record, load_service

KIT = "ilL-Extrusion-Kit-Template"


class Template(Record):
	def __init__(self, doctype, **values):
		super().__init__(values)
		self.doctype = doctype


def complete_kit(**changes):
	values = {
		"name": "KIT-RA01",
		"display_name": "Rainier [SF] Extrusion Kit",
		"product_category": "extrusions",
		"operating_temp_min_c": -20,
		"operating_temp_max_c": 45,
		"sublabel": "Surface",
		"hero_image": "/files/hero.png",
		"dimensions_image": "/files/dims.jpg",
		"target_brands": [Record(brand="illumenate", enabled=1)],
		"specifications": [Record(spec_label="Finish", spec_value="Black")],
		"default_profile_spec": "CH-RA01-BK",
		"kit_components": [
			Record(
				component_type="Profile",
				component_item="CH-RA01-BK",
				component_image="/files/ch.jpg",
				component_description="Black",
			)
		],
		"certifications": [Record(certification="Dry Rated", badge_image="/files/dry.svg")],
		"part_no_configurator": [
			Record(option_step=1, option_type="Finish", option_label="Finish", depends_on_step=0)
		],
	}
	values.update(changes)
	return Template(KIT, **values)


class Check(unittest.TestCase):
	def setUp(self):
		context = load_service(ROOT + ".spec_sheet_check")
		self.module, self.frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		self.frappe.conf = {
			"spec_sheet_template_sites": {"illumenate": "https://illumenate-staging.webflow.io"}
		}
		self.frappe.db.get_value.return_value = Record(
			dimensions="0.59 x 0.59", width_mm=None, height_mm=None
		)
		self.module.page_slug = lambda template: "extrusion-kit"

	def run_check(self, template):
		return self.module.check(template)

	def test_a_complete_kit_is_ready(self):
		result = self.run_check(complete_kit())
		self.assertEqual(result["missing"], [])
		self.assertEqual(result["warnings"], [])
		self.assertEqual(
			result["page_url"], "https://illumenate-staging.webflow.io/spec-sheet-templates/extrusion-kit"
		)

	def test_every_required_field_is_listed(self):
		template = complete_kit(
			display_name="",
			template_name="",
			sublabel="",
			hero_image=None,
			dimensions_image=None,
			specifications=[Record(spec_label="Finish", spec_value="")],
			default_profile_spec=None,
			kit_components=[],
		)
		missing = self.run_check(template)["missing"]
		for expected in (
			"Display Name or Template Name",
			"Sublabel",
			"Hero Image",
			"Dimensions Image",
			"Specifications (at least one row with a value)",
			"Default Profile Spec",
			"Kit Components (at least one row)",
		):
			self.assertIn(expected, missing)

	def test_brand_category_and_configurator_are_required(self):
		self.assertIn(
			"Target Brand (one enabled row)", self.run_check(complete_kit(target_brands=[]))["missing"]
		)
		self.assertIn("Product Category", self.run_check(complete_kit(product_category=None))["missing"])
		missing = self.run_check(
			complete_kit(
				part_no_configurator=[
					Record(option_step=1, option_type="Finish", option_label="", depends_on_step=None)
				]
			)
		)["missing"]
		self.assertIn("Part No. Configurator step 1: Option Label, Depends On Step", missing)
		self.assertIn(
			"Part No. Configurator (at least one step)",
			self.run_check(complete_kit(part_no_configurator=[]))["missing"],
		)

	def test_kit_rules(self):
		rows = [
			Record(
				component_type="Profile",
				component_item="CH-RA01-BK",
				component_image=None,
				component_description="",
			),
			Record(
				component_type="Lens",
				component_item=None,
				component_image="/files/l.jpg",
				component_description="White",
			),
		]
		result = self.run_check(
			complete_kit(
				kit_components=rows,
				operating_temp_min_c=0,
				operating_temp_max_c=0,
				certifications=[Record(certification="UL", badge_image=None)],
			)
		)
		self.assertIn("Operating Temperature Min and Max", result["missing"])
		self.assertIn("Kit Components row 1: Description", result["missing"])
		self.assertIn("Kit Components row 2: Component Item", result["missing"])
		self.assertIn(
			"No Component Image for Profile (its first item's Variant Of item has no image)",
			result["warnings"],
		)
		self.assertIn("Certification UL has no Badge Image (its badge is skipped)", result["warnings"])


class TemplateSites(unittest.TestCase):
	def test_the_site_config_map_may_be_a_json_string(self):
		with load_service(ROOT + ".spec_sheet_check") as (module, _frappe):
			expected = {"illumenate": "https://staging-illumenate.webflow.io"}
			self.assertEqual(module.template_sites(expected), expected)
			self.assertEqual(
				module.template_sites('{"illumenate": "https://staging-illumenate.webflow.io"}'), expected
			)
			self.assertEqual(module.template_sites("not json"), {})
			self.assertEqual(module.template_sites(None), {})
			self.assertEqual(module.template_sites('["a"]'), {})


if __name__ == "__main__":
	unittest.main()
