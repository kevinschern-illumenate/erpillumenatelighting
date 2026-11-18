"""Pure readiness evaluation for Webflow galleries (no Frappe needed)."""

import unittest

from illumenate_lighting.illumenate_lighting.api.gallery_readiness import evaluate, is_public_file

SERIES = {"Ode", "Custom"}


def make_gallery(**overrides):
	doc = {
		"slug": "ode-wellness",
		"gallery_title": "Ode Wellness",
		"gallery_type": "Residential",
		"seo_description": "A calm wellness space.",
		"about": "The space, the intent and the mood.",
		"completion_date": "2026-01-15",
		"videos": "https://www.youtube.com/watch?v=abc",
		"gallery_images": [{"image": "/files/hero.jpg", "alt_text": "Hero"}],
		"products_used": [{"product": "P-1", "series": "Ode"}],
		"credits": [{"credit_type": "Integrator", "credit_name": "Acme", "website": "https://acme.example"}],
		"applications": [{"application": "Cove"}],
		"services_provided": [{"service": "Troubleshooting"}],
	}
	doc.update(overrides)
	return doc


def make_config(**overrides):
	config = {
		"is_active": 1,
		"sync_enabled": 1,
		"collections": {"Galleries": "coll-1"},
		"erpnext_base_url": "https://erp.example",
		"brand_code": "ILL",
	}
	config.update(overrides)
	return config


REFS = {"P-1": {"name": "P-1", "webflow_item_id": "wf-1"}}


def run(gallery=None, config=None, refs=None, series=SERIES):
	return evaluate(
		gallery if gallery is not None else make_gallery(),
		config=config if config is not None else make_config(),
		product_refs=refs if refs is not None else REFS,
		active_series=series,
	)


def fields(items):
	return [item["field"] for item in items]


class IsPublicFileTest(unittest.TestCase):
	def test_public_cases(self):
		self.assertTrue(is_public_file("/files/x.jpg"))
		self.assertTrue(is_public_file("https://cdn.example/x.jpg"))

	def test_private_cases(self):
		self.assertFalse(is_public_file("/private/files/x.jpg"))
		self.assertFalse(is_public_file("https://erp.example/private/files/x.jpg"))
		self.assertFalse(is_public_file(""))


