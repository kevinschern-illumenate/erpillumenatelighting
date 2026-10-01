"""Quiz answers pre-fill only options the chosen template actually offers."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

FINISHES = [
	{"value": "Anodized Silver", "code": "AS"},
	{"value": "Black Anodized", "code": "BK"},
	{"value": "White", "code": "WH"},
]


class MatchOption(unittest.TestCase):
	def setUp(self):
		self.loaded = load_service(ROOT + ".portal.quiz_prefill")
		self.service, _frappe = self.loaded.__enter__()

	def tearDown(self):
		self.loaded.__exit__(None, None, None)

	def test_exact_then_kelvin_then_one_whole_word(self):
		match = self.service.match_option
		self.assertEqual(match("white", FINISHES), "White")
		self.assertEqual(match("AS", FINISHES), "Anodized Silver")
		self.assertEqual(match("Silver", FINISHES), "Anodized Silver")
		self.assertEqual(match("Black", FINISHES), "Black Anodized")
		ccts = [{"value": "30K Warm", "label": "3000K", "kelvin": 3000}, {"value": "35K", "kelvin": 3500}]
		self.assertEqual(match("3000K", ccts), "30K Warm")
		self.assertEqual(match("3500", ccts), "35K")
		self.assertEqual(match("Dry", [{"value": "Dry Location"}, {"value": "Wet Location"}]), "Dry Location")

	def test_ambiguous_missing_or_blank_answers_match_nothing(self):
		match = self.service.match_option
		self.assertIsNone(match("Anodized", FINISHES))
		self.assertIsNone(match("Gold", FINISHES))
		self.assertIsNone(match("", FINISHES))
		self.assertIsNone(match("Sil", FINISHES))


class Resolve(unittest.TestCase):
	def test_linear_answers_use_the_configurator_option_lists_and_its_led_package(self):
		calls = []

		def cascading(template, led_package_code=None):
			calls.append(led_package_code)
			ccts = [{"value": "3000K", "kelvin": 3000}] if led_package_code == "SW-PKG" else []
			return {
				"options": {
					"led_packages": [
						{"value": "SW-PKG", "spectrum_type": "Static White"},
						{"value": "TW-PKG", "spectrum_type": "Tunable White"},
					],
					"environment_ratings": [{"value": "Damp Location", "label": "Damp", "code": "DP"}],
					"ccts": ccts,
					"lens_appearances": [{"value": "Frosted"}],
					"mountings": [{"value": "Surface Clip", "label": "Surface"}],
					"finishes": FINISHES,
				}
			}

		engine = types.SimpleNamespace(get_cascading_options_for_template=cascading)
		with load_service(ROOT + ".portal.quiz_prefill", {ROOT + ".api.configurator_engine": engine}) as (
			service,
			frappe,
		):
			frappe.db.exists.return_value = True
			result = service.resolve(
				"Linear Fixture",
				"EL01",
				{
					"moisture": "Damp",
					"cct": "3000K",
					"lens": "Clear",
					"finish": "Silver",
					"mounting": "Surface",
					"light_type": "Static white",
				},
			)
		self.assertEqual(calls, [None, "SW-PKG"])
		self.assertEqual(
			result["selections"],
			{
				"environment_rating_code": "Damp Location",
				"cct_code": "3000K",
				"finish_code": "Anodized Silver",
				"mounting_method_code": "Surface Clip",
				"led_package_code": "SW-PKG",
			},
		)
		self.assertEqual(result["unmatched"], [{"field": "lens", "answer": "Clear"}])

	def test_tape_and_neon_use_the_template_rows_and_skip_fields_they_do_not_have(self):
		template = Record(
			allowed_options=[
				Record(option_type="CCT", cct="3000K", is_active=1),
				Record(option_type="CCT", cct="4000K", is_active=0),
				Record(option_type="Finish", finish="White", is_active=1),
			],
			allowed_tape_specs=[Record(environment_rating="Wet")],
		)
		details = {
			"ilL-Attribute-CCT": [Record(name="3000K", label="3000K", code="30", kelvin=3000)],
			"ilL-Attribute-Finish": [Record(name="White", code="WH")],
			"ilL-Attribute-Environment Rating": [Record(name="Wet", label="Wet", code="W")],
		}
		with load_service(ROOT + ".portal.quiz_prefill") as (service, frappe):
			frappe.db.exists.return_value = True
			frappe.get_cached_doc = MagicMock(return_value=template)
			frappe.get_all.side_effect = lambda doctype, filters=None, **kwargs: details[doctype]
			result = service.resolve(
				"LED Neon", "NEON-1", {"moisture": "wet", "cct": "4000K", "finish": "White", "lens": "Clear"}
			)
			requested = {call.args[0]: call.kwargs["filters"] for call in frappe.get_all.call_args_list}
		self.assertEqual(result["selections"], {"environment_rating": "Wet", "finish": "White"})
		self.assertEqual(result["unmatched"], [{"field": "cct", "answer": "4000K"}])
		self.assertEqual(requested["ilL-Attribute-CCT"], {"name": ["in", ["3000K"]]})

	def test_other_families_and_unknown_templates(self):
		with load_service(ROOT + ".portal.quiz_prefill") as (service, frappe):
			self.assertEqual(service.resolve("LED Sheet", "S1", {"cct": "3000K"})["selections"], {})
			frappe.db.exists.return_value = False
			frappe.get_all.side_effect = lambda doctype, **kwargs: (
				[Record(name="Damp", label="Damp")] if "Environment" in doctype else []
			)
			result = service.resolve("LED Tape", None, {"moisture": "Damp"})
		self.assertEqual(result["selections"], {"environment_rating": "Damp"})


if __name__ == "__main__":
	unittest.main()
