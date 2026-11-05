"""Template calculations live in the template (owner, 2026-11-05; plan 4.17, 4.18 C4-C9).

A template's specification rows and configurator steps are calculated from the template alone
(``template_calculations``): no ilL-Webflow-Product is created or read. The results are the
same as when the calculations ran on a temporary Webflow Product: the expected rows in
fixtures/template_calculations_parity.json were captured from that code (commit d88125d) over
the scenarios in template_calculation_cases.py.
"""

import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from template_calculation_cases import (
	FIXTURE,
	HAND_SET_TAPE_STEPS,
	OPTION,
	POPULATE,
	PRODUCT,
	PRODUCT_CASES,
	ROOT,
	Doc,
	_dict,
	load,
	new_product,
	product_rows,
	product_site_data,
	rows,
	scenarios,
	site,
	tape_template,
)
from test_services import load_service
from test_webflow_sync import _dependencies

CALCULATIONS = ROOT + ".template_calculations"
LISTING = ROOT + ".template_listing"
PRODUCT_MODULE = ROOT + ".doctype.ill_webflow_product.ill_webflow_product"


def plain(value):
	return json.loads(json.dumps(value, default=str))


def outcome(function):
	try:
		return plain(function())
	except Exception as error:
		return {"error": f"{type(error).__name__}: {error}"}


def product_lookups(calls):
	"""The lookups that touched a Webflow Product (or its configurator rows)."""
	return [
		call
		for call in calls
		if call[0] == "new_doc"
		or call[1] == PRODUCT
		or (call[1] == OPTION and isinstance(call[2], dict) and call[2].get("parenttype") == PRODUCT)
	]


def without_idx(table):
	return [{key: value for key, value in row.items() if key != "idx"} for row in table]


class TemplateCalculations(unittest.TestCase):
	expected = json.loads(FIXTURE.read_text())

	def test_every_template_type_calculates_what_the_temporary_product_did(self):
		for name, template in scenarios().items():
			with self.subTest(scenario=name), site():
				listing = load(LISTING)
				result = outcome(
					lambda: dict(
						zip(("specifications", "configurator"), listing.compute(template), strict=True)
					)
				)
				self.assertEqual(result, self.expected["compute"][name])

	def test_no_webflow_product_is_created_imported_or_read(self):
		for name, template in scenarios().items():
			with self.subTest(scenario=name), site() as frappe:
				sys.modules.pop(PRODUCT_MODULE, None)
				listing = load(LISTING)
				outcome(lambda: listing.compute(template))
				self.assertEqual(product_lookups(frappe.calls), [])
				self.assertNotIn(PRODUCT_MODULE, sys.modules)
				self.assertFalse(any(call[0] == "new_doc" for call in frappe.calls))

	def test_the_template_supplies_what_the_product_used_to(self):
		with site() as frappe:
			calculations = load(CALCULATIONS)
			template = tape_template(
				webflow_product="tape-product",
				part_no_configurator=[],
				specifications=rows(
					{"spec_label": "Hand Row", "spec_value": "kept", "is_calculated": 0},
					{"spec_label": "Old", "spec_value": "calculated", "is_calculated": 1},
				),
			)
			calculator = calculations.TemplateCalculator.for_template(template)
			self.assertEqual(calculator.name, "tape-product")
			self.assertEqual(calculator.product_name, "Tape HD Display")
			self.assertEqual(calculator.product_type, "LED Tape")
			self.assertEqual(calculator.tape_neon_template, "TAPE-TPL")
			self.assertIsNone(calculator.fixture_template)
			self.assertIs(calculator.flags.template_doc, template)
			self.assertEqual([row.spec_label for row in calculator.webflow_specifications], ["Hand Row"])
			# A template with no steps yet keeps no "Is Required" choices: the product's are
			# not read any more (plan 4.18 C8).
			self.assertEqual(calculator._get_existing_is_required(), {})
			outcome(lambda: load(LISTING).compute(template))
			self.assertEqual(product_lookups(frappe.calls), [])
			kit = calculations.TemplateCalculator.for_template(Doc("ilL-Extrusion-Kit-Template", "K"))
			self.assertEqual(
				(kit.name, kit.product_name, kit.product_type), ("template:K", "K", "Extrusion Kit")
			)

	def test_products_saved_on_their_own_fill_their_tables_as_before(self):
		for name, (product_name, product_type, field, template_name) in PRODUCT_CASES.items():
			with self.subTest(product=name), site(product_site_data()) as frappe:
				module = load(PRODUCT_MODULE)
				product = new_product(module.ilLWebflowProduct)
				product.name = product_name
				product.product_name = product_name.title()
				product.product_type = product_type
				product.set(field, template_name)
				product.is_configurable = 1
				product._is_new = False
				product.set(
					"webflow_specifications",
					[
						{"spec_label": "Hand Row", "spec_value": "kept", "display_order": 7},
						{"spec_label": "Dimensions", "spec_value": "old", "display_order": 1},
					],
				)
				product.set(
					"documents",
					[{"document_type": "Other", "document_file": "/files/x.pdf", "document_title": "X"}],
				)
				if field == "tape_neon_template":
					product.set("configurator_options", [dict(step) for step in HAND_SET_TAPE_STEPS])

				def sync(product=product):
					product.sync_custom_template_data()
					return product_rows(product)

				def populate(product=product, field=field):
					getattr(product, POPULATE[field])()
					return product_rows(product)

				result = {
					"after_sync": outcome(sync),
					"after_populate": outcome(populate),
					"errors": len(frappe.errors),
				}
				self.assertEqual(result, self.expected["product"][name])


