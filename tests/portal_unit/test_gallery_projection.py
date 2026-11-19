"""Pure payload projection for Webflow galleries (no Frappe needed)."""

import datetime
import unittest

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint
from illumenate_lighting.illumenate_lighting.api.gallery_projection import absolute_url, build_payload

BASE = "https://www.illumenatelighting.com"
REFS = {
	"PRD-1": {"name": "Rainier [SF]", "slug": "kit-ra01", "webflow_item_id": "wf1"},
	"PRD-2": {"name": "Ode <Pro>", "slug": "ode-pro", "webflow_item_id": "wf2"},
	"PRD-3": {"name": "Unstaged", "slug": None, "webflow_item_id": None},
}


def make_gallery(**overrides):
	doc = {
		"name": "ode-wellness",
		"slug": "ode-wellness",
		"gallery_title": "Ode Wellness",
		"featured": 1,
		"seo_description": "A calm space.",
		"about": "About text",
		"case_study": "<p>Already <b>HTML</b></p>",
		"gallery_type": "Residential",
		"quote": "Lovely",
		"quote_attribution": "A. Client",
		"location": "Seattle, WA",
		"completion_date": datetime.date(2026, 3, 9),
		"videos": "",
		"gallery_images": [
			{"image": "/files/a.jpg", "alt_text": "A", "caption": "cap"},
			{"image": "https://cdn.example.com/b.jpg", "alt_text": "B", "caption": ""},
		],
		"products_used": [{"product": "PRD-1", "series": "Ode", "note": "White finish"}],
		"credits": [{"credit_type": "Integrator", "credit_name": "Acme", "website": "https://acme.com"}],
		"applications": [{"application": "Hotels"}],
		"services_provided": [{"service": "Troubleshooting"}],
		"custom_items": [],
	}
	doc.update(overrides)
	return doc


def build(**overrides):
	return build_payload(make_gallery(**overrides), base_url=BASE, product_refs=REFS)


