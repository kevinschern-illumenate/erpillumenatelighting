"""Spec sheet images stored on the template's tables (owner, 2026-11-02)."""

import unittest

from test_services import ROOT, Record, load_service


class Images(unittest.TestCase):
	def test_each_component_type_takes_its_first_items_image(self):
		with load_service(ROOT + ".template_images") as (module, _frappe):
			rows = [
				Record(component_type="Profile", component_item="CH-RA01-SW"),
				Record(component_type="Profile", component_item="CH-RA01-WH"),
				Record(component_type="Lens", component_item=None),
				Record(component_type="Lens", component_item="LN-RA01-FR"),
			]
			images = {"CH-RA01-SW": "/files/ch-ra01.png", "LN-RA01-FR": "/files/lens.png"}
			template = Record(kit_components=rows)
			module.fill_component_images(template, image_of=images.get)
			self.assertEqual(
				[row.component_image for row in rows],
				["/files/ch-ra01.png", "/files/ch-ra01.png", "/files/lens.png", "/files/lens.png"],
			)

	def test_the_variant_parent_image_comes_first(self):
		with load_service(ROOT + ".template_images") as (module, frappe):
			items = {"CH-RA01-SW": Record(variant_of="CH-RA01", image="/files/own.png")}
			frappe.db.get_value.side_effect = lambda doctype, name, fields, as_dict=False: (
				items.get(name) if as_dict else {"CH-RA01": "/files/parent.png"}.get(name)
			)
			self.assertEqual(module.item_image("CH-RA01-SW"), "/files/parent.png")

	def test_badges_follow_the_templates_brand(self):
		with load_service(ROOT + ".template_images") as (module, _frappe):
			badges = {
				("UL", "badge_image_dark"): "/files/ul-ill.png",
				("UL", "badge_image_dark_206"): "/files/ul-206.png",
			}
			for brand, expected in (
				("illumenate", "/files/ul-ill.png"),
				("lighting_206", "/files/ul-206.png"),
			):
				row = Record(certification="UL")
				template = Record(certifications=[row], target_brands=[Record(brand=brand, enabled=1)])
				field = module.BADGE_FIELDS[brand]
				module.fill_certification_badges(template, badge_of=lambda name, f=field: badges[(name, f)])
				self.assertEqual(row.badge_image, expected)


if __name__ == "__main__":
	unittest.main()
