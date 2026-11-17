"""Duplicate as new product / template (plan 5.3) with Frappe boundary doubles."""

import copy
import re
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, load_service

MODULE = ROOT + ".api.product_clone"
LINKS = {
	"ilL-Fixture-Template": "fixture_template",
	"ilL-Tape-Neon-Template": "tape_neon_template",
	"ilL-Controller-Template": "controller_template",
	"ilL-Driver-Template": "driver_template",
	"ilL-Extrusion-Kit-Template": "kit_template",
	"ilL-LED-Sheet-Template": "led_sheet_template",
}
TABLES = {"sync_targets", "compatible_products", "gallery_images", "documents", "allowed_options"}


class Doc:
	def __init__(self, doctype, **values):
		self.doctype = doctype
		self.flags = types.SimpleNamespace()
		self.inserted = False
		self.__dict__.update(values)

	def get(self, key, default=None):
		return self.__dict__.get(key, default)

	def set(self, key, value):
		self.__dict__[key] = value

	def insert(self):
		self.name = self.get("product_slug") if self.doctype == "ilL-Webflow-Product" else self.template_code
		self.inserted = True
		return self


def meta(_doctype):
	def field(name):
		return types.SimpleNamespace(fieldtype="Table" if name in TABLES else "Data", default="Pending" if name == "sync_status" else None)

	return types.SimpleNamespace(has_field=lambda name: name != "image", get_field=field)


def product(**values):
	row = dict(
		name="slim-12",
		product_name="Slim 12",
		product_slug="slim-12",
		is_active=1,
		short_description="Slim channel",
		fixture_template="SLIM-12",
		webflow_item_id="wf-1",
		webflow_collection_slug="products",
		last_synced_at="2026-11-01",
		sync_status="Synced",
		sync_error_message="old",
		sync_targets=[{"brand": "illumenate", "webflow_item_id": "wf-1"}],
		compatible_products=[{"product": "other"}],
		featured_image="/files/slim.jpg",
		gallery_images=[{"image": "/files/g.jpg", "alt_text": "Slim"}],
		documents=[{"document_file": "/files/slim.pdf"}],
		target_brands=[{"brand": "illumenate", "enabled": 1}],
		specifications=[{"attribute": "CCT"}],
	)
	row.update(values)
	return Doc("ilL-Webflow-Product", **row)


def template(**values):
	row = dict(
		name="SLIM-12",
		template_code="SLIM-12",
		template_name="Slim 12",
		is_active=1,
		product_status="Active",
		webflow_product="slim-12",
		hero_image="/files/hero.jpg",
		hero_image_alt="Slim hero",
		spec_sheet="/files/slim.pdf",
		spec_submittal_template="/files/submittal.pdf",
		allowed_options=[{"option_type": "Finish"}],
		base_price_msrp=10,
	)
	row.update(values)
	return Doc("ilL-Fixture-Template", **row)


def names(cell):
	return set(re.findall(r"`([a-z0-9_]+)`", cell)) - {"product_status"}


