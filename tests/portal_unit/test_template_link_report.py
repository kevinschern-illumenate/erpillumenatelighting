"""Phase 1a consistency report for the template link flip."""

import unittest

from test_services import ROOT, load_service

KIT = "ilL-Extrusion-Kit-Template"
TAPE = "ilL-Tape-Neon-Template"
DRIVER = "ilL-Driver-Template"


def product(name, product_type="Extrusion Kit", **links):
	row = {
		"name": name,
		"product_type": product_type,
		"product_category": links.pop("product_category", None),
		"series": links.pop("series", None),
	}
	for field in (
		"fixture_template",
		"tape_neon_template",
		"controller_template",
		"driver_template",
		"kit_template",
		"led_sheet_template",
	):
		row[field] = links.get(field)
	return row


def template(name, webflow_product=None, product_status="Internal Only", **values):
	return {"name": name, "webflow_product": webflow_product, "product_status": product_status, **values}


class Report(unittest.TestCase):
	def build(self, products, templates, product_brands=None, template_brands=None):
		with load_service(ROOT + ".template_link_report") as (module, _frappe):
			full = {doctype: [] for doctype in module.TEMPLATE_DOCTYPES}
			full.update(templates)
			return module.build_report(products, full, product_brands or {}, template_brands or {})

	def test_consistent_pair_and_safe_fills(self):
		report = self.build(
			[
				product("kit-a", kit_template="KIT-A"),  # both sides agree
				product("kit-b", kit_template="KIT-B"),  # template backlink missing
				product("kit-c"),  # product link missing
			],
			{KIT: [template("KIT-A", "kit-a"), template("KIT-B"), template("KIT-C", "kit-c")]},
			product_brands={
				"kit-a": ["illumenate"],
				"kit-b": ["illumenate"],
				"kit-c": ["illumenate", "lighting_206"],
			},
		)
		self.assertEqual(report["consistent"], [{"template": (KIT, "KIT-A"), "product": "kit-a"}])
		self.assertEqual(
			report["set_template_link"], [{"template": (KIT, "KIT-B"), "webflow_product": "kit-b"}]
		)
		self.assertEqual(
			report["set_product_link"],
			[{"template": (KIT, "KIT-C"), "product": "kit-c", "field": "kit_template"}],
		)
		self.assertEqual(
			[row["template"] for row in report["seed_template_brand"]], [(KIT, "KIT-A"), (KIT, "KIT-B")]
		)
		self.assertEqual(report["brand_needs_owner"][0]["product_brands"], ["illumenate", "lighting_206"])
		self.assertEqual(report["conflicts"], [])

	def test_conflicts_are_listed_not_fixed(self):
		report = self.build(
			[
				product("kit-x", kit_template="KIT-X"),
				product("kit-y", kit_template="KIT-X"),  # two products claim one template
				product("two", kit_template="KIT-T", driver_template="DRV-T"),  # two templates on one product
				product("kit-d", kit_template="KIT-D"),  # sides disagree
				product("kit-other"),
				product("tape-on-kit", product_type="LED Tape"),
			],
			{
				KIT: [
					template("KIT-X"),
					template("KIT-D", "kit-other"),
					template("KIT-W", "tape-on-kit"),
				],
			},
		)
		issues = sorted(row["issue"] for row in report["conflicts"])
		self.assertIn("linked from more than one product", issues)
		self.assertIn("links more than one template", issues)
		self.assertIn("template and product disagree", issues)
		self.assertIn("product type 'LED Tape' does not fit", issues)
		self.assertEqual(report["set_template_link"] + report["set_product_link"], [])

	def test_active_without_product_duplicate_names_and_category_changes(self):
		report = self.build(
			[
				product("kit-a", kit_template="KIT-A", product_category="Linear", series="RA"),
				product(
					"tape-a", product_type="LED Tape", tape_neon_template="TAPE-A", product_category="Tape"
				),
			],
			{
				KIT: [
					template("KIT-A", "kit-a", product_category="Kits", series="RA"),
					template("KIT-ACT", product_status="Active"),
					template("dup-1"),
				],
				TAPE: [template("TAPE-A", "tape-a", product_category="LED Tape", webflow_category=None)],
				DRIVER: [template("DUP-1")],
			},
		)
		self.assertEqual(report["active_without_product"], [{"template": (KIT, "KIT-ACT")}])
		self.assertEqual(report["duplicate_names"], [[(DRIVER, "DUP-1"), (KIT, "dup-1")]])
		changes = {row["product"]: row["from_to"] for row in report["category_series_changes"]}
		self.assertEqual(changes["kit-a"], {"product_category": ["Linear", "Kits"]})
		# Tape mirrors its new Webflow Category (D54), not the tape-family Select.
		self.assertEqual(changes["tape-a"], {"product_category": ["Tape", None]})
		self.assertEqual(report["counts"]["category_series_changes"], 2)


if __name__ == "__main__":
	unittest.main()
