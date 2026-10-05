"""COB Tape: its own template category that configures, prices and builds exactly like LED Tape."""

import json
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	FAMILY_ALIASES,
	TAPE_CATEGORIES,
	TAPE_NEON_CATEGORIES,
	is_tape_category,
	same_template_family,
	spec_categories_for,
)

DOCTYPES = Path("illumenate_lighting/illumenate_lighting/doctype")


def options(stem, fieldname):
	schema = json.loads((DOCTYPES / stem / f"{stem}.json").read_text(encoding="utf-8"))
	return next(f["options"] for f in schema["fields"] if f["fieldname"] == fieldname).split("\n")


class Categories(unittest.TestCase):
	def test_cob_tape_is_a_tape_category_next_to_led_tape(self):
		self.assertEqual(TAPE_CATEGORIES, ("LED Tape", "COB Tape"))
		self.assertEqual(TAPE_NEON_CATEGORIES, ("LED Tape", "COB Tape", "LED Neon"))
		self.assertTrue(is_tape_category("COB Tape"))
		self.assertFalse(is_tape_category("LED Neon"))
		self.assertEqual(FAMILY_ALIASES["COB Tape"], "COB Tape")

	def test_cob_templates_may_keep_led_tape_specs_but_led_tape_never_takes_cob_specs(self):
		self.assertEqual(spec_categories_for("COB Tape"), ("COB Tape", "LED Tape"))
		self.assertEqual(spec_categories_for("LED Tape"), ("LED Tape",))
		self.assertEqual(spec_categories_for("LED Neon"), ("LED Neon",))

	def test_tape_products_match_either_tape_template_but_never_neon(self):
		self.assertTrue(same_template_family("LED Tape", "COB Tape"))
		self.assertTrue(same_template_family("COB Tape", "LED Tape"))
		self.assertFalse(same_template_family("LED Tape", "LED Neon"))
		self.assertFalse(same_template_family("LED Neon", "COB Tape"))
		self.assertTrue(same_template_family("LED Neon", "LED Neon"))

	def test_every_category_choice_offers_cob_tape(self):
		for stem, field in (
			("ill_tape_neon_template", "product_category"),
			("ill_spec_led_tape", "product_category"),
			("ill_configured_tape_neon", "product_category"),
			("ill_child_fixture_schedule_line", "product_type"),
			("ill_webflow_product", "product_type"),
			("ill_configured_group", "family"),
			("ill_configurator_session", "product_type"),
			("ill_child_finder_family", "family"),
			("ill_child_certification_applies_to", "product_type"),
		):
			with self.subTest(doctype=stem):
				choices = options(stem, field)
				self.assertIn("COB Tape", choices)
				self.assertEqual(choices.index("COB Tape"), choices.index("LED Tape") + 1)
		custom_fields = json.loads(
			Path("illumenate_lighting/illumenate_lighting/fixtures/custom_field.json").read_text(
				encoding="utf-8"
			)
		)
		product_types = [f for f in custom_fields if f["fieldname"] == "ill_product_type"]
		self.assertTrue(product_types)
		for field in product_types:
			self.assertIn("COB Tape", field["options"].split("\n"))


class TemplateValidation(unittest.TestCase):
	def template(self, category, spec_categories):
		document = types.ModuleType("frappe.model.document")
		document.Document = object
		model = types.ModuleType("frappe.model")
		model.document = document
		context = load_service(
			ROOT + ".doctype.ill_tape_neon_template.ill_tape_neon_template",
			{"frappe.model": model, "frappe.model.document": document},
		)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.db.get_value.side_effect = lambda doctype, name, field: spec_categories[name]
		doc = module.ilLTapeNeonTemplate()
		doc.product_category = category
		doc.allowed_tape_specs = [Record(idx=i + 1, tape_spec=name) for i, name in enumerate(spec_categories)]
		return doc

	def test_a_cob_template_accepts_cob_specs_and_specs_still_filed_as_led_tape(self):
		self.template(
			"COB Tape", {"COB-SD-SW-20-30K-300-3M-WH-8MM": "LED Tape", "COB-NEW": "COB Tape"}
		).validate()

	def test_an_led_tape_template_refuses_a_cob_spec_and_neon_stays_separate(self):
		with self.assertRaisesRegex(ValueError, "has product category 'COB Tape'"):
			self.template("LED Tape", {"COB-NEW": "COB Tape"}).validate()
		with self.assertRaisesRegex(ValueError, "'NON-PNC' has product category 'LED Neon'"):
			self.template("COB Tape", {"LED-HD": "LED Tape", "NON-PNC": "LED Neon"}).validate()
		with self.assertRaisesRegex(ValueError, "'COB Tape'"):
			self.template("Other", {}).validate()


