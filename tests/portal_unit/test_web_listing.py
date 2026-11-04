"""Product Data fields and Product Status on the six product templates."""

import json
import unittest
from pathlib import Path

from test_services import ROOT, load_service

from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	CONFIGURATOR_TABLE,
	IDENTITY_RIGHT,
	PLACED_FIELDS,
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

	def test_product_status_is_stamped_and_is_active_is_read_only(self):
		# Placement is the identity layout (test_identity_section_layout).
		for module in TEMPLATE_DOCTYPES.values():
			fields = {field["fieldname"]: field for field in doctype_json(module)["fields"]}
			self.assertEqual(fields["product_status"], STATUS_FIELD)
			self.assertEqual(fields["is_active"]["read_only"], 1)

	def test_marketing_fields_stay_off_the_templates(self):
		# Target Brands moved to the template (D10, D22); marketing copy stays on the product.
		for doctype in TEMPLATE_DOCTYPES:
			names = {field["fieldname"] for field in fields_for(doctype)}
			for marketing in ("web_slug", "short_description", "gallery_images", "documents"):
				self.assertNotIn(marketing, names)

	def test_every_template_owns_its_listing_data(self):
		for doctype, module in TEMPLATE_DOCTYPES.items():
			with self.subTest(doctype=doctype):
				fields = doctype_json(module)["fields"]
				names = [field["fieldname"] for field in fields]
				by_name = {field["fieldname"]: field for field in fields}
				tab = names.index(TAB)
				for fieldname, child in {
					"certifications": "ilL-Child-Spec-Certification",
					"specifications": "ilL-Child-Webflow-Spec-Custom",
					"other_documents": "ilL-Child-Webflow-Document",
					"target_brands": "ilL-Child-Webflow-Brand-Target",
				}.items():
					self.assertEqual(by_name[fieldname]["options"], child)
				for fieldname in (
					"dimensions_image",
					"spec_sheet_public_url",
					"specifications",
					"certifications",
				):
					self.assertGreater(names.index(fieldname), tab, fieldname)
				# Spec Sheet Public URL sits right under Dimensions Image (owner layout).
				self.assertEqual(names[names.index("dimensions_image") + 1], "spec_sheet_public_url")
				self.assertEqual(by_name["spec_sheet_public_url"]["read_only"], 1)
				# Other Documents sits above the tab, right after its anchor in the template's layout.
				anchor = dict((f["fieldname"], a) for f, a in PLACED_FIELDS[doctype])["other_documents"]
				self.assertLess(names.index("other_documents"), tab)
				self.assertEqual(names[names.index(anchor) + 1], "other_documents")
				self.assertEqual("webflow_category" in names, doctype == "ilL-Tape-Neon-Template")
				configurator = by_name[CONFIGURATOR_TABLE[doctype]]
				self.assertEqual(configurator["options"], "ilL-Child-Webflow-Configurator-Option")
				self.assertGreater(names.index(configurator["fieldname"]), tab)

	def test_identity_section_layout(self):
		for doctype, module in TEMPLATE_DOCTYPES.items():
			with self.subTest(doctype=doctype):
				fields = doctype_json(module)["fields"]
				end = next(
					i
					for i in range(1, len(fields))
					if fields[i]["fieldtype"] in ("Section Break", "Tab Break")
				)
				section = [f["fieldname"] if f["fieldtype"] != "Column Break" else "|" for f in fields[1:end]]
				self.assertEqual(
					section[:5], ["template_code", "template_name", "product_status", "sublabel", "|"]
				)
				right = [name for name in section[5:] if name in IDENTITY_RIGHT]
				self.assertEqual(right, [name for name in IDENTITY_RIGHT if name in section])

	def test_weight_sits_in_spec_sheet_details_where_the_template_has_it(self):
		for doctype, module in TEMPLATE_DOCTYPES.items():
			names = [f["fieldname"] for f in doctype_json(module)["fields"]]
			if "fixture_weight_per_foot_grams" not in names:
				continue
			with self.subTest(doctype=doctype):
				at = names.index("fixture_weight_per_foot_grams")
				if "spec_sheet_details_section" in names:
					self.assertLess(names.index("spec_sheet_details_section"), at)
					self.assertLess(at, names.index(TAB))
				else:
					self.assertGreater(at, names.index(TAB))

	def test_fixture_keeps_its_part_number_sections_beside_the_configurator(self):
		fields = {f["fieldname"]: f for f in doctype_json("ill_fixture_template")["fields"]}
		self.assertEqual(fields["part_number_builder"]["options"], "ilL-Child-PN-Builder-Row")
		self.assertEqual(set(CONFIGURATOR_TABLE.values()), {"part_no_configurator"})

	def test_product_data_tab_layout(self):
		for doctype, module in TEMPLATE_DOCTYPES.items():
			with self.subTest(doctype=doctype):
				fields = doctype_json(module)["fields"]
				start = [f["fieldname"] for f in fields].index(TAB)
				sections = [f["label"] for f in fields[start:] if f["fieldtype"] == "Section Break"]
				self.assertEqual(
					sections[:3], ["Product Data", "Specifications & Certifications", "Configurator"]
				)
				first = fields[start + 2 : [f["fieldname"] for f in fields].index("web_specs_certs_section")]
				self.assertEqual(sum(f["fieldtype"] == "Column Break" for f in first), 1)
				self.assertIn("dimensions_image", {f["fieldname"] for f in first})

	def test_webflow_product_is_editable_only_while_empty(self):
		for module in TEMPLATE_DOCTYPES.values():
			field = next(f for f in doctype_json(module)["fields"] if f["fieldname"] == "webflow_product")
			self.assertEqual(field["options"], "ilL-Webflow-Product")
			self.assertFalse(field.get("read_only"))
			self.assertEqual(field["read_only_depends_on"], "eval:doc.webflow_product")

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
		self.assertEqual(
			apply(Doc(before, product_status="Internal Only", is_active=1)), ("Internal Only", 1)
		)
		self.assertEqual(apply(Doc(before, product_status="Discontinued", is_active=1)), ("Discontinued", 0))
		self.assertEqual(apply(Doc(product_status="Draft", is_active=1)), ("Draft", 0))

	def test_code_that_only_flips_is_active_moves_the_status(self):
		active = {"product_status": "Internal Only", "is_active": 1}
		self.assertEqual(apply(Doc(active, product_status="Internal Only", is_active=0)), ("Draft", 0))
		archived = {"product_status": "Archived", "is_active": 0}
		self.assertEqual(apply(Doc(archived, product_status="Archived", is_active=1)), ("Active", 1))

	def test_active_live_is_an_active_status(self):
		before = {"product_status": "Active", "is_active": 1}
		self.assertEqual(
			apply(Doc(before, product_status="Active + Live", is_active=1)), ("Active + Live", 1)
		)
		self.assertEqual(apply(Doc(product_status="Active + Live", is_active=1)), ("Active + Live", 1))

	def test_an_untouched_inactive_status_is_kept(self):
		before = {"product_status": "Archived", "is_active": 0}
		self.assertEqual(apply(Doc(before, product_status="Archived", is_active=0)), ("Archived", 0))


if __name__ == "__main__":
	unittest.main()
