"""Web Listing fields on the six product templates (Webflow Product merge, step 2)."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from test_services import ROOT, load_service

from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	PREEXISTING,
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

	def test_tab_stays_hidden_until_cutover(self):
		for doctype in TEMPLATE_DOCTYPES:
			self.assertEqual(fields_for(doctype)[0], {**fields_for(doctype)[0], "hidden": 1})

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


def template(**values):
	doc = SimpleNamespace(doctype="ilL-Fixture-Template", name="ILL-EL01-SW", web_listed=0, web_slug=None)
	doc.__dict__.update(values)
	doc.get = lambda key: getattr(doc, key, None)
	return doc


class Row(dict):
	__getattr__ = dict.get


class SlugValidation(unittest.TestCase):
	def validate(self, doc, owners=None, linked=None, product=None):
		"""``product`` is the exact name of the Webflow Product the slug finds, if any."""
		owners = owners or {}
		with load_service(ROOT + ".web_listing") as (module, frappe):

			def get_value(doctype, filters, fieldname, as_dict=False):
				if doctype == "ilL-Webflow-Product":
					if as_dict:
						return Row(name=product, fixture_template=linked) if product else None
					return linked
				return owners.get(doctype)

			frappe.db.get_value.side_effect = get_value
			module.validate_web_listing(doc)
		return doc

	def test_slug_is_normalised(self):
		self.assertEqual(self.validate(template(web_slug="  ILL-EL01-SW ")).web_slug, "ill-el01-sw")

	def test_capitals_of_its_own_webflow_product_are_kept(self):
		doc = template(name="NON-SCM-SW", web_slug="non-scX-sw")
		self.assertEqual(self.validate(doc, linked="NON-SCM-SW", product="non-scX-sw").web_slug, "non-scX-sw")

	def test_capitals_are_lowercased_when_the_product_is_not_its_own(self):
		doc = template(name="NON-SCM-SW", web_slug="non-scX-sw")
		self.assertEqual(self.validate(doc, linked=None, product="non-scX-sw").web_slug, "non-scx-sw")

	def test_blank_slug_is_stored_as_null(self):
		self.assertIsNone(self.validate(template(web_slug="  ")).web_slug)

	def test_listing_requires_a_slug(self):
		with self.assertRaisesRegex(ValueError, "Set a Web Slug"):
			self.validate(template(web_listed=1))

	def test_malformed_slug_is_rejected(self):
		for slug in ("ill el01", "ill--el01", "-ill", "ill_el01"):
			with self.subTest(slug=slug), self.assertRaisesRegex(ValueError, "lowercase"):
				self.validate(template(web_slug=slug))

	def test_slug_must_be_unique_across_templates(self):
		with self.assertRaisesRegex(ValueError, "already used by ilL-Driver-Template FLRA-PWR"):
			self.validate(template(web_slug="flra-pwr"), owners={"ilL-Driver-Template": "FLRA-PWR"})

	def test_slug_of_a_product_linked_elsewhere_is_rejected(self):
		with self.assertRaisesRegex(ValueError, "linked to ILL-EL01-FS"):
			self.validate(template(web_slug="ill-el01-sw"), linked="ILL-EL01-FS")

	def test_unlinked_or_own_webflow_product_is_accepted(self):
		for linked in (None, "ILL-EL01-SW"):
			with self.subTest(linked=linked):
				self.assertEqual(
					self.validate(template(web_slug="ill-el01-sw"), linked=linked).web_slug, "ill-el01-sw"
				)


if __name__ == "__main__":
	unittest.main()
