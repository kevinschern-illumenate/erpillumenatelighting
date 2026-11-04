"""Staging gets its own Webflow site: stored item IDs are matched to the new site's items."""

import unittest

from test_services import ROOT, load_service


def item(id, erp_sync_id="", slug="", name=""):
	return {"id": id, "erp_sync_id": erp_sync_id, "slug": slug, "name": name}


class Matching(unittest.TestCase):
	def test_products_match_by_erp_sync_id_then_slug(self):
		with load_service(ROOT + ".api.staging_webflow_remap") as (module, _frappe):
			products = [
				{"name": "kit-ra01", "product_slug": "kit-ra01", "current": "old1"},
				{"name": "led-hd-sw", "product_slug": "Static-White-HD", "current": None},
				{"name": "gone", "product_slug": "gone", "current": "old3"},
			]
			items = [
				item("n1", erp_sync_id="KIT-RA01", slug="other"),
				item("n2", slug="static-white-hd"),
				item("n9", slug="only-on-webflow"),
			]
			matched, unmatched, unused = module.match_products(products, items)
			self.assertEqual(
				[(p["name"], p["item"]["id"]) for p in matched], [("kit-ra01", "n1"), ("led-hd-sw", "n2")]
			)
			self.assertEqual([p["name"] for p in unmatched], ["gone"])
			self.assertEqual([i["id"] for i in unused], ["n9"])

	def test_an_item_is_not_used_twice_by_erp_sync_id_and_slug(self):
		with load_service(ROOT + ".api.staging_webflow_remap") as (module, _frappe):
			matched, _unmatched, unused = module.match_products(
				[{"name": "a", "product_slug": "b"}], [item("n1", erp_sync_id="a"), item("n2", slug="b")]
			)
			self.assertEqual(matched[0]["item"]["id"], "n1")
			self.assertEqual([i["id"] for i in unused], ["n2"])

	def test_categories_match_by_slug_then_name(self):
		with load_service(ROOT + ".api.staging_webflow_remap") as (module, _frappe):
			categories = [
				{"name": "Extrusions", "category_slug": "extrusions", "category_name": "Extrusions"},
				{"name": "Neon", "category_slug": "", "category_name": "Neon"},
				{"name": "Missing", "category_slug": "missing", "category_name": "Missing"},
			]
			items = [item("c1", slug="extrusions"), item("c2", slug="neon-x", name="neon")]
			matched, unmatched, unused = module.match_categories(categories, items)
			self.assertEqual(
				[(c["name"], c["item"]["id"]) for c in matched], [("Extrusions", "c1"), ("Neon", "c2")]
			)
			self.assertEqual([c["name"] for c in unmatched], ["Missing"])
			self.assertEqual(unused, [])


if __name__ == "__main__":
	unittest.main()
