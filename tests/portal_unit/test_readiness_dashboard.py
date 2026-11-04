"""Product readiness dashboard (plan 5.6) with Frappe boundary doubles."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, load_service

MODULE = ROOT + ".api.readiness_dashboard"
LINKS = {
	"ilL-Fixture-Template": "fixture_template",
	"ilL-Tape-Neon-Template": "tape_neon_template",
	"ilL-Controller-Template": "controller_template",
	"ilL-Driver-Template": "driver_template",
	"ilL-Extrusion-Kit-Template": "kit_template",
	"ilL-LED-Sheet-Template": "led_sheet_template",
}
LINK_TYPES = {
	"fixture_template": ("Fixture Template",),
	"tape_neon_template": ("LED Tape", "COB Tape", "LED Neon"),
	"controller_template": ("Controller",),
	"driver_template": ("Driver",),
	"kit_template": ("Extrusion Kit",),
	"led_sheet_template": ("LED Sheet",),
}


def deps(images=None, allowed=True):
	return {
		ROOT + ".portal.staff": types.SimpleNamespace(allowed=lambda capability: allowed),
		ROOT + ".web_listing_schema": types.SimpleNamespace(WEBFLOW_PRODUCT_LINKS=LINKS, WEBFLOW_PRODUCT_LINK_TYPES=LINK_TYPES),
		ROOT + ".api.product_projection": types.SimpleNamespace(resolve_product_images=MagicMock(return_value=images or {})),
	}


def product(**values):
	row = {
		"name": "slim-12", "product_name": "Slim 12", "product_slug": "slim-12", "product_type": "Fixture Template",
		"is_active": 1, "is_configurable": 1, "fixture_template": "SLIM-12", "sync_status": "Synced", "sync_error_message": None,
	}
	row.update(values)
	return row


TEMPLATE = {"name": "SLIM-12", "hero_image": "/files/h.jpg", "hero_image_alt": "Slim", "spec_sheet": "/files/s.pdf"}


class RowStatus(unittest.TestCase):
	def status(self, *args, **kwargs):
		with load_service(MODULE, deps()) as (module, _frappe):
			return module.row_status(*args, **kwargs)

	def test_complete_product_is_green_everywhere(self):
		row = self.status(product(), TEMPLATE, {"primary": "/files/h.jpg", "primary_source": "template_hero"}, 4, 2,
			[{"image": "/files/g.jpg", "alt_text": "Side"}], [{"name": "PUB-1", "brand": "illumenate", "state": "LIVE"}])
		self.assertTrue(row["ready"])
		self.assertEqual({column: cell["status"] for column, cell in row["cells"].items()}, dict.fromkeys(row["cells"], "ok"))
		self.assertEqual((row["cells"]["source"]["doctype"], row["cells"]["source"]["name"]), ("ilL-Fixture-Template", "SLIM-12"))

	def test_failures_point_at_the_record_and_field_to_fix(self):
		row = self.status(product(product_name="", fixture_template=None, sync_status="Error", sync_error_message="429"),
			None, {}, 0, 0, [{"image": "/files/g.jpg", "alt_text": " "}], [])
		cells = row["cells"]
		self.assertFalse(row["ready"])
		self.assertEqual((cells["identity"]["status"], cells["identity"]["field"]), ("fail", "product_name"))
		self.assertEqual((cells["source"]["status"], cells["source"]["field"]), ("fail", "fixture_template"))
		self.assertEqual((cells["images"]["status"], cells["images"]["field"]), ("fail", "featured_image"))
		self.assertEqual((cells["specs"]["status"], cells["docs"]["status"]), ("warn", "warn"))
		self.assertEqual((cells["alt_text"]["status"], cells["alt_text"]["field"]), ("warn", "gallery_images"))
		self.assertEqual(cells["spec_sheet"]["status"], "na")
		self.assertEqual(cells["publication"]["status"], "warn")
		self.assertEqual((cells["webflow_sync"]["status"], cells["webflow_sync"]["message"]), ("fail", "429"))

	def test_template_gaps_click_through_to_the_template(self):
		row = self.status(product(), {"name": "SLIM-12", "hero_image": None, "hero_image_alt": None, "spec_sheet": None}, {}, 1, 1, [], [])
		images, sheet = row["cells"]["images"], row["cells"]["spec_sheet"]
		self.assertEqual((images["doctype"], images["name"], images["field"]), ("ilL-Fixture-Template", "SLIM-12", "hero_image"))
		self.assertEqual((sheet["status"], sheet["field"]), ("warn", "spec_sheet"))
		alt = self.status(product(), {**TEMPLATE, "hero_image_alt": ""}, {"primary": "x"}, 1, 1, [], [])["cells"]["alt_text"]
		self.assertEqual((alt["status"], alt["field"], alt["doctype"]), ("warn", "hero_image_alt", "ilL-Fixture-Template"))
		missing = self.status(product(), None, {"primary": "x"}, 1, 1, [], [])["cells"]["source"]
		self.assertEqual(missing["message"], "Linked template no longer exists")

	def test_publication_shows_the_worst_brand_and_non_template_products(self):
		row = self.status(product(product_type="Accessory", fixture_template=None, portal_item="ACC-1", is_active=0), None,
			{"primary": "x"}, 1, 1, [], [{"name": "A", "brand": "a", "state": "LIVE"}, {"name": "B", "brand": "b", "state": "FAILED"}])
		self.assertEqual(row["cells"]["source"]["status"], "ok")
		self.assertEqual((row["cells"]["publication"]["status"], row["cells"]["publication"]["name"]), ("fail", "B"))
		self.assertEqual(row["cells"]["publication"]["message"], "a: LIVE, b: FAILED")
		idle = self.status(product(product_type="Component", fixture_template=None, is_active=0), None, {"primary": "x"}, 1, 1, [], [])
		self.assertEqual((idle["cells"]["source"]["status"], idle["cells"]["publication"]["status"]), ("na", "na"))


class Dashboard(unittest.TestCase):
	def run_page(self, products, allowed=True, **kwargs):
		calls = []

		def get_all(doctype, **options):
			calls.append((doctype, options))
			if doctype == "ilL-Webflow-Product":
				return products
			if doctype == "ilL-Fixture-Template":
				return [TEMPLATE]
			if doctype == "ilL-Child-Webflow-Specification":
				return [{"parent": "a", "rows": 3}]
			if doctype == "ilL-Child-Webflow-Brand-Target":
				return ["b", "a", "c", "a"]
			return []

		with load_service(MODULE, deps({"a": {"primary": "/files/h.jpg"}}, allowed)) as (module, frappe):
			frappe.get_all = MagicMock(side_effect=get_all)
			return module.dashboard(**kwargs), calls, module

	def test_page_is_batched_and_keyset_paginated(self):
		products = [product(name=name, product_slug=name) for name in ("a", "b", "c")]
		result, calls, module = self.run_page(products, limit="2", family="Fixture Template")
		self.assertEqual([row["product"] for row in result["rows"]], ["a", "b"])
		self.assertEqual(result["next_cursor"], "b")
		product_call = calls[0][1]
		self.assertEqual(product_call["filters"], {"product_type": "Fixture Template"})
		self.assertEqual(product_call["limit_page_length"], 3)
		self.assertEqual(len(calls), 6)
		self.assertEqual(result["rows"][0]["cells"]["specs"]["message"], "3 rows")
		self.assertEqual(module.dashboard.whitelist_options, {"methods": ["GET"]})

	def test_brand_filter_and_cursor_and_incomplete_only(self):
		result, calls, _module = self.run_page([product(name="b"), product(name="c")], brand="illumenate", after="a", only_incomplete="1")
		self.assertEqual(calls[1][1]["filters"]["name"], ["in", ["b", "c"]])
		self.assertEqual(next(options for doctype, options in calls if doctype == "ilL-Product-Publication")["filters"]["brand"], "illumenate")
		self.assertTrue(all(not row["ready"] for row in result["rows"]))
		self.assertIsNone(result["next_cursor"])

	def test_empty_page_and_staff_only(self):
		result, calls, _module = self.run_page([])
		self.assertEqual((result["rows"], result["next_cursor"], len(calls)), ([], None, 1))
		with self.assertRaises(PermissionError):
			self.run_page([], allowed=False)


if __name__ == "__main__":
	unittest.main()
