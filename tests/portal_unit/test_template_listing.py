"""Phase 2: templates store spec rows and configurator steps; products take them."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

KIT = "ilL-Extrusion-Kit-Template"
TAPE = "ilL-Tape-Neon-Template"


class Flags(dict):
	__getattr__ = dict.get

	def __setattr__(self, key, value):
		self[key] = value


class Doc(dict):
	def __init__(self, doctype=None, name=None, **values):
		super().__init__(values)
		self.__dict__.update(doctype=doctype, name=name, flags=Flags())

	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		if key in ("doctype", "name", "flags"):
			self.__dict__[key] = value
		else:
			self[key] = value

	def set(self, key, value):
		self[key] = value


def spec(label, value, order=50):
	return {"spec_label": label, "spec_value": value, "display_order": order}


class Listing(unittest.TestCase):
	def setUp(self):
		product_module = types.ModuleType(ROOT + ".doctype.ill_webflow_product.ill_webflow_product")
		product_module.MANAGED_LABELS = ("Watts per Foot", "Operating Temperature", "Dimming")
		context = load_service(ROOT + ".template_listing", {product_module.__name__: product_module})
		self.module, self.frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)

	def test_the_shadow_product_reads_the_template_being_saved(self):
		self.frappe.new_doc = lambda doctype: Doc(doctype)
		self.frappe.get_all.return_value = [Record(option_step=2, is_required=0)]
		template = Doc(
			TAPE,
			"led-hd-sw",
			template_name="LED HD SW",
			product_category="LED Tape",
			webflow_product="led-hd-sw",
			specifications=[spec("Hand Row", "kept")],
		)
		product, field = self.module.shadow_product(template)
		self.assertEqual((field, product["tape_neon_template"]), ("tape_neon_template", "led-hd-sw"))
		self.assertEqual(product["product_type"], "LED Tape")
		self.assertIs(product.flags.template_doc, template)
		self.assertEqual(product["webflow_specifications"][0]["spec_label"], "Hand Row")
		# With no configurator on the template yet, the product's "Is Required" choices carry over.
		self.assertEqual(product.flags.existing_is_required, {2: 0})

	def test_a_kit_template_is_listed_as_an_extrusion_kit(self):
		self.assertEqual(self.module.product_type_for(Doc(KIT, "KIT-RA01")), "Extrusion Kit")

	def link(self, template):
		self.frappe.get_doc.return_value = template
		self.frappe.db.get_value.return_value = template["webflow_product"]

	def test_the_product_keeps_its_fresh_rows_and_takes_the_templates_decisions(self):
		self.link(
			Doc(
				KIT,
				"KIT-RA01",
				webflow_product="kit-ra01",
				# A stale calculated row (ignored) and a row typed on the template (taken).
				specifications=[spec("Watts per Foot", "stale", 20), spec("Template Note", "t", 90)],
				part_no_configurator=[{"option_step": 1, "is_required": 0}],
			)
		)
		option = Record(option_step=1, is_required=1, option_type="Finish")
		product = Doc(
			"ilL-Webflow-Product",
			"kit-ra01",
			kit_template="KIT-RA01",
			is_configurable=1,
			auto_populate_configurator_options=1,
			webflow_specifications=[spec("Watts per Foot", "4.4", 20), spec("Product Note", "p", 10)],
			configurator_options=[option],
		)
		self.module.apply_template_rows(product)
		self.assertEqual(
			[(row["spec_label"], row["spec_value"]) for row in product["webflow_specifications"]],
			[("Product Note", "p"), ("Watts per Foot", "4.4"), ("Template Note", "t")],
		)
		self.assertEqual(option.is_required, 0)

	def test_steps_set_up_by_hand_on_the_product_are_left_alone(self):
		self.link(
			Doc(
				TAPE,
				"led-hd-sw",
				webflow_product="led-hd-sw",
				specifications=[],
				part_no_configurator=[{"option_step": 1, "is_required": 0}],
			)
		)
		option = Record(option_step=1, is_required=1, option_type="IP Rating")
		product = Doc(
			"ilL-Webflow-Product",
			"led-hd-sw",
			tape_neon_template="led-hd-sw",
			is_configurable=1,
			auto_populate_configurator_options=0,
			webflow_specifications=[],
			configurator_options=[option],
		)
		self.module.apply_template_rows(product)
		self.assertEqual(option.is_required, 1)

	def test_a_hand_set_product_configurator_is_not_calculated_for_the_comparison(self):
		product = Doc(
			"ilL-Webflow-Product", "led-hd-sw", is_configurable=1, auto_populate_configurator_options=0
		)
		product.sync_custom_template_data = MagicMock()
		product.populate_tape_neon_configurator_options = MagicMock()
		product["tape_neon_template"] = "led-hd-sw"
		product["webflow_specifications"] = [spec("CRI", "90")]
		specs, configurator = self.module.fresh_product_rows(product)
		self.assertIsNone(configurator)
		product.populate_tape_neon_configurator_options.assert_not_called()
		self.assertEqual(specs[0]["spec_value"], "90")

	def test_a_template_without_decisions_leaves_the_product_alone(self):
		self.link(
			Doc(KIT, "KIT-RA01", webflow_product="kit-ra01", specifications=[], part_no_configurator=[])
		)
		rows = [spec("Watts per Foot", "4.4")]
		product = Doc("ilL-Webflow-Product", "kit-ra01", kit_template="KIT-RA01", webflow_specifications=rows)
		self.module.apply_template_rows(product)
		self.assertIs(product["webflow_specifications"], rows)

	def test_a_failed_calculation_keeps_the_rows_and_never_blocks_the_save(self):
		self.frappe.new_doc = MagicMock(side_effect=RuntimeError("no profile"))
		self.frappe.log_error = MagicMock()
		self.frappe.msgprint = MagicMock()
		template = Doc(KIT, "KIT-RA01", specifications=[spec("Watts per Foot", "4.4")])
		self.module.refresh_template(template)
		self.assertEqual(template["specifications"], [spec("Watts per Foot", "4.4")])
		self.frappe.msgprint.assert_called_once()

	def readers(self, legacy=False, product_flags=(), template_auto=1):
		self.frappe.flags.web_listing_legacy_read = legacy
		templates = [
			Record(name="led-hd-sw", webflow_product="led-hd-sw", auto_populate_configurator=template_auto)
		]
		rows = {
			"ilL-Tape-Neon-Template": [Record(parent="led-hd-sw", option_step=1, option_type="CCT")],
			"ilL-Webflow-Product": [
				Record(parent="led-hd-sw", option_step=0, option_type="Series"),
				Record(parent="no-template", option_step=2, option_type="Finish"),
			],
		}

		def get_all(doctype, filters=None, **kwargs):
			if doctype == TAPE:
				return templates
			if doctype == "ilL-Webflow-Product":
				return list(product_flags)
			if doctype == self.module.OPTION:
				return [
					row for row in rows.get(filters["parenttype"], []) if row.parent in filters["parent"][1]
				]
			return []

		self.frappe.get_all.side_effect = get_all
		products = [
			{"name": "led-hd-sw", "tape_neon_template": "led-hd-sw"},
			{"name": "no-template"},
		]
		return self.module.configurator_rows(products)

	def test_readers_take_the_templates_configurator(self):
		result = self.readers()
		self.assertEqual([row.option_type for row in result["led-hd-sw"]], ["CCT"])
		# A product without a template keeps reading its own table.
		self.assertEqual([row.option_type for row in result["no-template"]], ["Finish"])

	def test_hand_set_steps_stay_on_the_product_until_decided(self):
		hand_set = [Record(name="led-hd-sw", is_configurable=1, auto_populate_configurator_options=0)]
		result = self.readers(product_flags=hand_set)
		self.assertEqual([row.option_type for row in result["led-hd-sw"]], ["Series"])
		# Once the template takes the steps (it stops calculating), the template is read.
		result = self.readers(product_flags=hand_set, template_auto=0)
		self.assertEqual([row.option_type for row in result["led-hd-sw"]], ["CCT"])

	def test_the_report_says_what_differs_in_a_step(self):
		self.frappe.parse_json = __import__("json").loads
		self.frappe.as_json = __import__("json").dumps
		hand = {
			"option_step": 1,
			"option_type": "CCT",
			"is_required": 1,
			"allowed_values_json": '[{"code": "30"}]',
		}
		calculated = {
			"option_step": 1,
			"option_type": "CCT",
			"is_required": 0,
			"allowed_values_json": '[{"code": "30"}, {"code": "40"}]',
		}
		(step,) = self.module.side_by_side([hand], [calculated])
		self.assertEqual(step["differs"], ["is_required", "allowed values"])
		self.assertEqual((step["only_hand_set"], step["only_calculated"]), ([], ["40"]))

	def test_legacy_read_sends_readers_back_to_the_product(self):
		result = self.readers(legacy=True)
		self.assertEqual([row.option_type for row in result["led-hd-sw"]], ["Series"])

	def test_a_hand_set_configurator_is_shown_next_to_the_calculated_one(self):
		hand = [
			{
				"option_step": 0,
				"option_type": "Series",
				"option_label": "Series",
				"allowed_values_json": "[1]",
			},
			{
				"option_step": 1,
				"option_type": "CCT",
				"option_label": "CCT",
				"allowed_values_json": '["a","b"]',
			},
		]
		calculated = [
			{
				"option_step": 1,
				"option_type": "CCT",
				"option_label": "CCT",
				"allowed_values_json": '["a","b"]',
			},
			{
				"option_step": 2,
				"option_type": "Finish",
				"option_label": "Finish",
				"allowed_values_json": "[]",
			},
		]
		self.frappe.parse_json = __import__("json").loads
		steps = self.module.side_by_side(hand, calculated)
		self.assertEqual([step["step"] for step in steps], [0, 1, 2])
		self.assertEqual([step["same"] for step in steps], [False, True, False])
		self.assertEqual(steps[0]["hand_set"], "Series / Series (1 values)")
		self.assertIsNone(steps[0]["calculated"])
		self.assertEqual(steps[2]["calculated"], "Finish / Finish (0 values)")

	def test_a_template_set_up_by_hand_keeps_its_steps(self):
		self.module.compute = MagicMock(return_value=([spec("CRI", "90")], [{"option_step": 1}]))
		template = Doc(TAPE, "led-hd-sw", auto_populate_configurator=0, part_no_configurator=["hand"])
		self.module.refresh_template(template)
		self.assertEqual(template["part_no_configurator"], ["hand"])
		self.assertEqual(template["specifications"], [spec("CRI", "90")])
		template["auto_populate_configurator"] = 1
		self.module.refresh_template(template)
		self.assertEqual(template["part_no_configurator"], [{"option_step": 1}])

	def test_differences_from_d43_are_expected_and_the_rest_are_not(self):
		diff = self.module.diff_listing(
			[
				spec("Dimming", "TBD"),
				spec("Operating Temperature", "32°F (0°C) to 32°F (0°C)"),
				spec("Watts per Foot", "4.4"),
				spec("CRI", "90"),
			],
			[spec("Watts per Foot", "4.4"), spec("CRI", "95")],
			[{"option_step": 1, "option_type": "Finish"}],
			[{"option_step": 1, "option_type": "Finish"}],
		)
		self.assertEqual([row["label"] for row in diff["expected"]], ["Dimming", "Operating Temperature"])
		self.assertEqual(diff["unexpected"], [{"label": "CRI", "product": "90", "template": "95"}])
		self.assertEqual(diff["configurator"], [])


if __name__ == "__main__":
	unittest.main()
