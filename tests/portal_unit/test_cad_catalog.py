"""CAD catalog projection (draw-to-quote plan 1.3): drawing data only, never prices.

The records in ``tools/system_designer/fixtures/cad/catalog-records.json`` build the committed
``catalog.sample.json`` the AutoLISP tests and the ``ilq/2`` writer read. Regenerate after a deliberate
mapping change with ``python3 -B tests/portal_unit/test_cad_catalog.py --write``.
"""

import copy
import json
import sys
import types
import unittest
from pathlib import Path

from test_services import ROOT, Record, load_service

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

	def test_linear_templates_carry_the_configurator_cascade(self):
		linear = self.payload["fixture_templates"][0]["linear"]
		combos = {(c["led_package"], c["environment"], c["cct"], c["lens"]): c["outputs"] for c in linear["combos"]}
		# 300 and 600 lm/ft tape behind a 90 % frosted lens deliver 270 and 540: the 250 and 500 levels.
		self.assertEqual(combos[("SW-2835", "Dry", "2700K", "Frosted")], [250, 500])
		# A 56 % white lens (stored as a percent) needs the same tape for lower levels.
		self.assertEqual(combos[("SW-2835", "Dry", "2700K", "White")], [150, 350])
		# Environment rows narrow the tape: only the Wet offering, in 3000K, builds a Wet fixture.
		self.assertEqual(combos[("SW-2835", "Wet", "3000K", "Frosted")], [250])
		self.assertNotIn(("SW-2835", "Wet", "2700K", "Frosted"), combos)
		# A Tunable White package offers its own CCTs; its generic-CCT offering builds each of them.
		self.assertEqual(combos[("TW-2835", "Dry", "3000K", "White")], [200])
		self.assertEqual([row["value"] for row in linear["environments"]], ["Dry", "Wet"])  # Damp inactive
		self.assertEqual(linear["environments"][0]["label"], "Dry Location")
		self.assertEqual([row["value"] for row in linear["ccts"]], ["2700K", "3000K"])
		self.assertEqual(
			[(row["value"], row["transmission_pct"]) for row in linear["lenses"]], [("Frosted", 90.0), ("White", 56.0)]
		)
		self.assertEqual(linear["finishes"][0], {"value": "BK", "label": "Black"})
		self.assertEqual(
			linear["defaults"],
			{"environment": "Dry", "lens": "Frosted", "mounting": "Surface", "finish": "BK", "feed_type": "Wire Leads"},
		)
		self.assertEqual([row["value"] for row in linear["feed_directions"]], ["Back", "End"])

	def test_linear_template_without_buildable_tape_has_no_options(self):
		data = records()
		data["linear"]["tape_rows"]["ILL-RA01-SW"] = [{"tape_offering": "OFF-GONE"}]
		self.assertNotIn("linear", self.module.build_payload(data)["fixture_templates"][0])
		data = records()
		del data["linear"]
		self.assertNotIn("linear", self.module.build_payload(data)["fixture_templates"][0])

	def test_linear_fallbacks_follow_the_engine(self):
		data = records()
		linear = data["linear"]
		# No allowed environment, lens or mounting rows: every record is offered, as in the portal.
		linear["options"]["ILL-RA01-SW"] = [
			row for row in linear["options"]["ILL-RA01-SW"] if row["option_type"] not in ("Lens Appearance", "Mounting Method")
		]
		# A static package with its own CCT list meets the tape CCTs; inactive CCTs are left out.
		linear["led_packages"]["SW-2835"]["ccts"] = ["3000K", "2700K"]
		linear["ccts"][1]["is_active"] = 0
		options = self.module.build_payload(data)["fixture_templates"][0]["linear"]
		self.assertEqual([row["value"] for row in options["mountings"]], ["Surface", "Recessed"])
		self.assertEqual({c["cct"] for c in options["combos"] if c["led_package"] == "SW-2835"}, {"2700K"})
		self.assertNotIn("lens", options["defaults"])

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
		controls = {row["code"]: row for row in self.payload["controllers"]}
		decoder = controls["DMXD-PWM-5C-SF"]
		self.assertEqual((decoder["category"], decoder["kind"], decoder["dmx_footprint"]), ("dmx-decoder", "decoder", 5))
		self.assertTrue(decoder["receives_dmx"])
		self.assertEqual(controls["DMXC-TW-BK-WALL"]["ports"], [{"name": "DMX512", "direction": "out", "protocol": "DMX512"}])
		self.assertEqual(controls["PIX-4"]["max_data_length_ft"], 15)
		self.assertNotIn("receives_dmx", controls["PIX-4"])
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

	def test_minimum_toolkit_version_is_published_when_set(self):
		self.assertNotIn("min_toolkit_version", self.payload["settings"])
		data = records()
		data["min_toolkit_version"] = "0.5.0"
		self.assertEqual(self.module.build_payload(data)["settings"]["min_toolkit_version"], "0.5.0")

	def test_template_index(self):
		index = self.module.template_index(self.payload)
		self.assertIn(("LED Tape", "led-hd-sw"), index)
		self.assertIn(("Extrusion Kit", "KIT-AZ01"), index)
		self.assertIn(("Linear Fixture", "ILL-RA01-SW"), index)


