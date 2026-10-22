"""Product Data fields and Product Status on the six product templates."""

import json
import unittest
from pathlib import Path

from test_services import ROOT, load_service

from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	PREEXISTING,
	STATUS_FIELD,
	TAB,
	TEMPLATE_DOCTYPES,
	fields_for,
)

DOCTYPES = Path("illumenate_lighting/illumenate_lighting/doctype")


def doctype_json(module):
	return json.loads((DOCTYPES / module / f"{module}.json").read_text(encoding="utf-8"))


def module_for(doctype):
	return doctype.lower().replace("-", "_").replace(" ", "_")


class StampedSchema(unittest.TestCase):
	def test_every_template_carries_the_stamped_fields_after_its_own(self):
		for doctype, module in TEMPLATE_DOCTYPES.items():
			with self.subTest(doctype=doctype):
				fields = doctype_json(module)["fields"]
				names = [field["fieldname"] for field in fields]
				self.assertEqual(len(names), len(set(names)), "duplicate fieldnames")
				start = names.index(TAB)
				self.assertEqual(fields[start:], fields_for(doctype), "run tools/stamp_web_listing_fields.py")
				self.assertTrue(PREEXISTING[doctype] <= set(names[:start]))

	def test_field_order_matches_fields(self):
		for module in TEMPLATE_DOCTYPES.values():
			data = doctype_json(module)
			self.assertEqual(data["field_order"], [field["fieldname"] for field in data["fields"]])

	def test_product_status_follows_is_active_which_is_read_only(self):
		for module in TEMPLATE_DOCTYPES.values():
			fields = doctype_json(module)["fields"]
			names = [field["fieldname"] for field in fields]
			at = names.index("is_active")
			self.assertEqual(fields[at + 1], STATUS_FIELD)
			self.assertEqual(fields[at]["read_only"], 1)

	def test_marketing_fields_stay_off_the_templates(self):
		for doctype in TEMPLATE_DOCTYPES:
			names = {field["fieldname"] for field in fields_for(doctype)}
			for marketing in (
				"web_slug",
				"short_description",
				"gallery_images",
				"documents",
				"target_brands",
			):
				self.assertNotIn(marketing, names)

	def test_tables_and_links_point_at_existing_doctypes(self):
		core = {"Item", "DocType"}
		for doctype in TEMPLATE_DOCTYPES:
			for field in fields_for(doctype):
				if field["fieldtype"] in ("Table", "Link") and field["options"] not in core:
					module = module_for(field["options"])
					self.assertTrue((DOCTYPES / module / f"{module}.json").exists(), field["options"])

	def test_publication_records_can_point_at_a_listing(self):
		for module in ("ill_product_publication", "ill_publish_job", "ill_product_verification_request"):
			fields = {field["fieldname"]: field for field in doctype_json(module)["fields"]}
			self.assertEqual(fields["listing_doctype"]["options"], "DocType")
			self.assertEqual(fields["listing_name"]["fieldtype"], "Dynamic Link")
			self.assertEqual(fields["listing_name"]["options"], "listing_doctype")


class Doc(dict):
	"""A template as validate() sees it: values now, and the values before this save."""

	def __init__(self, before=None, **values):
		super().__init__(values)
		self.before = before

	__getattr__ = dict.get

	def __setattr__(self, key, value):
		if key == "before":
			object.__setattr__(self, key, value)
		else:
			self[key] = value

	def get_doc_before_save(self):
		return self.before


def apply(doc):
	with load_service(ROOT + ".web_listing") as (module, _frappe):
		module.apply_product_status(doc)
	return doc.product_status, doc.is_active


class ProductStatus(unittest.TestCase):
	def test_a_new_template_without_a_status_starts_internal_only(self):
		self.assertEqual(apply(Doc(is_active=1)), ("Internal Only", 1))
		self.assertEqual(apply(Doc(is_active=0)), ("Draft", 0))

	def test_a_new_inactive_template_is_not_made_active_by_the_status_default(self):
		self.assertEqual(apply(Doc(product_status="Internal Only", is_active=0)), ("Draft", 0))
		self.assertEqual(apply(Doc(product_status="Active", is_active=0)), ("Draft", 0))
		self.assertEqual(apply(Doc(product_status="Internal Only", is_active=1)), ("Internal Only", 1))
		self.assertEqual(apply(Doc(product_status="Active", is_active=1)), ("Active", 1))

	def test_a_chosen_status_sets_is_active(self):
		before = {"product_status": "Active", "is_active": 1}
		self.assertEqual(apply(Doc(before, product_status="Internal Only", is_active=1)), ("Internal Only", 1))
		self.assertEqual(apply(Doc(before, product_status="Discontinued", is_active=1)), ("Discontinued", 0))
		self.assertEqual(apply(Doc(product_status="Draft", is_active=1)), ("Draft", 0))

	def test_code_that_only_flips_is_active_moves_the_status(self):
		active = {"product_status": "Internal Only", "is_active": 1}
		self.assertEqual(apply(Doc(active, product_status="Internal Only", is_active=0)), ("Draft", 0))
		archived = {"product_status": "Archived", "is_active": 0}
		self.assertEqual(apply(Doc(archived, product_status="Archived", is_active=1)), ("Active", 1))

	def test_an_untouched_inactive_status_is_kept(self):
		before = {"product_status": "Archived", "is_active": 0}
		self.assertEqual(apply(Doc(before, product_status="Archived", is_active=0)), ("Archived", 0))


if __name__ == "__main__":
	unittest.main()
