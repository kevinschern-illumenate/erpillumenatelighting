"""Pre-fill never invents choices that the selected template does not offer."""

import types
import unittest
from unittest.mock import MagicMock

from test_product_finder_content import FakeDocument
from test_services import ROOT, Record, load_service

BASE = ROOT + ".portal.product_finder"


class Prefill(unittest.TestCase):
	def test_every_family_uses_allowed_values_and_driver_load(self):
		for family in (
			"Linear Fixture",
			"LED Tape",
			"LED Neon",
			"LED Sheet",
			"Extrusion Kit",
			"Driver",
			"Controller",
		):
			with (
				self.subTest(family=family),
				load_service(
					BASE + ".prefill",
					{
						BASE + ".matcher": types.SimpleNamespace(
							requirements=lambda *a: [
								{
									"facet": "finish",
									"wanted": ["White"],
									"answer": "white",
									"answer_label": "White",
									"selected": [],
								},
								{
									"facet": "driver_wattage",
									"wanted": [],
									"answer": 75,
									"answer_label": "75 W",
									"selected": [],
								},
							]
						),
						ROOT + ".api.driver_controller_configurator": types.SimpleNamespace(
							_allowed_values=lambda doc, axis: [
								{"value": v} for v in ([60, 96, 120] if axis == "Wattage" else ["White"])
							]
						),
					},
				) as (service, frappe),
			):
				frappe.get_cached_doc = MagicMock(
					return_value=FakeDocument(
						is_active=1,
						allowed_options=[Record(is_active=1, option_type="Finish", finish="White")],
					)
				)
				service._linear_candidates = lambda *a: {"ilL-Attribute-Finish": [{"value": "White"}]}
				result = service.prefill_for_template(family, "T", {}, {"questions": []})
				selections = result["selections"]
				if family == "LED Sheet":
					self.assertEqual(selections["options"]["Finish"], "White")
				else:
					self.assertEqual(
						selections.get("finish_code" if family == "Linear Fixture" else "finish"), "White"
					)
				if family in ("Driver", "Controller"):
					self.assertEqual(selections["wattage"], 96)
				self.assertNotIn("Black", str(selections))

	def test_inactive_template_has_no_prefill(self):
		with load_service(BASE + ".prefill") as (service, frappe):
			frappe.get_cached_doc = MagicMock(return_value=Record(is_active=0))
			self.assertEqual(
				service.prefill_for_template("LED Tape", "T", {}, {"questions": []})["selections"], {}
			)

	def test_sheet_package_selects_a_real_spec(self):
		with load_service(
			BASE + ".prefill",
			{
				BASE + ".matcher": types.SimpleNamespace(
					requirements=lambda *a: [{"facet": "light_type", "answer": "Static white"}]
				)
			},
		) as (service, frappe):
			frappe.get_cached_doc = MagicMock(
				return_value=FakeDocument(is_active=1, allowed_specs=[Record(spec="S", is_active=1)])
			)
			frappe.get_all.side_effect = [[Record(name="S", led_package="W", cct="3000K")], ["W"]]
			result = service.prefill_for_template("LED Sheet", "T", {}, {"questions": []})
			self.assertEqual(result["selections"]["spec"], "S")
