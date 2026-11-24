"""Production Linear Fixture readiness (docs/superpowers/specs/2026-11-24-production-fixture-readiness-design.md).

On production the catalog data sits on the Webflow Product; the spec sheet and the sync read
the template. ``carry_listing_fields`` copies it onto empty template fields; the Fixture
Readiness report lists what each template still needs.
"""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

FIXTURE = "ilL-Fixture-Template"
FIELDS = {"sublabel", "dimensions_image", "hero_image", "certifications"}


def product(**values):
	return {
		"name": "ill-sh01-sw",
		"fixture_template": "ILL-SH01-SW",
		"sublabel": "Surface",
		"featured_image": "/files/SH01_LIT.jpg",
		"dimensions_image": "/files/SH01_Dims_Web.svg",
		"certifications": [
			{"certification": "Wet Rated", "display_order": 4},
			{"certification": "Dry Rated", "display_order": 2},
			{"certification": "Damp Rated", "display_order": 3},
			{"certification": "24V DC", "display_order": 1},
		],
		**values,
	}


def template(**values):
	return {"name": "ILL-SH01-SW", "webflow_product": "ill-sh01-sw", **values}


class PlanCarry(unittest.TestCase):
	def plan(self, listing, tpl, fields=FIELDS):
		with load_service(ROOT + ".web_listing_migration") as (module, _frappe):
			return module.plan_carry(listing, tpl, fields)

	def test_fills_empty_template_fields_from_the_product(self):
		values, tables, notes, review = self.plan(product(), template())
		self.assertEqual(
			values,
			{
				"sublabel": "Surface",
				"dimensions_image": "/files/SH01_Dims_Web.svg",
				"hero_image": "/files/SH01_LIT.jpg",
			},
		)
		# In the product's display order; the badge image fills itself in on the template's save.
		self.assertEqual(
			tables,
			{
				"certifications": [
					{"certification": c} for c in ("24V DC", "Dry Rated", "Damp Rated", "Wet Rated")
				]
			},
		)
		self.assertEqual(notes, [])
		self.assertEqual(review, ["hero_image is the product's featured image: check it"])

	def test_never_overwrites_a_template_value(self):
		values, tables, notes, review = self.plan(
			product(),
			template(
				sublabel="Surface Mount",
				hero_image="/files/SH01_ASSEMBLED.jpg",
				dimensions_image="/files/SH01_Dims_Web.svg",
				certifications=[{"certification": "Dry Rated"}],
			),
		)
		self.assertEqual((values, tables, review), ({}, {}, []))
		self.assertIn("sublabel kept as 'Surface Mount'; product has 'Surface'", notes)
		self.assertIn("certifications kept: template already has 1 rows", notes)
		# The same value, or a hero image the product's featured image differs from, is no conflict.
		self.assertFalse(any("dimensions_image" in note or "hero_image" in note for note in notes))

	def test_empty_product_values_carry_nothing(self):
		values, tables, notes, review = self.plan(
			product(sublabel="", featured_image=None, dimensions_image=None, certifications=[]), template()
		)
		self.assertEqual((values, tables, notes, review), ({}, {}, [], []))

	def test_only_fields_the_template_type_has(self):
		values, tables, _notes, review = self.plan(product(), template(), fields={"sublabel"})
		self.assertEqual((values, tables, review), ({"sublabel": "Surface"}, {}, []))