class HandSetTapeNeon(unittest.TestCase):
	"""The hand-set Tape/Neon refresh moved from the product's save to the template's own."""

	expected = json.loads(FIXTURE.read_text())["product"]

	def test_hand_set_steps_take_the_templates_allowed_options_as_the_product_did(self):
		for case, template in (
			("tape", tape_template(auto_populate_configurator=0)),
			("neon", scenarios()["neon"]),
		):
			with self.subTest(case=case), site() as frappe:
				calculations = load(CALCULATIONS)
				template["auto_populate_configurator"] = 0
				template.set("part_no_configurator", [dict(step) for step in HAND_SET_TAPE_STEPS])
				calculations.refresh_hand_set_tape_neon(template)
				self.assertEqual(
					without_idx(plain(template["part_no_configurator"])),
					without_idx(self.expected[case]["after_sync"]["configurator_options"]),
				)
				self.assertEqual(product_lookups(frappe.calls), [])

	def refresh(self, template):
		images = types.ModuleType(ROOT + ".template_images")
		images.refresh = lambda template: None
		supplies = types.ModuleType(ROOT + ".template_power_supplies")
		supplies.refresh = lambda template: None
		modules = {images.__name__: images, supplies.__name__: supplies}
		with site(modules=modules) as frappe:
			listing = load(LISTING)
			listing.refresh_template(template)
			return frappe

	def test_a_hand_set_tape_template_is_refreshed_on_its_own_save_before_renumbering(self):
		template = tape_template(
			auto_populate_configurator=0,
			part_no_configurator=rows(
				{"option_step": 1, "option_type": "CCT", "option_label": "CCT", "allowed_values_json": "[]"},
				{"option_step": 2, "option_type": "Finish", "option_label": "Finish"},
				# A row just added (no step yet).
				{"option_step": None, "option_type": "IP Rating", "option_label": "IP Rating"},
			),
		)
		frappe = self.refresh(template)
		steps = template["part_no_configurator"]
		self.assertEqual(
			[(row.option_type, row.option_step) for row in steps],
			[
				("CCT", 1),
				("Finish", 2),
				# The new row gets the next step when the steps are renumbered.
				("IP Rating", 3),
				# Allowed option types with no step: step 99 (lookup, not renumbered).
				("Environment Rating", 99),
				("Output Level", 99),
				("Mounting Method", 99),
				# Added after Finish (step 3) before renumbering, so it moves to the next free
				# step instead of sharing step 3 with the new row.
				("Length", 4),
			],
		)
		self.assertEqual(json.loads(steps[2].allowed_values_json)[0]["code"], "65")
		cct = json.loads(steps[0].allowed_values_json)
		self.assertEqual([value["code"] for value in cct], ["30", "27", "30"])
		self.assertEqual(json.loads(steps[1].allowed_values_json)[0]["label"], "Silver (custom)")
		self.assertEqual(json.loads(steps[-1].allowed_values_json)[0]["value"], "__length_metadata__")
		self.assertEqual(product_lookups(frappe.calls), [])

	def test_calculated_and_other_hand_set_templates_are_not_touched_by_it(self):
		# A calculated Tape template is rebuilt from the calculation alone.
		template = tape_template()
		with site():
			expected = load(LISTING).compute(tape_template())[1]
		self.refresh(template)
		self.assertEqual(without_idx(plain(template["part_no_configurator"])), plain(expected))
		# A hand-set Fixture template keeps its steps as they are (only renumbered).
		fixture = scenarios()["fixture"]
		fixture["auto_populate_configurator"] = 0
		fixture.set(
			"part_no_configurator",
			rows({"option_step": 1, "option_type": "Finish", "allowed_values_json": "[1]"}),
		)
		self.refresh(fixture)
		self.assertEqual(
			plain(fixture["part_no_configurator"]),
			[{"option_step": 1, "option_type": "Finish", "allowed_values_json": "[1]", "idx": 1}],
		)

	def test_a_failed_refresh_never_blocks_the_save(self):
		class Unreadable(_dict):
			"""A step whose label cannot be read: the refresh fails on it."""

			def __getattr__(self, key):
				if key == "option_label":
					raise RuntimeError("unreadable")
				return self.get(key)

		template = tape_template(auto_populate_configurator=0)
		template["part_no_configurator"] = [
			Unreadable(option_step=2, option_type="CCT"),
			Unreadable(option_step=1, option_type="IP Rating"),
		]
		frappe = self.refresh(template)
		self.assertTrue(
			any("Hand-set Tape/Neon steps refresh failed" in str(error) for error in frappe.errors)
		)
		# The steps are still renumbered and the specifications still stored.
		self.assertEqual([row.option_step for row in template["part_no_configurator"]], [1, 2])
		self.assertTrue(template["specifications"])


