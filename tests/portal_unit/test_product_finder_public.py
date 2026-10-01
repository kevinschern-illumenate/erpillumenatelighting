"""The public projection never contains commercial or internal product data."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

BASE = ROOT + ".portal.product_finder"
PRODUCT = {
	"name": "P",
	"slug": "p",
	"title": "Product",
	"image": "/files/p.png",
	"family": "Driver",
	"capability": "configure",
	"item_code": "SECRET",
	"price": 99,
	"stock": 20,
}


class Public(unittest.TestCase):
	def context(self):
		self.sessions = types.SimpleNamespace(
			DOCTYPE="Session",
			start=MagicMock(return_value="TOKEN"),
			validate_answers=lambda d, a: a,
			_complete_doc=MagicMock(
				return_value={
					"matches": [{"name": "P", "reasons": ["Fits"], "verify": []}],
					"counts": {"match": 1},
					"relaxed": [],
					"route": None,
				}
			),
		)
		return load_service(
			ROOT + ".api.product_finder_public",
			{
				BASE + ".definition": types.SimpleNamespace(
					load_definition=lambda: {
						"questions": [{"options": [{"image": "/files/choice.png"}]}],
						"settings": {},
					}
				),
				BASE + ".server_definition": types.SimpleNamespace(load=lambda: {}),
				BASE + ".facts": types.SimpleNamespace(load=lambda: [PRODUCT, {**PRODUCT, "name": "HIDDEN"}]),
				BASE + ".sessions": self.sessions,
				BASE + ".matcher": types.SimpleNamespace(evaluate=MagicMock(return_value={"options": {}})),
				ROOT + ".api.webflow_brand": types.SimpleNamespace(
					resolve_brand=lambda b: {"webflow_site_url": "https://brand.test"}
				),
			},
		)

	def setup(self, frappe):
		frappe.session.user = "Guest"
		frappe.get_cached_doc = MagicMock(
			return_value=Record(public_enabled=1, public_brands=[Record(brand="brand")])
		)
		frappe.utils.get_url = lambda path: "https://erp.test" + path if path.startswith("/") else path
		frappe.get_all.side_effect = lambda dt, **kw: (
			["P", "HIDDEN"]
			if "Brand-Target" in dt
			else [Record(parent="P", webflow_collection_slug="products")]
		)

	def test_brand_switch_and_unknown_brand(self):
		with self.context() as (api, frappe):
			self.setup(frappe)
			for brand in ("", None, "foreign"):
				with self.assertRaises(PermissionError):
					api.get_definition(brand)
			frappe.get_cached_doc.return_value.public_enabled = 0
			with self.assertRaises(PermissionError):
				api.get_definition("brand")

	def test_published_only_and_safe_recursive_projection(self):
		with self.context() as (api, frappe):
			self.setup(frappe)
			products, _ = api.published("brand")
			self.assertEqual([p["name"] for p in products], ["P"])
			result = api.complete("brand", "{}")

			def check(value):
				if isinstance(value, dict):
					for key, child in value.items():
						self.assertFalse(any(word in key.lower() for word in ("price", "stock", "item")))
						check(child)
				elif isinstance(value, list):
					for child in value:
						check(child)

			check(result)
			self.assertEqual(result["matches"][0]["url"], "https://brand.test/products/p")
			self.assertEqual(result["matches"][0]["image"], "https://erp.test/files/p.png")
			self.assertEqual(result["claim_url"], "https://erp.test/portal/product-finder?claim=TOKEN")
			self.assertEqual(
				api.get_definition("brand")["questions"][0]["options"][0]["image"],
				"https://erp.test/files/choice.png",
			)

	def test_size_limit_verbs_and_unsafe_images(self):
		with self.context() as (api, frappe):
			self.setup(frappe)
			with self.assertRaises(ValueError):
				api.evaluate("brand", " " * 4097, "q")
			for image in (
				"javascript:alert(1)",
				"http://unsafe.test/a",
				"//unsafe.test/a",
				"/private/files/a",
			):
				self.assertIsNone(api.absolute_image(image))
			self.assertEqual(api.complete.whitelist_options, {"allow_guest": True, "methods": ["POST"]})
			frappe.session.user = "buyer"
			with self.assertRaises(PermissionError):
				api.complete("brand", "{}")