class CarryListingFields(unittest.TestCase):
	"""The whitelisted run: dry run by default, writes only with dry_run=0, scope respected."""

	def setUp(self):
		context = load_service(ROOT + ".web_listing_migration")
		self.module, self.frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		self.frappe.only_for = MagicMock()
		self.frappe.db.set_value = MagicMock()
		self.frappe.db.savepoint = MagicMock()
		self.frappe.db.commit = MagicMock()
		self.inserted = []
		self.templates = {
			"ILL-SH01-SW": template(),
			"ILL-NOLINK": {"name": "ILL-NOLINK", "webflow_product": None},
			"ILL-OTHER": {"name": "ILL-OTHER", "webflow_product": "ill-other"},
		}
		self.products = {
			"ill-sh01-sw": product(),
			"ill-other": product(name="ill-other", fixture_template="ILL-ELSE"),
		}

		def get_all(doctype, **kwargs):
			return sorted(self.templates) if doctype == FIXTURE else []

		def get_doc(arg, name=None):
			if isinstance(arg, dict):
				row = Record(arg)
				row["db_insert"] = lambda: self.inserted.append(dict(arg))
				return row
			data = self.templates.get(name) if arg == FIXTURE else self.products.get(name)
			return Record(as_dict=lambda: dict(data))

		self.frappe.get_all = MagicMock(side_effect=get_all)
		self.frappe.get_doc = MagicMock(side_effect=get_doc)
		self.frappe.db.exists = MagicMock(side_effect=lambda doctype, name: name in self.products)
		self.frappe.get_meta = MagicMock(return_value=Record(has_field=lambda field: field in FIELDS))
		self.module.template_doctypes_arg = lambda doctypes=None: [FIXTURE]

	def run_carry(self, dry_run):
		return self.module.carry_listing_fields(dry_run=dry_run)

	def test_dry_run_reports_and_writes_nothing(self):
		report = self.run_carry(1)
		rows = {row["template"]: row for row in report["templates"]}
		self.assertEqual(rows[f"{FIXTURE} ILL-SH01-SW"]["action"], "would carry")
		self.assertEqual(
			rows[f"{FIXTURE} ILL-SH01-SW"]["fields"], ["dimensions_image", "hero_image", "sublabel"]
		)
		self.assertEqual(rows[f"{FIXTURE} ILL-SH01-SW"]["tables"], {"certifications": 4})
		self.assertEqual(report["not_linked"], [f"{FIXTURE} ILL-NOLINK"])
		# A product that links another template does not belong to this one.
		self.assertEqual(rows[f"{FIXTURE} ILL-OTHER"]["action"], "skipped")
		self.frappe.db.set_value.assert_not_called()
		self.assertEqual(self.inserted, [])

	def test_apply_writes_values_and_certification_rows(self):
		self.run_carry(0)
		self.frappe.db.set_value.assert_called_once()
		args = self.frappe.db.set_value.call_args
		self.assertEqual(args.args[:2], (FIXTURE, "ILL-SH01-SW"))
		self.assertEqual(args.args[2]["hero_image"], "/files/SH01_LIT.jpg")
		self.assertEqual(
			[(row["doctype"], row["parentfield"], row["certification"], row["idx"]) for row in self.inserted],
			[
				("ilL-Child-Spec-Certification", "certifications", c, i)
				for i, c in enumerate(("24V DC", "Dry Rated", "Damp Rated", "Wet Rated"), 1)
			],
		)


class ReadinessRow(unittest.TestCase):
	"""The Fixture Readiness report's pure row logic."""

	def row(self, tpl, listing=None):
		with load_service(ROOT + ".report.fixture_readiness.fixture_readiness") as (module, _frappe):
			return module.readiness(tpl, listing)

	def test_empty_production_template_splits_its_gaps(self):
		result = self.row(
			template(template_name="St. Helens SW", allowed_options=[{}], allowed_tape_offerings=[{}]),
			product(),
		)
		self.assertEqual(result["fill_in"], ["Target Brand", "Product Category"])
		self.assertEqual(
			result["from_product"], ["Sublabel", "Hero Image (check)", "Dimensions Image", "Certifications"]
		)
		self.assertEqual(
			result["calculated"],
			[
				"Specifications",
				"Part No. Configurator",
				"Output Options",
				"Delivered Lumens",
				"Compatible Power Supplies",
			],
		)
		self.assertEqual(result["optional"], ["Spec Gallery"])
		self.assertFalse(result["ready"])

	def test_a_missing_input_is_named_next_to_what_it_blocks(self):
		result = self.row(template(template_name="X", allowed_options=[{}]), product())
		self.assertIn("Output Options (needs Allowed Tape Offerings)", result["calculated"])
		self.assertIn("Delivered Lumens (needs Allowed Tape Offerings)", result["calculated"])

	def test_unlinked_template_must_be_linked_and_filled_by_hand(self):
		result = self.row({"name": "ILL-X", "template_name": "X"}, None)
		self.assertEqual(result["from_product"], [])
		self.assertIn("Webflow Product link", result["fill_in"])
		self.assertIn("Sublabel", result["fill_in"])
		self.assertIn("Hero Image", result["fill_in"])

	def test_complete_template_is_ready(self):
		full = template(
			template_name="St. Helens SW",
			target_brands=[{"brand": "illumenate", "enabled": 1}],
			sublabel="Surface",
			hero_image="/files/h.jpg",
			dimensions_image="/files/d.svg",
			product_category="linear-fixtures",
			certifications=[{"certification": "Dry Rated"}],
			allowed_options=[{}],
			allowed_tape_offerings=[{}],
			specifications=[{"spec_value": "24VDC"}],
			part_no_configurator=[{"option_type": "CCT"}],
			output_options=[{}],
			delivered_lumens=[{}],
			compatible_power_supplies=[{}],
			spec_gallery=[{}],
		)
		result = self.row(full, product())
		self.assertEqual((result["fill_in"], result["from_product"], result["calculated"]), ([], [], []))
		self.assertTrue(result["ready"])


if __name__ == "__main__":
	unittest.main()
