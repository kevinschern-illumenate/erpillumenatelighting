"""Pure validation rules for ilL-Webflow-Gallery (no Frappe needed)."""

import json
import unittest
from pathlib import Path

from illumenate_lighting.illumenate_lighting.api import gallery_schema as schema
from illumenate_lighting.illumenate_lighting.api.gallery_rules import validate_gallery

DOCTYPES = Path(__file__).resolve().parents[2] / "illumenate_lighting" / "illumenate_lighting" / "doctype"


def load_doctype(folder):
	return json.loads((DOCTYPES / folder / f"{folder}.json").read_text())


def gallery(**overrides):
	doc = {
		"slug": "ode-wellness",
		"credits": [{"credit_type": "Integrator", "credit_name": "Acme"}],
	}
	doc.update(overrides)
	return doc


def check(doc, slug_locked=False, slug_taken=False):
	return validate_gallery(doc, slug_locked=slug_locked, slug_taken=slug_taken)


class ValidateGalleryTest(unittest.TestCase):
	def test_valid_gallery_has_no_errors(self):
		self.assertEqual(check(gallery()), [])

	def test_slug_must_match_re(self):
		for bad in ("Ode", "a b", "a_b", "", None, "ode-wellness\n", "-a"):
			self.assertTrue(check(gallery(slug=bad)), repr(bad))

	def test_duplicate_credit_type_rejected(self):
		credits = [
			{"credit_type": "Integrator", "credit_name": "A"},
			{"credit_type": "Integrator", "credit_name": "B"},
		]
		errors = check(gallery(credits=credits))
		self.assertEqual(len(errors), 1)
		self.assertIn("Integrator", errors[0])

	def test_slug_locked_after_stage(self):
		doc = gallery(slug="new-slug", _old_slug="ode-wellness")
		self.assertTrue(check(doc, slug_locked=True))
		self.assertEqual(check(doc, slug_locked=False), [])
		same = gallery(slug="ode-wellness", _old_slug="ode-wellness")
		self.assertEqual(check(same, slug_locked=True), [])

	def test_slug_taken_rejected(self):
		self.assertTrue(check(gallery(), slug_taken=True))

	def test_first_image_is_hero_note_not_a_field(self):
		fields = {f["fieldname"]: f for f in load_doctype("ill_webflow_gallery")["fields"]}
		self.assertNotIn("hero_image", fields)
		self.assertIn("first row", fields["gallery_images"]["description"])


class DoctypeJsonTest(unittest.TestCase):
	def test_gallery_type_options_match_constant(self):
		fields = {f["fieldname"]: f for f in load_doctype("ill_webflow_gallery")["fields"]}
		self.assertEqual(fields["gallery_type"]["options"], "\n".join(schema.GALLERY_TYPES))

	def test_doctype_shape(self):
		doc = load_doctype("ill_webflow_gallery")
		self.assertEqual(doc["autoname"], "field:slug")
		fields = {f["fieldname"]: f for f in doc["fields"]}
		expected = {
			"gallery_title", "slug", "is_active", "featured", "gallery_images", "seo_description",
			"about", "case_study", "gallery_type", "applications", "services_provided",
			"products_used", "quote", "quote_attribution", "location", "completion_date", "credits",
			"videos", "custom_items", "target_brands", "sync_targets", "status_guide",
			"publication_status",
		}
		self.assertEqual(expected, {n for n, f in fields.items() if f["fieldtype"] not in (
			"Section Break", "Column Break", "Tab Break")})
		self.assertEqual(fields["about"]["description"],
			"Information about the space, the intended lighting and the mood")
		self.assertEqual(fields["sync_targets"]["read_only"], 1)
		self.assertEqual(fields["sync_targets"]["options"], "ilL-Child-Webflow-Sync-State")
		self.assertEqual(fields["target_brands"]["options"], "ilL-Child-Webflow-Brand-Target")
		self.assertEqual(fields["custom_items"]["options"], "ilL-Child-Gallery-Custom-Item")

	def test_status_guide_is_a_collapsed_section_at_the_bottom(self):
		doc = load_doctype("ill_webflow_gallery")
		fields = {f["fieldname"]: f for f in doc["fields"]}
		self.assertEqual(doc["field_order"][-2:], ["status_guide_section", "status_guide"])
		self.assertEqual(fields["status_guide_section"]["fieldtype"], "Section Break")
		self.assertEqual(fields["status_guide_section"]["collapsible"], 1)
		self.assertEqual(fields["status_guide"]["fieldtype"], "HTML")
		guide = fields["status_guide"]["options"]
		# Every status the pill can show is explained, and the template has no placeholders to render.
		for label in ("Needs staging", "Changes not staged", "Queued", "Staged", "Live", "Failed", "Retired"):
			self.assertIn(">" + label + "<", guide)
		self.assertNotIn("{", guide)

	def test_custom_item_child(self):
		doc = load_doctype("ill_child_gallery_custom_item")
		self.assertEqual(doc["istable"], 1)
		fields = {f["fieldname"]: f for f in doc["fields"]}
		self.assertEqual(fields["item_name"]["reqd"], 1)
		self.assertEqual(fields["detail"]["fieldtype"], "Small Text")
		self.assertEqual(fields["image"]["fieldtype"], "Attach Image")