class TestProjection(unittest.TestCase):
	def test_scalars_and_shape(self):
		p = build()
		self.assertEqual(p["schema_version"], 1)
		self.assertEqual(p["erp_sync_id"], "ode-wellness")
		self.assertEqual(p["name"], "Ode Wellness")
		self.assertEqual(p["case_study_html"], "<p>Already <b>HTML</b></p>")
		self.assertEqual(p["completion_date"], "2026-03-09")
		self.assertEqual(p["applications"], ["Hotels"])
		self.assertEqual(p["services_provided"], ["Troubleshooting"])
		self.assertEqual(p["product_item_ids"], ["wf1"])

	def test_completion_date_forms(self):
		self.assertEqual(build(completion_date="2026-03-09")["completion_date"], "2026-03-09")
		self.assertEqual(
			build(completion_date=datetime.datetime(2026, 3, 9, 4, 5))["completion_date"], "2026-03-09"
		)
		self.assertIsNone(build(completion_date=None)["completion_date"])

	def test_first_row_is_hero(self):
		p = build()
		self.assertEqual(p["hero_image"], {"url": BASE + "/files/a.jpg", "alt": "A"})
		self.assertEqual(p["gallery_images"][0], p["hero_image"])
		self.assertEqual(len(p["gallery_images"]), 2)
		rows = make_gallery()["gallery_images"][::-1]
		q = build(gallery_images=rows)
		self.assertEqual(q["hero_image"]["url"], "https://cdn.example.com/b.jpg")
		self.assertNotEqual(fingerprint(p), fingerprint(q))

	def test_no_images_gives_no_hero(self):
		p = build(gallery_images=[{"image": "", "alt_text": "x"}])
		self.assertIsNone(p["hero_image"])
		self.assertEqual(p["gallery_images"], [])

	def test_relative_public_path_becomes_absolute(self):
		self.assertEqual(absolute_url("/files/a.jpg", BASE + "/"), BASE + "/files/a.jpg")
		self.assertEqual(absolute_url("https://x.com/a.jpg", BASE), "https://x.com/a.jpg")
		self.assertEqual(build()["gallery_images"][0]["url"], BASE + "/files/a.jpg")

	def test_relative_path_without_slash_becomes_absolute(self):
		self.assertEqual(absolute_url("files/a.jpg", BASE), BASE + "/files/a.jpg")
		p = build(gallery_images=[{"image": "files/a.jpg", "alt_text": "A"}])
		self.assertEqual(p["hero_image"]["url"], BASE + "/files/a.jpg")

	def test_spaces_in_a_file_name_are_percent_encoded(self):
		# Webflow rejects a URL with raw spaces ("Invalid file url") when it imports the image on publish.
		self.assertEqual(
			absolute_url("/files/Lilium Static White_Hero.png", BASE),
			BASE + "/files/Lilium%20Static%20White_Hero.png",
		)

	def test_encoding_is_idempotent_and_handles_odd_names(self):
		once = absolute_url("/files/Caf\u00e9 #1 (final)?.png", BASE)
		self.assertEqual(once, BASE + "/files/Caf%C3%A9%20%231%20%28final%29%3F.png")
		self.assertEqual(absolute_url(once[len(BASE) :], BASE), once)
		self.assertEqual(absolute_url("/files/a%20b.png", BASE), BASE + "/files/a%20b.png")
		# A % that is not an escape is data, not part of one.
		self.assertEqual(absolute_url("/files/100% cotton.png", BASE), BASE + "/files/100%25%20cotton.png")

	def test_https_url_has_only_its_path_encoded(self):
		self.assertEqual(
			absolute_url("https://x.com/my file.jpg?v=1", BASE), "https://x.com/my%20file.jpg?v=1"
		)

	def test_every_image_in_the_payload_is_encoded(self):
		gallery = {
			"slug": "g",
			"gallery_title": "G",
			"gallery_images": [
				{"image": "/files/Lilium Static White_Hero.png", "alt_text": "hero"},
				{"image": "/files/Second Shot.jpg", "alt_text": ""},
			],
			"custom_items": [{"item_name": "Kit", "detail": "black", "image": "/files/Kit Photo.jpg"}],
		}
		payload = build_payload(gallery, base_url=BASE, product_refs={})
		hero = BASE + "/files/Lilium%20Static%20White_Hero.png"
		self.assertEqual(payload["hero_image"]["url"], hero)
		self.assertEqual(payload["gallery_images"][0]["url"], hero)
		self.assertEqual(payload["gallery_images"][1]["url"], BASE + "/files/Second%20Shot.jpg")
		self.assertIn('src="' + BASE + '/files/Kit%20Photo.jpg"', payload["custom_items_html"])

	def test_http_and_protocol_relative_pass_through(self):
		self.assertEqual(absolute_url("http://x.com/a.jpg", BASE), "http://x.com/a.jpg")
		self.assertEqual(absolute_url("//x.com/a.jpg", BASE), "//x.com/a.jpg")

	def test_product_item_ids_deduplicated_in_row_order(self):
		rows = [
			{"product": "PRD-1", "series": "Ode", "note": "one"},
			{"product": "PRD-2", "series": "Ode"},
			{"product": "PRD-1", "series": "COB", "note": "two"},
		]
		p = build(products_used=rows)
		self.assertEqual(p["product_item_ids"], ["wf1", "wf2"])

	def test_series_distinct_in_row_order(self):
		rows = [{"series": s} for s in ("Custom", "COB", "Custom")]
		self.assertEqual(build(products_used=rows)["series_used"], ["Custom", "COB"])

	def test_series_only_row_adds_series_and_no_product_id(self):
		p = build(products_used=[{"series": "Custom", "note": "kept in the row"}])
		self.assertEqual(p["series_used"], ["Custom"])
		self.assertEqual(p["product_item_ids"], [])
		self.assertEqual(
			p["products"],
			[
				{
					"product": None,
					"name": None,
					"slug": None,
					"series": "Custom",
					"note": "kept in the row",
					"webflow_item_id": None,
				}
			],
		)

	def test_product_without_item_id_is_skipped(self):
		rows = [{"product": "PRD-3", "series": "Ode"}, {"product": "PRD-1", "series": "Ode"}]
		p = build(products_used=rows)
		self.assertEqual(p["product_item_ids"], ["wf1"])

	def test_products_are_the_table_row_by_row(self):
		rows = [
			{"product": "PRD-1", "series": "Ode", "note": "White finish"},
			{"product": "PRD-2", "series": "Ode", "note": ""},
			{"product": "PRD-3", "series": "", "note": "Dimmed"},
			{"product": "PRD-1", "series": "COB", "note": "again"},
		]
		self.assertEqual(
			build(products_used=rows)["products"],
			[
				{
					"product": "PRD-1",
					"name": "Rainier [SF]",
					"slug": "kit-ra01",
					"series": "Ode",
					"note": "White finish",
					"webflow_item_id": "wf1",
				},
				{
					"product": "PRD-2",
					"name": "Ode <Pro>",
					"slug": "ode-pro",
					"series": "Ode",
					"note": None,
					"webflow_item_id": "wf2",
				},
				{
					"product": "PRD-3",
					"name": "Unstaged",
					"slug": None,
					"series": None,
					"note": "Dimmed",
					"webflow_item_id": None,
				},
				{
					"product": "PRD-1",
					"name": "Rainier [SF]",
					"slug": "kit-ra01",
					"series": "COB",
					"note": "again",
					"webflow_item_id": "wf1",
				},
			],
		)

	def test_a_product_missing_from_the_refs_falls_back_to_its_docname(self):
		rows = [{"product": "PRD-9", "series": "Ode", "note": "n"}]
		row = build(products_used=rows)["products"][0]
		self.assertEqual((row["product"], row["name"], row["slug"], row["webflow_item_id"]), ("PRD-9", "PRD-9", None, None))

	def test_no_products_is_an_empty_list_and_notes_html_is_gone(self):
		p = build(products_used=[])
		self.assertEqual(p["products"], [])
		self.assertNotIn("product_notes_html", p)

	def test_custom_items_image_under_its_paragraph(self):
		items = [
			{"item_name": "Sign <1>", "detail": "Neon & glass", "image": "/files/s.png"},
			{"item_name": "Plain", "detail": "No image", "image": ""},
		]
		self.assertEqual(
			build(custom_items=items)["custom_items_html"],
			"<p>Sign &lt;1&gt;: Neon &amp; glass</p>"
			f'<img src="{BASE}/files/s.png" alt="Sign &lt;1&gt;">'
			"<p>Plain: No image</p>",
		)

	def test_videos_split_on_commas_and_newlines(self):
		p = build(videos="https://youtu.be/a, https://vimeo.com/b\nhttps://x.com/c.mp4,\n")
		self.assertEqual(p["videos"], ["https://youtu.be/a", "https://vimeo.com/b", "https://x.com/c.mp4"])
		self.assertEqual(build(videos=None)["videos"], [])

	def test_credits_only_filled_types(self):
		credits = [
			{"credit_type": "Integrator", "credit_name": "Acme", "website": "https://acme.com"},
			{"credit_type": "Architect", "credit_name": "  ", "website": "https://x.com"},
			{"credit_type": "Owner", "credit_name": "Bob", "website": None},
		]
		self.assertEqual(
			build(credits=credits)["credits"],
			{
				"Integrator": {"name": "Acme", "website": "https://acme.com"},
				"Owner": {"name": "Bob", "website": ""},
			},
		)

	def test_payload_is_deterministic(self):
		self.assertEqual(fingerprint(build()), fingerprint(build()))
