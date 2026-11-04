"""Pins the ilL-Webflow-Product form tidy-up (hardening plan 5.9)."""

import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DOCTYPES = os.path.join(HERE, "..", "..", "illumenate_lighting", "illumenate_lighting", "doctype")


def load(folder):
	with open(os.path.join(DOCTYPES, folder, folder + ".json"), encoding="utf-8") as handle:
		return json.load(handle)


def fields(doc):
	return {field["fieldname"]: field for field in doc["fields"]}


SOURCE_LINKS = {
	"fixture_template": "doc.product_type=='Fixture Template'",
	"driver_spec": "doc.product_type=='Driver'",
	"driver_template": "doc.product_type=='Driver'",
	"controller_spec": "doc.product_type=='Controller'",
	"controller_template": "doc.product_type=='Controller'",
	"profile_spec": "['Component', 'Extrusion Kit'].includes(doc.product_type)",
	"lens_spec": "doc.product_type=='Component'",
	"tape_neon_template": "in_list(['LED Tape','COB Tape','LED Neon'], doc.product_type)",
	"led_sheet_template": "doc.product_type=='LED Sheet'",
	"kit_template": "doc.product_type=='Extrusion Kit'",
	"accessory_spec": "in_list(['Accessory','Component'], doc.product_type)",
}


class WebflowProductSchema(unittest.TestCase):
	def setUp(self):
		self.product = load("ill_webflow_product")
		self.fields = fields(self.product)

	def test_deprecated_tape_spec_shows_only_when_it_holds_a_value(self):
		field = self.fields["tape_spec"]
		self.assertEqual(field["depends_on"], "eval:doc.tape_spec")
		self.assertFalse(field.get("hidden"))
		self.assertEqual(field.get("read_only"), 1)
		self.assertEqual(field["options"], "ilL-Spec-LED Tape")

	def test_source_links_collapse_by_product_type_but_keep_legacy_values_visible(self):
		for name, relevant in SOURCE_LINKS.items():
			with self.subTest(field=name):
				self.assertEqual(self.fields[name]["depends_on"], f"eval:{relevant} || doc.{name}")
				self.assertFalse(self.fields[name].get("hidden"))

	def test_sync_and_publication_status_fields_are_read_only(self):
		for name in ("sync_targets", "last_synced_at", "sync_status", "sync_error_message"):
			with self.subTest(field=name):
				self.assertEqual(self.fields[name].get("read_only"), 1)
		state = fields(load("ill_child_webflow_sync_state"))
		for name in ("sync_status", "webflow_item_id", "webflow_collection_slug", "last_synced_at", "sync_error_message"):
			with self.subTest(child_field=name):
				self.assertEqual(state[name].get("read_only"), 1)
		self.assertEqual(state["sync_status"]["options"].split("\n"), ["Never Synced", "Pending", "Synced", "Error"])

	def test_tidy_up_is_additive(self):
		self.assertGreaterEqual(self.product["modified"], "2026-11-20 10:00:00.000000")
		self.assertGreaterEqual(load("ill_child_webflow_sync_state")["modified"], "2026-11-20 10:00:00.000000")
		for name in (*SOURCE_LINKS, "tape_spec", "portal_item"):
			self.assertIn(name, self.fields)
			self.assertIn(name, self.product["field_order"])


if __name__ == "__main__":
	unittest.main()