class BlockingTest(unittest.TestCase):
	def assert_blocks(self, result, field):
		self.assertFalse(result["ready"])
		self.assertIn(field, fields(result["issues"]))

	def test_fully_valid_gallery_is_ready(self):
		result = run()
		self.assertTrue(result["ready"])
		self.assertEqual(result["issues"], [])
		self.assertEqual(result["warnings"], [])

	def test_missing_title(self):
		self.assert_blocks(run(make_gallery(gallery_title="")), "gallery_title")

	def test_bad_slug(self):
		self.assert_blocks(run(make_gallery(slug="Bad Slug")), "slug")
		self.assert_blocks(run(make_gallery(slug="ok-slug\n")), "slug")

	def test_no_gallery_images(self):
		self.assert_blocks(run(make_gallery(gallery_images=[])), "gallery_images")

	def test_private_first_image_blocks(self):
		rows = [{"image": "/private/files/x.jpg"}]
		self.assert_blocks(run(make_gallery(gallery_images=rows)), "gallery_images")

	def test_private_later_image_blocks(self):
		rows = [{"image": "/files/a.jpg"}, {"image": "/private/files/b.jpg"}]
		self.assert_blocks(run(make_gallery(gallery_images=rows)), "gallery_images")

	def test_public_and_https_images_pass(self):
		rows = [{"image": "/files/x.jpg"}, {"image": "https://cdn.example/y.jpg"}]
		self.assertTrue(run(make_gallery(gallery_images=rows))["ready"])

	def test_gallery_type_not_allowed(self):
		self.assert_blocks(run(make_gallery(gallery_type="Spaceport")), "gallery_type")

	def test_application_not_allowed(self):
		rows = [{"application": "Nope"}]
		self.assert_blocks(run(make_gallery(applications=rows)), "applications")

	def test_service_not_allowed(self):
		rows = [{"service": "Nope"}]
		self.assert_blocks(run(make_gallery(services_provided=rows)), "services_provided")

	def test_products_used_empty(self):
		self.assert_blocks(run(make_gallery(products_used=[])), "products_used")

	def test_product_row_without_series(self):
		rows = [{"product": "P-1", "series": ""}]
		self.assert_blocks(run(make_gallery(products_used=rows)), "products_used")

	def test_series_not_active(self):
		rows = [{"product": "P-1", "series": "Retired"}]
		self.assert_blocks(run(make_gallery(products_used=rows)), "products_used")

	def test_product_not_staged(self):
		refs = {"P-1": {"name": "P-1", "webflow_item_id": None}}
		result = run(refs=refs)
		self.assert_blocks(result, "products_used")
		self.assertIn("P-1", [i["record"] for i in result["issues"]])

	def test_product_missing_from_refs(self):
		self.assert_blocks(run(refs={}), "products_used")

	def test_no_integrator_credit(self):
		credits = [{"credit_type": "Architect", "credit_name": "A"}]
		self.assert_blocks(run(make_gallery(credits=credits)), "credits")

	def test_integrator_without_name(self):
		credits = [{"credit_type": "Integrator", "credit_name": " "}]
		self.assert_blocks(run(make_gallery(credits=credits)), "credits")

	def test_website_not_https(self):
		credits = [{"credit_type": "Integrator", "credit_name": "A", "website": "http://a.example"}]
		self.assert_blocks(run(make_gallery(credits=credits)), "credits")

	def test_website_without_host(self):
		credits = [{"credit_type": "Integrator", "credit_name": "A", "website": "https://"}]
		self.assert_blocks(run(make_gallery(credits=credits)), "credits")

	def test_video_from_unsupported_host(self):
		self.assert_blocks(run(make_gallery(videos="https://example.com/watch")), "videos")

	def test_supported_videos_pass(self):
		videos = "https://youtu.be/a, https://vimeo.com/1\nhttps://www.loom.com/share/x\nhttps://x.test/a.mp4"
		self.assertTrue(run(make_gallery(videos=videos))["ready"])

	def test_brand_inactive(self):
		self.assert_blocks(run(config=make_config(is_active=0)), "brand_active")

	def test_sync_disabled(self):
		self.assert_blocks(run(config=make_config(sync_enabled=0)), "sync_enabled")

	def test_no_galleries_collection(self):
		self.assert_blocks(run(config=make_config(collections={})), "galleries_collection")


class WarningTest(unittest.TestCase):
	def assert_warns(self, result, field):
		self.assertTrue(result["ready"])
		self.assertEqual(result["issues"], [])
		self.assertIn(field, fields(result["warnings"]))

	def test_seo_too_long(self):
		self.assert_warns(run(make_gallery(seo_description="x" * 161)), "seo_description")

	def test_seo_empty(self):
		self.assert_warns(run(make_gallery(seo_description="")), "seo_description")

	def test_integrator_without_website(self):
		credits = [{"credit_type": "Integrator", "credit_name": "Acme"}]
		self.assert_warns(run(make_gallery(credits=credits)), "credits")

	def test_no_completion_date(self):
		self.assert_warns(run(make_gallery(completion_date=None)), "completion_date")

	def test_no_about(self):
		self.assert_warns(run(make_gallery(about="")), "about")


class DependenciesTest(unittest.TestCase):
	def test_dependencies_change_with_webflow_id(self):
		first = run()["dependencies"]
		refs = {"P-1": {"name": "P-1", "webflow_item_id": "wf-2"}}
		second = run(refs=refs)["dependencies"]
		self.assertNotEqual(first, second)
		self.assertEqual(first["products"], {"P-1": "wf-1"})
		self.assertEqual(first["series"], ["Ode"])


if __name__ == "__main__":
	unittest.main()
