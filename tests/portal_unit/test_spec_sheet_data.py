"""Spec sheet payload v2: template and product kept apart, legacy view unchanged (plan 4.6)."""

import json
import unittest
from pathlib import Path

from test_services import ROOT, load_service

APP = Path(__file__).resolve().parents[2] / "illumenate_lighting/illumenate_lighting"
LAYOUT = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading"}


class Row(dict):
	def __getattr__(self, key):
		return self.get(key)

	def as_dict(self):
		return dict(self)


class Doc(Row):
	def __init__(self, doctype, name, **values):
		super().__init__(values, name=name)
		self.doctype = doctype

	def __setattr__(self, key, value):
		self[key] = value

	def as_dict(self):
		return {
			"doctype": self.doctype,
			**{k: ([dict(r) for r in v] if isinstance(v, list) else v) for k, v in self.items()},
		}


class Payload(unittest.TestCase):
	def setUp(self):
		context = load_service(ROOT + ".spec_sheet_data")
		self.module, self.frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		self.frappe.conf = {"illumenate_environment": "staging"}

	def test_every_webflow_product_field_has_an_owner(self):
		doc = json.loads((APP / "doctype/ill_webflow_product/ill_webflow_product.json").read_text())
		fields = {f["fieldname"] for f in doc["fields"] if f["fieldtype"] not in LAYOUT}
		owned = {field for field, _note in self.module.PRODUCT_FIELDS}
		classified = owned | set(self.module.MIRRORED) | set(self.module.NOT_LISTING)
		self.assertEqual(sorted(fields - classified), [], "classify new Webflow Product fields")
		self.assertEqual(sorted(classified - fields), [], "drop removed fields")
		self.assertFalse(owned & set(self.module.MIRRORED))

	def test_sections_keep_owners_apart_and_legacy_is_passed_through(self):
		template = Doc(
			"ilL-Extrusion-Kit-Template",
			"KIT-RA01",
			template_name="Rainier Kit",
			webflow_product="kit-ra01",
			specifications=[{"spec_label": "CRI", "spec_value": "90", "parent": "KIT-RA01", "idx": 1}],
			modified="x",
		)
		product = Doc(
			"ilL-Webflow-Product",
			"kit-ra01",
			product_slug="kit-ra01",
			webflow_status="Published",
			webflow_specifications=[{"spec_label": "CRI", "spec_value": "90"}],
			sync_targets=[Row(brand="illumenate", webflow_item_id="abc", sync_status="Synced")],
			sync_status="Pending",
		)
		legacy = {"name": "kit-ra01", "custom_webflow_status": "Published", "configurator_options": []}
		data = self.module.build(template, product, "illumenate", legacy)
		self.assertEqual(data["schema_version"], 2)
		self.assertEqual(data["context"]["environment"], "staging")
		self.assertEqual(data["template"]["specifications"], [{"spec_label": "CRI", "spec_value": "90"}])
		self.assertNotIn("modified", data["template"])
		self.assertNotIn("webflow_specifications", data["product"])
		self.assertEqual(data["product"]["webflow_status"], "Published")
		self.assertEqual(data["webflow"]["webflow_item_id"], "abc")
		self.assertEqual(data["webflow"]["sync_status"], "Synced")
		self.assertIs(data["legacy"], legacy)

	def test_a_template_without_a_product(self):
		data = self.module.build(Doc("ilL-Driver-Template", "PS-UNIV"), None, "illumenate")
		self.assertIsNone(data["product"])
		self.assertIsNone(data["webflow"])
		self.assertIsNone(data["legacy"])

	def test_a_spec_sheet_is_only_for_the_templates_own_brand(self):
		self.frappe._ = lambda text: text
		template = Doc(
			"ilL-Extrusion-Kit-Template", "KIT-RA01", target_brands=[Row(brand="illumenate", enabled=1)]
		)
		self.assertEqual(self.module._brand(template), "illumenate")
		self.assertEqual(self.module._brand(template, "illumenate"), "illumenate")
		with self.assertRaises(ValueError):
			self.module._brand(template, "lighting_206")
		with self.assertRaises(ValueError):
			self.module._brand(Doc("ilL-Extrusion-Kit-Template", "KIT-RA02", target_brands=[]))

	def test_the_file_name_has_the_brand_and_keeps_brackets(self):
		name = self.module.spec_sheet_file_name
		kit = Doc(
			"ilL-Extrusion-Kit-Template",
			"KIT-RA01",
			display_name="Rainier [SF] Extrusion Kit",
			template_name="Rainier [SF]-6.5ft Extrusion Kit",
		)
		self.assertEqual(
			name(kit, "illumenate"), "ilLumenate Lighting_Rainier [SF] Extrusion Kit_Spec Sheet.pdf"
		)
		self.assertEqual(name(kit, "lighting_206"), "206 Lighting_Rainier [SF] Extrusion Kit_Spec Sheet.pdf")
		driver = Doc("ilL-Driver-Template", "PS-UNIV", display_name="", template_name="")
		self.assertEqual(name(driver, "illumenate"), "ilLumenate Lighting_PS-UNIV_Spec Sheet.pdf")
		odd = Doc("ilL-Driver-Template", "X", template_name='A/B: "C"  D')
		self.assertEqual(name(odd, "illumenate"), "ilLumenate Lighting_AB C D_Spec Sheet.pdf")

	def test_the_ownership_table_names_each_field_once(self):
		fields = [row[0] for row in self.module.ownership_table()]
		self.assertEqual(len(fields), len(set(fields)))


if __name__ == "__main__":
	unittest.main()