class Duplicate(unittest.TestCase):
	def run_duplicate(self, records, *args, roles=("ilL Catalog Publisher",), exists=(), **kwargs):
		staff = types.SimpleNamespace(allowed=lambda capability: capability == "catalog" and "ilL Catalog Publisher" in roles)
		schema = types.SimpleNamespace(WEBFLOW_PRODUCT_LINKS=LINKS)
		deps = {ROOT + ".portal.staff": staff, ROOT + ".web_listing_schema": schema}
		with load_service(MODULE, deps) as (module, frappe):
			frappe.get_doc = MagicMock(side_effect=lambda doctype, name: records[(doctype, name)])
			frappe.copy_doc = lambda doc: copy.deepcopy(doc)
			frappe.get_meta = meta
			frappe.db.exists = MagicMock(side_effect=lambda doctype, name: (doctype, name) in exists)
			self.frappe = frappe
			return module.duplicate(*args, **kwargs)

	def test_product_copy_is_an_inactive_draft_without_sync_identity_or_shared_template(self):
		records = {("ilL-Webflow-Product", "slim-12"): product()}
		created = []
		original_insert = Doc.insert
		Doc.insert = lambda self: created.append(self) or original_insert(self)
		try:
			result = self.run_duplicate(records, "ilL-Webflow-Product", "slim-12", "Slim 24", include_media="1")
		finally:
			Doc.insert = original_insert
		self.assertEqual(result, {"doctype": "ilL-Webflow-Product", "name": "slim-24", "readiness": "product"})
		(doc,) = created
		self.assertTrue(doc.flags.in_copy)
		self.assertEqual((doc.product_name, doc.product_slug, doc.is_active), ("Slim 24", "slim-24", 0))
		for field in ("webflow_item_id", "webflow_collection_slug", "last_synced_at", "sync_error_message", "fixture_template"):
			self.assertIsNone(doc.get(field), field)
		self.assertEqual(doc.sync_status, "Pending")
		self.assertEqual((doc.sync_targets, doc.compatible_products), ([], []))
		self.assertEqual(doc.featured_image, "/files/slim.jpg")
		self.assertEqual(len(doc.gallery_images), 1)
		self.assertEqual(doc.target_brands, [{"brand": "illumenate", "enabled": 1}])
		self.assertEqual(doc.specifications, [{"attribute": "CCT"}])
		source = records[("ilL-Webflow-Product", "slim-12")]
		self.assertEqual((source.webflow_item_id, source.fixture_template, source.is_active), ("wf-1", "SLIM-12", 1))

	def test_skipping_media_clears_images_gallery_and_documents(self):
		records = {("ilL-Webflow-Product", "slim-12"): product()}
		created = []
		original_insert = Doc.insert
		Doc.insert = lambda self: created.append(self) or original_insert(self)
		try:
			self.run_duplicate(records, "ilL-Webflow-Product", "slim-12", "Slim 24", "slim-24-v2", include_media="0")
		finally:
			Doc.insert = original_insert
		doc = created[0]
		self.assertEqual(doc.product_slug, "slim-24-v2")
		self.assertIsNone(doc.featured_image)
		self.assertEqual((doc.gallery_images, doc.documents), ([], []))

	def test_product_can_copy_its_family_template_and_links_the_copy(self):
		records = {("ilL-Webflow-Product", "slim-12"): product(), ("ilL-Fixture-Template", "SLIM-12"): template()}
		result = self.run_duplicate(records, "ilL-Webflow-Product", "slim-12", "Slim 24", template_code="SLIM-24", include_media=0)
		self.assertEqual(result["template"], {"doctype": "ilL-Fixture-Template", "name": "SLIM-24"})

	def test_template_copy_is_a_draft_without_back_link(self):
		records = {("ilL-Fixture-Template", "SLIM-12"): template()}
		created = []
		original_insert = Doc.insert
		Doc.insert = lambda self: created.append(self) or original_insert(self)
		try:
			result = self.run_duplicate(records, "ilL-Fixture-Template", "SLIM-12", "SLIM-24", include_media="false", template_name="Slim 24")
		finally:
			Doc.insert = original_insert
		self.assertEqual(result, {"doctype": "ilL-Fixture-Template", "name": "SLIM-24", "readiness": "template"})
		doc = created[0]
		self.assertEqual((doc.template_code, doc.template_name, doc.product_status), ("SLIM-24", "Slim 24", "Draft"))
		self.assertIsNone(doc.webflow_product)
		self.assertIsNone(doc.is_active)
		self.assertIsNone(doc.hero_image)
		self.assertIsNone(doc.spec_sheet)
		self.assertEqual(doc.spec_submittal_template, "/files/submittal.pdf")
		self.assertEqual(doc.allowed_options, [{"option_type": "Finish"}])
		self.assertEqual(doc.base_price_msrp, 10)

	def test_name_collisions_bad_input_and_missing_template_are_refused(self):
		records = {("ilL-Webflow-Product", "slim-12"): product(fixture_template=None), ("ilL-Fixture-Template", "SLIM-12"): template()}
		with self.assertRaisesRegex(ValueError, "already exists"):
			self.run_duplicate(records, "ilL-Webflow-Product", "slim-12", "Slim 12", exists={("ilL-Webflow-Product", "slim-12")})
		with self.assertRaisesRegex(ValueError, "already exists"):
			self.run_duplicate(records, "ilL-Fixture-Template", "SLIM-12", "SLIM-12", exists={("ilL-Fixture-Template", "SLIM-12")})
		with self.assertRaisesRegex(ValueError, "new product name"):
			self.run_duplicate(records, "ilL-Webflow-Product", "slim-12", "  ")
		with self.assertRaisesRegex(ValueError, "template code"):
			self.run_duplicate(records, "ilL-Fixture-Template", "SLIM-12", "<b>")
		with self.assertRaisesRegex(ValueError, "no family template"):
			self.run_duplicate(records, "ilL-Webflow-Product", "slim-12", "Slim 24", template_code="SLIM-24")
		with self.assertRaisesRegex(ValueError, "can be duplicated"):
			self.run_duplicate(records, "Item", "X", "Y")

	def test_requires_catalog_role_and_create_permission(self):
		records = {("ilL-Webflow-Product", "slim-12"): product()}
		with self.assertRaises(PermissionError):
			self.run_duplicate(records, "ilL-Webflow-Product", "slim-12", "Slim 24", roles=("Dealer",))
		staff = types.SimpleNamespace(allowed=lambda capability: True)
		deps = {ROOT + ".portal.staff": staff, ROOT + ".web_listing_schema": types.SimpleNamespace(WEBFLOW_PRODUCT_LINKS=LINKS)}
		with load_service(MODULE, deps) as (module, frappe):
			frappe.has_permission = MagicMock(return_value=False)
			with self.assertRaises(PermissionError):
				module.duplicate("ilL-Webflow-Product", "slim-12", "Slim 24")
		self.assertEqual(module.duplicate.whitelist_options, {"methods": ["POST"]})

	def test_field_register_lists_exactly_the_cleared_fields(self):
		with load_service(MODULE, {ROOT + ".portal.staff": types.SimpleNamespace(allowed=MagicMock()), ROOT + ".web_listing_schema": types.SimpleNamespace(WEBFLOW_PRODUCT_LINKS=LINKS)}) as (module, _frappe):
			register = Path(__file__).resolve().parents[2] / "docs" / "B2B_AUTHORING_FIELD_REGISTER.md"
			rows = {line.split("|")[1].strip(): line.split("|")[2:4] for line in register.read_text().splitlines() if line.startswith(("| Webflow Product |", "| Family template |"))}
			self.assertEqual(names(rows["Webflow Product"][0]), set(module.PRODUCT_EXCLUDES))
			self.assertEqual(names(rows["Webflow Product"][1]), set(module.PRODUCT_MEDIA))
			self.assertEqual(names(rows["Family template"][0]), set(module.TEMPLATE_EXCLUDES))
			self.assertEqual(names(rows["Family template"][1]), set(module.TEMPLATE_MEDIA))


if __name__ == "__main__":
	unittest.main()