class TapeValidation(unittest.TestCase):
	def service(self, template_category):
		families = []
		rollout = types.SimpleNamespace(require_configuration=families.append)
		context = load_service(ROOT + ".api.tape_neon_configurator", {ROOT + ".portal.rollout": rollout})
		service, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.logger = MagicMock()
		meta = Record(is_free_cutting=0, default_tape_spec=None, product_category=template_category)
		frappe.db.get_value.side_effect = lambda doctype, name, field=None, *a, **kw: (
			template_category if field == "product_category" else meta
		)
		frappe.get_all.side_effect = lambda doctype, *args, **kwargs: []
		return service, frappe, families

	def test_a_cob_template_configures_as_cob_tape_over_cob_and_led_tape_specs(self):
		service, frappe, families = self.service("COB Tape")
		result = service.validate_tape_configuration(
			{"cct": "3000K", "output_level": "300 lm/ft"}, tape_neon_template="cob-sd-sw"
		)
		self.assertEqual(families, ["COB Tape"])
		self.assertFalse(result["is_valid"])
		spec_searches = [
			call.kwargs["filters"]["product_category"]
			for call in frappe.get_all.call_args_list
			if call.args[0] == "ilL-Spec-LED Tape" and "product_category" in call.kwargs.get("filters", {})
		]
		self.assertIn(["in", ["COB Tape", "LED Tape"]], spec_searches)

	def test_led_tape_and_untemplated_requests_stay_led_tape(self):
		for template, category in (("led-hd-sw", "LED Tape"), (None, "LED Tape"), ("non-pnc-sw", "LED Neon")):
			with self.subTest(template=template):
				service, _frappe, families = self.service(category)
				service.validate_tape_configuration(
					{"cct": "3000K", "output_level": "Std"}, tape_neon_template=template
				)
				self.assertEqual(families, ["LED Tape"])

	def test_cob_descriptions_name_cob_tape(self):
		service, _frappe, _families = self.service("COB Tape")
		spec = Record(
			name="COB-SD-SW-20-30K-300-3M-WH-8MM", item="COB-SD-SW-20-30K-300-3M-WH-8MM", is_free_cutting=1
		)
		description = service._build_tape_description(
			{}, spec, None, 2250.44, 12, product_category="COB Tape"
		)
		self.assertTrue(description.startswith("COB Tape: COB-SD-SW-20-30K-300-3M-WH-8MM"))


class LineFamily(unittest.TestCase):
	def family(self, family, template, categories):
		access = types.SimpleNamespace(can_edit_schedule=MagicMock(), can_read_schedule=MagicMock())
		build = types.SimpleNamespace(atomic_build=lambda f: f)
		context = load_service(
			ROOT + ".portal.configuration",
			{ROOT + ".portal.access": access, ROOT + ".api.build_artifacts": build},
		)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.db.get_value.side_effect = lambda doctype, name, field: categories.get(
			name if isinstance(name, str) else name["template_code"]
		)
		return module.family_for_template(family, template)

	def test_a_tape_line_follows_its_templates_category(self):
		self.assertEqual(self.family("LED Tape", "cob-sd-sw", {"cob-sd-sw": "COB Tape"}), "COB Tape")
		self.assertEqual(self.family("COB Tape", "led-hd-sw", {"led-hd-sw": "LED Tape"}), "LED Tape")

	def test_other_families_and_unknown_templates_keep_the_requested_family(self):
		self.assertEqual(self.family("LED Neon", "cob-sd-sw", {"cob-sd-sw": "COB Tape"}), "LED Neon")
		self.assertEqual(self.family("LED Tape", "missing", {}), "LED Tape")
		self.assertEqual(self.family("COB Tape", None, {}), "COB Tape")
		self.assertEqual(self.family("LED Tape", "non-pnc-sw", {"non-pnc-sw": "LED Neon"}), "LED Tape")


