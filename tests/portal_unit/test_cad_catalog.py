"""CAD catalog projection (draw-to-quote plan 1.3): drawing data only, never prices.

The records in ``tools/system_designer/fixtures/cad/catalog-records.json`` build the committed
``catalog.sample.json`` the AutoLISP tests and the ``ilq/2`` writer read. Regenerate after a deliberate
mapping change with ``python3 -B tests/portal_unit/test_cad_catalog.py --write``.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

from test_services import ROOT, load_service

MODULE = ROOT + ".system_design.cad_catalog"
FIXTURES = Path(__file__).resolve().parents[2] / "tools/system_designer/fixtures/cad"
RECORDS = json.loads((FIXTURES / "catalog-records.json").read_text(encoding="utf-8"))


def records():
	return copy.deepcopy(RECORDS)


class CadCatalog(unittest.TestCase):
	def setUp(self):
		self.context = load_service(MODULE)
		self.module, _frappe = self.context.__enter__()
		self.payload = self.module.build_payload(records())
		self.templates = {row["code"]: row for row in self.payload["templates"]}

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def test_committed_sample_matches_the_mapping(self):
		expected = json.loads((FIXTURES / "catalog.sample.json").read_text(encoding="utf-8"))
		self.assertEqual(json.loads(json.dumps(self.payload)), expected)

	def test_no_price_cost_or_rank_anywhere(self):
		self.assertEqual(self.module.forbidden_keys(self.payload), set())
		text = json.dumps(self.payload)
		for word in ("msrp", "adder", "rank", "cost", "price"):
			self.assertNotIn(word, text.lower())

	def test_forbidden_keys_refuse_a_priced_style(self):
		data = records()
		data["styles"][0]["selections"]["unit_price"] = 10
		with self.assertRaisesRegex(ValueError, "unit_price"):
			self.module.build_payload(data)

	def test_tape_variants_carry_offering_overrides_in_inches(self):
		variants = {row["id"]: row for row in self.templates["led-hd-sw"]["variants"]}
		base = variants["TEST-HD-SW-24|OFF-1"]
		self.assertEqual(base["w_per_ft"], 4.4)
		self.assertEqual(base["cut_mm"], 50)
		self.assertEqual(base["cut_in"], 1.9685)
		self.assertEqual(base["max_run_single_ft"], 16.4)
		self.assertEqual(base["max_run_double_ft"], 32.8)
		self.assertEqual(base["reel_ft"], 16.4042)
		self.assertEqual(base["environment_rating"], "Dry")
		bright = variants["TEST-HD-SW-24|OFF-2"]
		self.assertEqual((bright["w_per_ft"], bright["cut_mm"]), (6.2, 100))
		self.assertEqual(variants["TEST-HD-SW-24-WET|OFF-3"]["environment_rating"], "Wet")
		self.assertEqual(self.templates["led-hd-sw"]["default_variant"], "TEST-HD-SW-24|OFF-1")

	def test_bend_radius_spec_first_then_half_the_template_diameter(self):
		variants = {row["id"]: row for row in self.templates["led-hd-sw"]["variants"]}
		self.assertNotIn("min_bend_radius_in", variants["TEST-HD-SW-24|OFF-1"])
		self.assertEqual(variants["TEST-HD-SW-24-WET|OFF-3"]["min_bend_radius_in"], 1)
		neon = self.templates["non-pnc-sw"]["variants"][0]
		self.assertEqual(neon["min_bend_radius_in"], 1.9685)
		self.assertEqual(neon["max_run_single_ft"], 32.8)  # voltage-drop fallback

	def test_free_cut_tape_has_no_cut_interval(self):
		variant = self.templates["cob-fc-sw"]["variants"][0]
		self.assertTrue(variant["free_cut"])
		self.assertNotIn("cut_in", variant)

	def test_options_are_active_ordered_and_defaulted(self):
		options = self.templates["led-hd-sw"]["options"]
		self.assertEqual([row["key"] for row in options], ["environment_rating", "cct", "output_level", "feed_type", "feed_direction"])
		cct = options[1]
		self.assertEqual(cct["values"], ["2700K", "3000K"])
		self.assertEqual(cct["default"], "3000K")
		self.assertEqual(options[2]["default"], "300 lm/ft")

	def test_profiles_fixture_and_kit_templates(self):
		profiles = {row["code"]: row for row in self.payload["profiles"]}
		self.assertEqual(profiles["CH-AZ01-SV"]["width_in"], 0.685)
		self.assertEqual(profiles["CH-AZ01-SV"]["stock_length_in"], 78.7402)
		self.assertFalse(profiles["CH-AZ01-SV"]["curve_capable"])
		self.assertEqual(profiles["CH-AZ01-SV"]["outline"]["body"][:2], [-0.342, 0])
		self.assertTrue(profiles["CH-RA01-BK"]["curve_capable"])
		self.assertNotIn("outline", profiles["CH-RA01-BK"])
		self.assertEqual(self.payload["kit_templates"][0]["profile"], "CH-AZ01-SV")
		self.assertEqual(self.payload["fixture_templates"][0]["max_assembled_in"], 98.4252)

	def test_design_items_drop_ranks_and_keep_tags(self):
		driver = self.payload["drivers"][0]
		self.assertEqual(driver["code"], "PS-96-24")
		self.assertEqual((driver["outputs"], driver["per_output_w"], driver["class2"]), (1, 96, True))
		self.assertEqual(self.payload["controllers"][0]["category"], "dmx-decoder")
		self.assertEqual(self.payload["wires"][0]["awg"], "18")

	def test_hash_ignores_who_and_when(self):
		data = records()
		data["generated_at"] = "2027-01-01 00:00:00"
		data["styles"] = []
		self.assertEqual(self.module.build_payload(data)["hash"], self.payload["hash"])
		data["tapes"][0]["watts_per_foot"] = 4.5
		self.assertNotEqual(self.module.build_payload(data)["hash"], self.payload["hash"])

	def test_settings_are_the_designer_ones_only(self):
		self.assertNotIn("terms_text", self.payload["settings"])
		self.assertEqual(self.payload["settings"]["plan_route_slack_pct"], 15.0)

	def test_template_index(self):
		index = self.module.template_index(self.payload)
		self.assertIn(("LED Tape", "led-hd-sw"), index)
		self.assertIn(("Extrusion Kit", "KIT-AZ01"), index)
		self.assertIn(("Linear Fixture", "ILL-RA01-SW"), index)


def write():
	with load_service(MODULE) as (module, _frappe):
		payload = module.build_payload(records())
	(FIXTURES / "catalog.sample.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
	if "--write" in sys.argv:
		write()
	else:
		unittest.main()
