"""Every product template can be linked from a Webflow Product in Desk."""

import json
import re
import unittest
from pathlib import Path

from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	TEMPLATE_DOCTYPES,
	WEBFLOW_PRODUCT_LINK_TYPES,
	WEBFLOW_PRODUCT_LINKS,
)

DOCTYPE_DIR = Path("illumenate_lighting/illumenate_lighting/doctype/ill_webflow_product")
PRODUCT = json.loads((DOCTYPE_DIR / "ill_webflow_product.json").read_text())
FIELDS = {field["fieldname"]: field for field in PRODUCT["fields"]}
PRODUCT_TYPES = FIELDS["product_type"]["options"].split("\n")


def section_of(fieldname):
	order = PRODUCT["field_order"]
	for name in reversed(order[: order.index(fieldname)]):
		if FIELDS[name]["fieldtype"] in ("Section Break", "Tab Break"):
			return FIELDS[name]
	return None


class TemplateLinks(unittest.TestCase):
	def test_every_template_has_a_link_field(self):
		self.assertEqual(set(WEBFLOW_PRODUCT_LINKS), set(TEMPLATE_DOCTYPES))
		self.assertEqual(set(WEBFLOW_PRODUCT_LINKS.values()), set(WEBFLOW_PRODUCT_LINK_TYPES))
		for doctype, fieldname in WEBFLOW_PRODUCT_LINKS.items():
			field = FIELDS[fieldname]
			self.assertEqual((field["fieldtype"], field["options"]), ("Link", doctype))
			self.assertTrue(field.get("label"))

	def test_link_fields_sit_in_the_visible_source_section(self):
		for fieldname in WEBFLOW_PRODUCT_LINK_TYPES:
			section = section_of(fieldname)
			self.assertEqual(section["fieldname"], "source_reference_section", fieldname)
			self.assertFalse(section.get("hidden"))
			self.assertFalse(FIELDS[fieldname].get("hidden"))

	def test_link_fields_show_for_their_product_types(self):
		for fieldname, product_types in WEBFLOW_PRODUCT_LINK_TYPES.items():
			shown_for = set(re.findall(r"'([^']+)'", FIELDS[fieldname]["depends_on"]))
			self.assertEqual(shown_for, set(product_types), fieldname)
			self.assertTrue(set(product_types) <= set(PRODUCT_TYPES), fieldname)

	def test_form_script_knows_every_template(self):
		script = (DOCTYPE_DIR / "ill_webflow_product.js").read_text()
		block = re.search(r"const TEMPLATE_LINKS = \{(.*?)\};", script, re.S).group(1)
		self.assertEqual(dict(re.findall(r'(\w+): "([^"]+)"', block)), {v: k for k, v in WEBFLOW_PRODUCT_LINKS.items()})
		for fieldname in WEBFLOW_PRODUCT_LINK_TYPES:
			self.assertIn(f'on_template_change(frm, "{fieldname}")', script)


if __name__ == "__main__":
	unittest.main()