if __name__ == "__main__":
	unittest.main()


class PublicationStatusTest(unittest.TestCase):
	def test_field_options_match_the_constant(self):
		fields = {f["fieldname"]: f for f in load_doctype("ill_webflow_gallery")["fields"]}
		field = fields["publication_status"]
		self.assertEqual(set(field["options"].split("\n")), set(schema.PUBLICATION_STATUSES))
		self.assertEqual(field["default"], schema.DEFAULT_PUBLICATION_STATUS)
		self.assertEqual((field["read_only"], field["in_list_view"], field["in_standard_filter"]), (1, 1, 1))

	def test_one_record_maps_like_the_sidebar_pill(self):
		status = schema.publication_status
		self.assertEqual(status("QUEUED"), "Queued")
		self.assertEqual(status("STAGED"), "Staged")
		self.assertEqual(status("LIVE"), "Live")
		self.assertEqual(status("FAILED"), "Failed")
		self.assertEqual(status("RETIRED"), "Retired")
		self.assertEqual(status("NEEDS_REVIEW"), "Needs staging")
		self.assertEqual(status("NEEDS_REVIEW", staged_hash="a"), "Changes not staged")
		self.assertEqual(status("READY", live_hash="a"), "Changes not staged")

	def test_no_record_means_needs_staging(self):
		self.assertEqual(schema.gallery_status([]), "Needs staging")

	def test_several_brands_show_the_one_needing_attention(self):
		live = {"state": "LIVE"}
		self.assertEqual(schema.gallery_status([live, {"state": "FAILED"}]), "Failed")
		stale = {"state": "NEEDS_REVIEW", "live_hash": "a"}
		self.assertEqual(schema.gallery_status([live, stale]), "Changes not staged")
		self.assertEqual(schema.gallery_status([live, {"state": "STAGED"}]), "Staged")
		self.assertEqual(schema.gallery_status([live, live]), "Live")


class FormLayoutTest(unittest.TestCase):
	def setUp(self):
		doc = load_doctype("ill_webflow_gallery")
		self.order = doc["field_order"]
		self.fields = {f["fieldname"]: f for f in doc["fields"]}

	def between(self, field, start, end):
		return self.order.index(start) < self.order.index(field) < self.order.index(end)

	def test_status_sits_under_the_title(self):
		self.assertEqual(self.order[self.order.index("gallery_title") + 1], "publication_status")

	def test_location_and_date_are_in_identity(self):
		for name in ("location", "completion_date"):
			self.assertTrue(self.between(name, "identity_section", "images_section"), name)

	def test_videos_are_in_images(self):
		self.assertTrue(self.between("videos", "images_section", "content_section"))

	def test_quote_follows_the_case_study_and_details_is_gone(self):
		i = self.order.index("case_study")
		self.assertEqual(self.order[i + 1 : i + 3], ["quote", "quote_attribution"])
		self.assertNotIn("details_section", self.order)
		self.assertNotIn("column_break_details", self.fields)

	def test_descriptions(self):
		self.assertEqual(self.fields["quote_attribution"]["description"], "Full Name, Company")
		self.assertEqual(
			self.fields["videos"]["description"],
			"Optional. One or more video links, separated by commas or new lines. YouTube, Vimeo, Loom, "
			"or a direct .mp4 link. Shown in the gallery strip and lightbox.",
		)

	def test_every_field_is_still_in_the_order_once(self):
		self.assertEqual(sorted(self.order), sorted(self.fields))