class Styles(unittest.TestCase):
	"""Run styles from configuration presets, with their short drawing codes (CAD plan WP 1.2)."""

	def setUp(self):
		self.actor = Record(user="buyer@example.com", customer="CUST-A", is_internal=False)
		self.revalidated = []

		def revalidate(request):
			self.revalidated.append(request["template"])
			return (None, ["gone"]) if request["template"] == "gone" else (request, [])

		def is_cad_enabled(value):
			return value is None or bool(int(value))

		self.extras = {
			ROOT + ".portal.site_flags": types.SimpleNamespace(presets_enabled=lambda: True),
			ROOT + ".portal.access": types.SimpleNamespace(get_actor=lambda user=None: self.actor),
			ROOT + ".portal.presets": types.SimpleNamespace(revalidate=revalidate, is_cad_enabled=is_cad_enabled),
		}

	@staticmethod
	def preset(name, template="led-hd-sw", **values):
		request = {"family": "LED Tape", "template": template, "selections": {"cct": "2700K"}}
		values = {"shared_with_company": 0, **values}
		return Record(name=name, label=name, family="LED Tape", template=template, request_json=json.dumps(request),
			**values)

	def test_style_row_carries_the_code_only_when_set(self):
		with load_service(MODULE) as (module, _frappe):
			request = {"family": "LED Tape", "template": "led-hd-sw", "selections": {}}
			row = module.style_row(Record(name="P1", label="Cove", cad_code="HD27"), request)
			self.assertEqual(row["code"], "HD27")
			self.assertEqual(row["id"], "preset:P1")
			for empty in (None, ""):
				self.assertNotIn("code", module.style_row(Record(name="P1", label="Cove", cad_code=empty), request))
			self.assertNotIn("code", module.style_row(Record(name="P1", label="Cove"), request))

	def test_load_styles_skips_presets_switched_off_for_cad(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			frappe.db.exists.return_value = True
			frappe.db.has_column.return_value = True
			own = [
				self.preset("ON", cad_code="HD27", cad_enabled=1),
				self.preset("OFF", cad_code="OFF", cad_enabled=0),
				self.preset("LEGACY", cad_enabled=None),
				self.preset("GONE", template="gone"),
			]
			shared = [self.preset("SHARED", shared_with_company=1, cad_enabled=1), self.preset("ON", cad_enabled=1)]
			frappe.get_all.side_effect = [own, shared]
			styles = {row["id"]: row for row in module.load_styles("buyer@example.com")}
			self.assertEqual(set(styles), {"preset:ON", "preset:LEGACY", "preset:SHARED"})
			self.assertEqual(styles["preset:ON"]["code"], "HD27")
			self.assertNotIn("code", styles["preset:LEGACY"])
			self.assertNotIn("OFF", self.revalidated, "switched-off presets are not even re-checked")
			fields = frappe.get_all.call_args_list[0].kwargs["fields"]
			self.assertIn("cad_code", fields)
			self.assertIn("cad_enabled", fields)
			self.assertEqual(module.forbidden_keys(list(styles.values())), set())

	def test_load_styles_before_the_migration_reads_no_cad_fields(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			frappe.db.exists.return_value = True
			frappe.db.has_column.return_value = False
			frappe.get_all.side_effect = [[self.preset("P1")], []]
			styles = module.load_styles()
			self.assertEqual([row["id"] for row in styles], ["preset:P1"])
			self.assertNotIn("cad_code", frappe.get_all.call_args_list[0].kwargs["fields"])


def write():
	with load_service(MODULE) as (module, _frappe):
		payload = module.build_payload(records())
	(FIXTURES / "catalog.sample.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")


class LinearLoader(unittest.TestCase):
	"""``load_linear`` reads the rows ``linear_options`` needs, dropping disabled and inactive tape."""

	def test_loader_rows_build_the_same_cascade(self):
		linear = records()["linear"]
		availability = types.SimpleNamespace(disabled_tape_offerings=lambda names: {"OFF-L2"})
		extras = {ROOT + ".api.item_availability": availability}
		with load_service(MODULE, extras) as (module, frappe):
			tape_rows = [{**row, "parent": "ILL-RA01-SW"} for row in linear["tape_rows"]["ILL-RA01-SW"]]
			option_rows = [{**row, "parent": "ILL-RA01-SW"} for row in linear["options"]["ILL-RA01-SW"]]

			def get_all(doctype, filters=None, fields=None, **kwargs):
				if doctype == "ilL-Child-Template-Allowed-Option":
					return [Record(row) for row in option_rows]
				if doctype == "ilL-Child-Template-Allowed-TapeOffering":
					return [Record(row) for row in tape_rows]
				if doctype == "ilL-Rel-Tape Offering":
					self.assertEqual(filters["is_active"], 1)
					return [Record(row) for name, row in linear["offerings"].items() if name in filters["name"][1]]
				if doctype == "ilL-Attribute-LED Package":
					return [Record(name=name, spectrum_type=row["spectrum_type"]) for name, row in linear["led_packages"].items()]
				if doctype == "ilL-Child-LED Package CCT":
					return [Record(parent="TW-2835", cct=cct) for cct in ("2700K", "3000K")]
				if doctype == "ilL-Attribute-Output Level":
					return [Record(row) for row in linear["output_levels"].values()]
				if doctype == "ilL-Attribute-CCT":
					return [Record(row) for row in linear["ccts"]]
				if doctype == "ilL-Attribute-Lens Appearance":
					return [Record(row) for row in linear["lenses"].values()]
				if doctype == "ilL-Attribute-Environment Rating":
					return [Record(row) for row in linear["environments"]]
				if doctype == "ilL-Attribute-Finish":
					return [Record(row) for row in linear["finishes"]]
				if doctype == "ilL-Attribute-Mounting Method":
					return [Record(row) for row in linear["mountings"]]
				if doctype == "ilL-Attribute-Power Feed Type":
					return [Record(row) for row in linear["feed_types"]]
				if doctype == "ilL-Attribute-Feed-Direction":
					return [Record(direction_name=name) for name in linear["feed_directions"]]
				raise AssertionError(doctype)

			frappe.get_all.side_effect = get_all
			frappe.db.has_column.return_value = True
			frappe.db.exists.return_value = True
			loaded = module.load_linear(["ILL-RA01-SW"])
			self.assertNotIn("OFF-L2", loaded["offerings"])  # its tape Item is disabled
			self.assertEqual(loaded["led_packages"]["TW-2835"]["ccts"], ["2700K", "3000K"])
			options = module.linear_options("ILL-RA01-SW", loaded)
		combos = {(c["led_package"], c["environment"], c["cct"], c["lens"]): c["outputs"] for c in options["combos"]}
		self.assertEqual(combos[("SW-2835", "Dry", "2700K", "Frosted")], [250])  # 600 lm/ft tape is disabled
		self.assertEqual(combos[("TW-2835", "Wet", "2700K", "White")], [200])


if __name__ == "__main__":
	if "--write" in sys.argv:
		write()
	else:
		unittest.main()
