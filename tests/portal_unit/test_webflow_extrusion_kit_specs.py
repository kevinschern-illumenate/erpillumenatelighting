"""Saving an Extrusion Kit Webflow Product calculates specifications without failing.

The Extrusion Kit specs block reads the kit template, so it belongs with the other
template-driven specs in sync_custom_template_data. Placed in calculate_specifications
it raised NameError on template_doc, and every Extrusion Kit save and catalog import failed.
"""

import types
import unittest
from pathlib import Path

from test_services import ROOT, load_service


class Meta:
	def get_field(self, fieldname):
		return object() if fieldname == "specifications" else None

	def has_field(self, fieldname):
		return False


class ExtrusionKitSpecs(unittest.TestCase):
	def test_calculate_specifications_does_not_read_the_template(self):
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
		doc = module.ilLWebflowProduct()
		doc.meta = Meta()
		doc.specifications = []
		doc.product_type = "Extrusion Kit"
		doc.kit_template = "DEMO-EXTRUSION-KIT"
		for field in (
			"fixture_template",
			"driver_spec",
			"controller_spec",
			"led_sheet_template",
			"tape_spec",
			"profile_spec",
		):
			setattr(doc, field, None)
		doc.calculate_specifications()
		self.assertEqual(doc.specifications, [])
		frappe.get_doc.assert_not_called()

	def test_the_kit_branch_lives_in_template_sync_with_managed_labels(self):
		path = (
			Path(__file__)
			.resolve()
			.parents[2]
			.joinpath(*ROOT.split("."), "doctype", "ill_webflow_product", "ill_webflow_product.py")
		)
		source = path.read_text(encoding="utf-8")
		calculate = source[
			source.index("def calculate_specifications") : source.index("def _calculate_fixture_specs")
		]
		sync = source[source.index("def sync_custom_template_data") :]
		self.assertNotIn("template_doc", calculate)
		self.assertIn('elif self.product_type == "Extrusion Kit":', sync)
		self.assertIn('"Lenses",', sync[: sync.index("def format_inches")])


if __name__ == "__main__":
	unittest.main()
