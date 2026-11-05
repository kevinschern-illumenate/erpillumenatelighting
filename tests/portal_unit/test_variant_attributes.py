"""Accessory variant options in Add Fixture Line: the Finish list must never be silently empty."""

import types
import unittest

from test_services import ROOT, Record, load_service

EXTRAS = {
	"illumenate_lighting.templates.pages.configure": types.SimpleNamespace(
		_fetch_webflow_gallery=lambda products: {}, attach_images=lambda doctype, templates: templates
	),
	ROOT + ".api.option_cache": types.SimpleNamespace(
		cached_projection=lambda kind, template, build: build()
	),
}

FINISHES = [
	Record(attribute_value="Anodized Silver", abbr="SV"),
	Record(attribute_value="Black", abbr="BK"),
	Record(attribute_value="White", abbr="WH"),
]


def item(code, finish):
	return Record(
		item_code=code, item_name=code, attributes=[Record(attribute="Finish", attribute_value=finish)]
	)


class VariantAttributes(unittest.TestCase):
	def run_endpoint(self, variants):
		template = Record(item_code="CH-1", attributes=[Record(attribute="Finish", numeric_values=0)])
		docs = {"CH-1": template, **{row.item_code: row for row in variants}}
		with load_service(ROOT + ".api.portal", EXTRAS) as (module, frappe):
			frappe.db.get_value.return_value = Record(item_code="CH-1", item_name="Channel", has_variants=1)
			frappe.get_doc.side_effect = lambda doctype, name: docs[name]

			def get_all(doctype, filters=None, **kwargs):
				if doctype == "Item":
					return [Record(item_code=row.item_code) for row in variants]
				return FINISHES

			frappe.get_all.side_effect = get_all
			return module.get_item_variant_attributes("CH-1")

	def test_values_keep_the_variant_spelling_in_list_order(self):
		result = self.run_endpoint(
			[item("CH-1-WH", "white "), item("CH-1-SV", "Anodized Silver"), item("CH-1-CU", "Copper")]
		)
		self.assertEqual(
			result["attributes"][0]["values"],
			[
				{"value": "Anodized Silver", "abbr": "SV"},
				{"value": "white ", "abbr": "WH"},
				{"value": "Copper", "abbr": "Copper"},
			],
		)
		self.assertNotIn("variants", result)

	def test_blank_variant_values_offer_the_items_directly(self):
		result = self.run_endpoint([item("CH-1-BK", None), item("CH-1-SV", ""), item("CH-1-WH", "  ")])
		self.assertEqual(result["attributes"][0]["values"], [])
		self.assertEqual(result["incomplete_attributes"], ["Finish"])
		self.assertEqual([row["item_code"] for row in result["variants"]], ["CH-1-BK", "CH-1-SV", "CH-1-WH"])


if __name__ == "__main__":
	unittest.main()
