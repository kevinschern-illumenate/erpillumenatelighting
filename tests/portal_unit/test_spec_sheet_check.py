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
		"part_no_configurator": [Record(option_step=1)],
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

	def run_check(self, template, page=True):
		return self.module.check(template, page_exists=lambda url: page)

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

	def test_a_missing_webflow_page_or_brand_stops_it(self):
		self.assertIn(
			"Webflow spec sheet page https://illumenate-staging.webflow.io/spec-sheet-templates/extrusion-kit (not found)",
			self.run_check(complete_kit(), page=False)["missing"],
		)
		self.assertIn(
			"Target Brand (one enabled row)", self.run_check(complete_kit(target_brands=[]))["missing"]
		)

	def test_kit_component_rules(self):
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
				certifications=[Record(certification="UL", badge_image=None)],
				part_no_configurator=[],
			)
		)
		self.assertIn("Kit Components row 2: Component Type and Component Item", result["missing"])
		self.assertIn(
			"Component Image for Profile (from its first item's Variant Of image)", result["missing"]
		)
		self.assertIn("Kit Components row 1 has no Description (only the code is shown)", result["warnings"])
		self.assertIn("Certification UL has no Badge Image (its badge is skipped)", result["warnings"])
		self.assertIn(
			"No Part No. Configurator steps (the part number section is hidden)", result["warnings"]
		)


if __name__ == "__main__":
	unittest.main()
