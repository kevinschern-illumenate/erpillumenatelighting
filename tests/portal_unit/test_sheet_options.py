"""LED Sheet option cascade answered by the server (plan 6.4)."""

import json
import types
import unittest

from test_services import ROOT, Record, load_service

PANELS = {
	"SPEC-O-10": Record(is_active=1, item="LED-SNF-SW-O-10W-SHEET", cct="3000K"),
	"SPEC-I-10": Record(is_active=1, item="LED-SNF-SW-I-10W-SHEET", cct="3000K"),
	"SPEC-O-20": Record(is_active=1, item="LED-SNF-SW-O-20W-SHEET", cct="3000K"),
	"SPEC-OFF": Record(is_active=0, item="LED-SNF-SW-I-20W-SHEET", cct="3000K"),
}


def option(option_type, value, code, is_active=1):
	return Record(option_type=option_type, attribute_link=value, option_code=code, is_active=is_active, is_default=0)


TEMPLATE = Record(
	name="SNF-SW",
	allowed_specs=[Record(spec=name, is_active=1) for name in PANELS],
	allowed_options=[
		option("CCT", "3000K", "30K"),
		option("Output Level", "10W", "10W"),
		option("Output Level", "20W", "20W"),
		option("Environment Rating", "Outdoor", "O"),
		option("Environment Rating", "Indoor", "I"),
		option("Environment Rating", "Wet", "W", is_active=0),
		option("Finish", "White", "WH"),
	],
)


class SheetCascadingOptions(unittest.TestCase):
	def cascade(self, options, enabled=True):
		required = []
		extras = {
			ROOT + ".portal.rollout": types.SimpleNamespace(require_configuration=required.append),
			ROOT + ".portal.site_flags": types.SimpleNamespace(sheet_server_options_enabled=lambda: enabled),
		}
		with load_service(ROOT + ".api.led_sheet_configurator", extras) as (service, frappe):
			frappe.db.get_all.side_effect = lambda *args, **kwargs: []
			frappe.db.sql.side_effect = lambda *args, **kwargs: []
			frappe.get_doc.side_effect = lambda doctype, name: TEMPLATE if doctype == "ilL-LED-Sheet-Template" else PANELS[name]
			result = service.get_sheet_cascading_options("SNF-SW", options)
			self.assertEqual(required, ["LED Sheet"], "the configurator permission is always checked")
			return result, frappe

	def test_choices_narrow_the_other_options_and_identify_one_panel(self):
		result, _frappe = self.cascade(json.dumps({"CCT": "3000K", "Environment Rating": "Indoor", "Finish": "White"}))
		self.assertTrue(result["enabled"])
		self.assertEqual(result["available"]["Output Level"], ["10W"], "no indoor 20 W panel is sold")
		self.assertEqual(result["available"]["Environment Rating"], ["Outdoor", "Indoor"])
		self.assertEqual(result["available"]["Finish"], ["White"])
		self.assertEqual(result["matches"], ["SPEC-I-10"])
		self.assertEqual(result["spec"], "SPEC-I-10")
		self.assertEqual(result["invalid"], [])
		self.assertNotIn("msrp_adder", json.dumps(result), "no prices in the cascade")

	def test_an_impossible_combination_matches_nothing_and_shows_the_way_out(self):
		result, _frappe = self.cascade({"selected_environment_rating": "Indoor", "output_level": "20W"})
		self.assertEqual(result["match_count"], 0)
		self.assertIsNone(result["spec"])
		self.assertEqual(result["available"]["Output Level"], ["10W"])
		self.assertEqual(result["available"]["Environment Rating"], ["Outdoor"])

	def test_ambiguous_choices_name_every_panel_but_no_spec(self):
		result, _frappe = self.cascade({"Environment Rating": "Outdoor"})
		self.assertEqual(result["matches"], ["SPEC-O-10", "SPEC-O-20"])
		self.assertIsNone(result["spec"])

	def test_values_the_template_does_not_offer_are_reported_and_ignored(self):
		result, _frappe = self.cascade({"Environment Rating": "Wet", "Output Level": "20W", "Colour": "Red"})
		self.assertEqual(result["invalid"], ["Environment Rating"])
		self.assertEqual(result["matches"], ["SPEC-O-20"])
		self.assertNotIn("Wet", result["available"]["Environment Rating"])

	def test_kill_switch_answers_without_reading_the_catalog(self):
		result, frappe = self.cascade({"Environment Rating": "Indoor"}, enabled=False)
		self.assertEqual(result, {"success": True, "enabled": False})
		frappe.get_doc.assert_not_called()

	def test_the_cascade_and_the_save_path_choose_the_same_panel(self):
		extras = {ROOT + ".portal.site_flags": types.SimpleNamespace(sheet_server_options_enabled=lambda: True)}
		with load_service(ROOT + ".api.led_sheet_configurator", extras) as (service, frappe):
			frappe.db.get_all.side_effect = lambda *args, **kwargs: []
			frappe.db.sql.side_effect = lambda *args, **kwargs: []
			frappe.get_doc.side_effect = lambda doctype, name: PANELS[name]
			resolved = service._resolve_options(
				TEMPLATE, {"CCT": "3000K", "Output Level": "10W", "Environment Rating": "Indoor", "Finish": "White"}
			)
			self.assertEqual(service.resolve_sheet_spec(TEMPLATE, resolved), "SPEC-I-10")


class SheetOptionsFlag(unittest.TestCase):
	def test_on_unless_a_site_turns_it_off(self):
		with load_service(ROOT + ".portal.site_flags") as (flags, frappe):
			self.assertTrue(flags.sheet_server_options_enabled())
			frappe.conf["ill_portal_sheet_server_options"] = "false"
			self.assertFalse(flags.sheet_server_options_enabled())


if __name__ == "__main__":
	unittest.main()
