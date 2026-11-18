"""Pure payload projection for Webflow galleries (no Frappe needed)."""

import datetime
import unittest

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint
from illumenate_lighting.illumenate_lighting.api.gallery_projection import absolute_url, build_payload

BASE = "https://www.illumenatelighting.com"
REFS = {
	"PRD-1": {"name": "Rainier [SF]", "webflow_item_id": "wf1"},
	"PRD-2": {"name": "Ode <Pro>", "webflow_item_id": "wf2"},
	"PRD-3": {"name": "Unstaged", "webflow_item_id": None},
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
		self.assertEqual(p["product_notes_html"], "<p>Rainier [SF]: one</p><p>Rainier [SF]: two</p>")

	def test_series_distinct_in_row_order(self):
		rows = [{"series": s} for s in ("Custom", "COB", "Custom")]
		self.assertEqual(build(products_used=rows)["series_used"], ["Custom", "COB"])

	def test_series_only_row_adds_series_not_notes(self):
		p = build(products_used=[{"series": "Custom", "note": "ignored"}])
		self.assertEqual(p["series_used"], ["Custom"])
		self.assertEqual(p["product_notes_html"], "")
		self.assertEqual(p["product_item_ids"], [])

	def test_product_without_item_id_is_skipped(self):
		rows = [{"product": "PRD-3", "series": "Ode"}, {"product": "PRD-1", "series": "Ode"}]
		p = build(products_used=rows)
		self.assertEqual(p["product_item_ids"], ["wf1"])

	def test_product_notes_one_paragraph_per_row_with_note(self):
		rows = [
			{"product": "PRD-1", "series": "Ode", "note": "White finish"},
			{"product": "PRD-2", "series": "Ode", "note": ""},
			{"product": "PRD-3", "series": "Ode", "note": "Dimmed"},
		]
		self.assertEqual(
			build(products_used=rows)["product_notes_html"],
			"<p>Rainier [SF]: White finish</p><p>Unstaged: Dimmed</p>",
		)

	def test_notes_fall_back_to_docname(self):
		rows = [{"product": "PRD-9", "series": "Ode", "note": "n"}]
		self.assertEqual(build(products_used=rows)["product_notes_html"], "<p>PRD-9: n</p>")

	def test_notes_escape_html(self):
		rows = [{"product": "PRD-2", "series": "Ode", "note": 'a<b & "c"'}]
		self.assertEqual(
			build(products_used=rows)["product_notes_html"],
			"<p>Ode &lt;Pro&gt;: a&lt;b &amp; &quot;c&quot;</p>",
		)

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
