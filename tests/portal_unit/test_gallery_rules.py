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
			"videos", "custom_items", "target_brands", "sync_targets",
		}
		self.assertEqual(expected, {n for n, f in fields.items() if f["fieldtype"] not in (
			"Section Break", "Column Break", "Tab Break")})
		self.assertEqual(fields["about"]["description"],
			"Information about the space, the intended lighting and the mood")
		self.assertEqual(fields["sync_targets"]["read_only"], 1)
		self.assertEqual(fields["sync_targets"]["options"], "ilL-Child-Webflow-Sync-State")
		self.assertEqual(fields["target_brands"]["options"], "ilL-Child-Webflow-Brand-Target")
		self.assertEqual(fields["custom_items"]["options"], "ilL-Child-Gallery-Custom-Item")

	def test_custom_item_child(self):
		doc = load_doctype("ill_child_gallery_custom_item")
		self.assertEqual(doc["istable"], 1)
		fields = {f["fieldname"]: f for f in doc["fields"]}
		self.assertEqual(fields["item_name"]["reqd"], 1)
		self.assertEqual(fields["detail"]["fieldtype"], "Small Text")
		self.assertEqual(fields["image"]["fieldtype"], "Attach Image")


if __name__ == "__main__":
	unittest.main()