class ExportTemplateRecord(unittest.TestCase):
	"""The v2 export of a template with no Webflow Product still uses a temporary product, but
	its configurator steps come from the template calculation, not the product methods."""

	def test_the_temporary_product_takes_the_templates_calculated_steps(self):
		steps = [{"option_step": 1, "option_type": "CCT"}]
		calculator = MagicMock()
		calculator.configurator_rows.return_value = steps
		calculations = types.ModuleType(CALCULATIONS)
		calculations.TemplateCalculator = MagicMock()
		calculations.TemplateCalculator.for_template.return_value = calculator
		calculations.SPEC_FIELDS = ("spec_label", "is_calculated")
		calculations.plain_rows = lambda found, fields: [
			{f: row.get(f) for f in fields} for row in found or []
		]
		calculations.display_name = lambda template: template.get("display_name")
		calculations.product_type_for = lambda template: "LED Tape"

		class Product(_dict):
			def set(self, key, value):
				self[key] = value

		product = Product(flags=_dict())
		for method in ("set_dynamic_hero_image", "populate_attribute_links"):
			product[method] = MagicMock()
		product.sync_custom_template_data = MagicMock()
		product.populate_certification_badges = MagicMock()
		template = Doc(
			"ilL-Tape-Neon-Template",
			"TAPE-TPL",
			display_name="Tape HD",
			is_active=1,
			specifications=rows(
				{"spec_label": "Hand Row", "is_calculated": 0}, {"spec_label": "CRI", "is_calculated": 1}
			),
		)
		with load_service(
			ROOT + ".api.webflow_export_v2", {**_dependencies(), CALCULATIONS: calculations}
		) as (
			module,
			frappe,
		):
			frappe.new_doc = MagicMock(return_value=product)
			with patch.object(module, "_finish_products", return_value=[{"exported": 1}]) as finish:
				self.assertEqual(module.export_template_record(template, "illumenate"), {"exported": 1})
		frappe.new_doc.assert_called_once_with(PRODUCT)
		calculations.TemplateCalculator.for_template.assert_called_once_with(template)
		self.assertEqual(product["configurator_options"], steps)
		self.assertEqual((product.name, product.product_type), ("template:TAPE-TPL", "LED Tape"))
		self.assertEqual((product.tape_neon_template, product.flags.template_doc), ("TAPE-TPL", template))
		self.assertEqual(product["webflow_specifications"], [{"spec_label": "Hand Row", "is_calculated": 0}])
		product.sync_custom_template_data.assert_called_once_with()
		# The product's populate_* methods are not called: this stand-in has none (calling one
		# would fail). The export reads the product with the template (Listing).
		self.assertEqual(finish.call_args.args[3]("template:TAPE-TPL"), (product, template))


if __name__ == "__main__":
	unittest.main()