class PortalCategoryList(unittest.TestCase):
	def test_item_groups_name_their_template_category(self):
		with load_service(ROOT + ".api.portal") as (module, _frappe):
			category = module.tape_neon_category_for_group
			self.assertEqual(category("COB Tape"), "COB Tape")
			self.assertEqual(category("cob tape"), "COB Tape")
			self.assertEqual(category("LED Tape"), "LED Tape")
			self.assertEqual(category("LED Tape - Outdoor"), "LED Tape")
			self.assertEqual(category("LED Neon"), "LED Neon")
			self.assertIsNone(category("Configured LED Tape"))
			self.assertIsNone(category("Linear Fixtures"))
			self.assertIsNone(category(None))

	def test_cob_tape_series_are_listed_for_the_add_line_modal(self):
		with load_service(ROOT + ".api.portal") as (module, frappe):
			frappe.get_all.return_value = []
			module.get_tape_neon_templates_for_schedule("COB Tape")
			self.assertEqual(
				frappe.get_all.call_args.kwargs["filters"], {"is_active": 1, "product_category": "COB Tape"}
			)
			frappe.get_all.reset_mock()
			self.assertEqual(module.get_tape_neon_templates_for_schedule("Other"), {"templates": []})
			frappe.get_all.assert_not_called()


class Rollout(unittest.TestCase):
	def reason(self, families):
		staff = types.SimpleNamespace(allowed=lambda role: False)
		with load_service(ROOT + ".portal.rollout", {ROOT + ".portal.staff": staff}) as (service, _frappe):
			lists = {"ill_portal_enabled_families": families, "ill_portal_pilot_users": None}
			service._list = lambda key: lists[key]
			return service.reason("COB Tape")

	def test_cob_tape_follows_led_tape_unless_listed_on_its_own(self):
		self.assertEqual(self.reason(None), "ok")
		self.assertEqual(self.reason(["LED Tape"]), "ok")
		self.assertEqual(self.reason(["COB Tape"]), "ok")
		self.assertEqual(self.reason(["Linear Fixture", "LED Neon"]), "family_not_enabled")


class ConfiguredItems(unittest.TestCase):
	def test_cob_builds_get_their_own_configured_item_group(self):
		with load_service(ROOT + ".api.manufacturing_generator") as (module, _frappe):
			group = module.configured_tape_neon_item_group
			self.assertEqual(group("COB Tape"), "Configured COB Tape")
			self.assertEqual(group("LED Tape"), "Configured LED Tape")
			self.assertEqual(group("LED Neon"), "Configured LED Neon")
			self.assertEqual(group(None), "Configured LED Tape")


class Migration(unittest.TestCase):
	def test_existing_sites_receive_the_cob_tape_patch_after_model_sync(self):
		patches = Path("illumenate_lighting/patches.txt").read_text().split("[post_model_sync]", 1)[1]
		self.assertIn("illumenate_lighting.patches.add_cob_tape_category", patches.splitlines())

	def test_the_patch_adds_a_cob_tape_group_beside_led_tape_only_where_tape_is_sold(self):
		with load_service("illumenate_lighting.patches.add_cob_tape_category") as (patch, frappe):
			frappe.db.exists.side_effect = lambda doctype, name: name == "LED Tape"
			frappe.db.get_value.return_value = "Products"
			patch.ensure_cob_tape_item_group()
			frappe.get_doc.assert_called_once_with(
				{
					"doctype": "Item Group",
					"item_group_name": "COB Tape",
					"parent_item_group": "Products",
					"is_group": 0,
				}
			)
			frappe.get_doc.reset_mock()
			frappe.db.exists.side_effect = lambda doctype, name: True
			patch.ensure_cob_tape_item_group()
			frappe.get_doc.assert_not_called()
			frappe.db.exists.side_effect = lambda doctype, name: False
			patch.ensure_cob_tape_item_group()
			frappe.get_doc.assert_not_called()


if __name__ == "__main__":
	unittest.main()
