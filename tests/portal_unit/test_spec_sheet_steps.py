"""Reading a schedule line into its generated spec sheet's values (api/spec_sheet_steps.py)."""

import json
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


def row(step, option_type, label, values, **extra):
	return {
		"option_step": step,
		"option_type": option_type,
		"option_label": label,
		"allowed_values_json": json.dumps(values),
		**extra,
	}


def codes(*values):
	return [{"code": value, "label": value} for value in values]


FIXTURE = [
	row(0, "Series", "Series", codes("ILL-SH03-SW")),
	row(1, "Environment Rating", "Dry/Wet", codes("20", "67")),
	row(2, "CCT", "CCT", codes("27K", "30K")),
	row(3, "Lens Appearance", "Lens", codes("WH", "FR")),
	row(4, "Output Level", "Output", codes("100", "200")),
	row(5, "Mounting Method", "Mounting", codes("MC")),
	row(6, "Finish", "Finish", codes("SV", "BK")),
	row(7, "Length", "Length", [{"value": "__length_metadata__", "label": "Length", "code": ""}]),
	row(8, "Feed Direction", "Start Feed Direction", codes("E", "B")),
	row(9, "Feed Direction", "Start Feed Length", codes("1", "5")),
	row(10, "Feed Direction", "End Feed Direction", codes("C", "E")),
	row(11, "Feed Direction", "End Feed Length", codes("1")),
	row(98, "Fixture Output Level", "Fixture Output Level", codes("x")),
	row(99, "Endcap Color", "Endcap Color", codes("y")),
]
KIT = [
	row(1, "Lens Appearance", "Lens", codes("WH", "CL")),
	row(2, "Mounting Method", "Mounting", codes("MC", "MG")),
	row(3, "Finish", "Finish", codes("BK", "WH")),
	row(4, "Length", "Length", [{"code": "2M", "label": "2M (6.56ft)", "is_default": 1}]),
]


def service(extras=None):
	packets = types.ModuleType("packets")
	packets._part_number = lambda line: line.get("part_number")
	packets._template_spec_sheet = lambda build: ("ilL-Fixture-Template", "ILL-SH03-SW", "/files/s.pdf")
	submittal = types.ModuleType("spec_submittal")
	submittal._driver_document_source = MagicMock(return_value=None)
	submittal._controller_document_source = MagicMock(return_value=None)
	stubs = {ROOT + ".portal.packets": packets, ROOT + ".api.spec_submittal": submittal, **(extras or {})}
	return load_service(ROOT + ".api.spec_sheet_steps", stubs)


class StepsFromPartNumber(unittest.TestCase):
	def test_fixture_part_number_fills_every_step_even_out_of_step_order(self):
		with service() as (module, _frappe):
			steps, warnings = module.steps_from_part_number(
				"ILL-SH03-SW-20-30K-200-WH-MC-SV-216.0-E1-C", "ILL-SH03-SW", FIXTURE
			)
		self.assertEqual(warnings, [])
		self.assertEqual(
			steps,
			{
				"1": "20",
				"2": "30K",
				"3": "WH",
				"4": "200",
				"5": "MC",
				"6": "SV",
				"7": "216.0",
				"8": "E",
				"9": "1",
				"10": "C",
			},
		)

	def test_kit_takes_its_stock_length_when_the_part_number_leaves_it_out(self):
		with service() as (module, _frappe):
			steps, warnings = module.steps_from_part_number("KIT-SH01-CL-MC-BK", "kit-sh01", KIT)
		self.assertEqual(warnings, [])
		self.assertEqual(steps, {"1": "CL", "2": "MC", "3": "BK", "4": "2M"})

	def test_the_same_code_in_two_steps_goes_to_each_in_turn(self):
		with service() as (module, _frappe):
			steps, _warnings = module.steps_from_part_number("KIT-SH01-WH-MC-WH", "KIT-SH01", KIT)
		self.assertEqual(steps["1"], "WH")
		self.assertEqual(steps["3"], "WH")

	def test_unknown_and_leftover_codes_are_warned_not_guessed(self):
		with service() as (module, _frappe):
			steps, warnings = module.steps_from_part_number("KIT-SH01-ZZ-MC-BK-EXTRA", "KIT-SH01", KIT)
		self.assertNotIn("1", steps)
		self.assertIn("Lens: the part number KIT-SH01-ZZ-MC-BK-EXTRA has no code", warnings[0])
		self.assertIn("ZZ, EXTRA did not match a step", warnings[1])

	def test_build_codes_that_disagree_are_warned(self):
		with service() as (module, _frappe):
			warnings = module.compare_with_build(
				{"3": "WH", "6": "SV"},
				FIXTURE,
				"ilL-Configured-Fixture",
				{"sku_lens_code": "FR", "sku_finish_code": "sv"},
			)
		self.assertEqual(warnings, ["Lens: the part number says WH, the build says FR"])


class LineText(unittest.TestCase):
	def schedule(self):
		return Record(
			ill_project="PRJ-1",
			schedule_name="Main",
			lines=[
				Record(name="R1", line_key="K1", line_id="L1", qty=4, location="Lobby"),
				Record(name="R2", line_key="K2", line_id="L2", qty=2, location=""),
				Record(
					name="R3",
					line_key="K3",
					line_id="PS1",
					qty=1,
					manufacturer_type="ACCESSORY",
					power_supply_for_line="K1",
					part_number="PS-UNIV-96W",
				),
			],
		)

	def test_footer_text_uses_the_line_location_then_the_project(self):
		with service() as (module, frappe):
			frappe.db.get_value.return_value = {"project_name": "Seattle Library", "location": "Seattle"}
			schedule = self.schedule()
			first = module.project_text(schedule, schedule.lines[0])
			second = module.project_text(schedule, schedule.lines[1])
			supply = module.project_text(schedule, schedule.lines[2])
		self.assertEqual(
			first, {"project_name": "Seattle Library", "fixture_type": "L1", "project_location": "Lobby"}
		)
		self.assertEqual(second["project_location"], "Seattle")
		self.assertEqual(supply["fixture_type"], "L1")

	def test_line_summary_lists_qty_length_runs_watts_and_supplies(self):
		with service() as (module, _frappe):
			schedule = self.schedule()
			summary = module.line_summary(
				schedule,
				schedule.lines[0],
				"ilL-Configured-Fixture",
				{"manufacturable_overall_length_mm": 5486.4, "runs_count": 2, "total_watts": 86.4},
			)
		self.assertEqual(
			summary, "Qty 4 · Built length 216.0″ · 2 runs · 86.4W total · Power: PS-UNIV-96W (PS1)"
		)


class Resolve(unittest.TestCase):
	def test_a_fixture_line_resolves_its_sheet_steps_and_text(self):
		with service() as (module, frappe):
			frappe.get_all.side_effect = lambda doctype, **kw: (
				["illumenate"] if doctype == "ilL-Child-Webflow-Brand-Target" else FIXTURE
			)

			def get_value(doctype, name, fields, **kw):
				if doctype == "ilL-Fixture-Template":
					return "/files/sh03.pdf"
				if doctype == "ilL-Project":
					return {"project_name": "Seattle Library", "location": "Seattle"}
				return {"sku_lens_code": "WH", "manufacturable_overall_length_mm": 5486, "total_watts": 40}

			frappe.db.get_value.side_effect = get_value
			line = Record(
				name="R1",
				line_id="L1",
				qty=1,
				location="Lobby",
				manufacturer_type="ILLUMENATE",
				configured_fixture="ILL-CF-1",
				part_number="ILL-SH03-SW-20-30K-200-WH-MC-SV-216.0-E1-C",
			)
			result = module.resolve(Record(ill_project="PRJ-1", lines=[line]), line)
		self.assertEqual(result["sheet_url"], "/files/sh03.pdf")
		self.assertEqual(result["steps"]["7"], "216.0")
		self.assertEqual(result["text"]["fixture_type"], "L1")
		self.assertIn("Built length", result["text"]["line_summary"])
		self.assertEqual(result["build"], {"doctype": "ilL-Configured-Fixture", "name": "ILL-CF-1"})
		self.assertEqual(result["warnings"], [])

	def test_206_lighting_templates_stay_on_the_old_path(self):
		with service() as (module, frappe):
			frappe.get_all.return_value = ["lighting_206"]
			line = Record(name="R1", manufacturer_type="ILLUMENATE", configured_fixture="CF")
			self.assertIsNone(module.resolve(Record(lines=[line]), line))

	def test_other_manufacturers_have_no_generated_sheet(self):
		with service() as (module, _frappe):
			line = Record(name="R1", manufacturer_type="OTHER")
			self.assertIsNone(module.resolve(Record(lines=[line]), line))

	def test_a_template_without_steps_says_to_save_it(self):
		with service() as (module, frappe):
			frappe.get_all.side_effect = lambda doctype, **kw: (
				["illumenate"] if doctype == "ilL-Child-Webflow-Brand-Target" else []
			)
			frappe.db.get_value.side_effect = lambda doctype, *a, **kw: (
				"/files/sh03.pdf" if doctype == "ilL-Fixture-Template" else {}
			)
			line = Record(name="R1", manufacturer_type="ILLUMENATE", configured_fixture="CF", part_number="X")
			result = module.resolve(Record(lines=[line]), line)
		self.assertEqual(result["steps"], {})
		self.assertIn("has no Part Number Builder steps", result["warnings"][0])


class Readiness(unittest.TestCase):
	def test_lists_which_templates_a_packet_can_fill(self):
		fill = types.ModuleType("spec_sheet_fill")
		fill.inspect = lambda content: {
			"has_form": content == b"generated",
			"steps": {"1": ["WH"]} if content == b"generated" else {},
			"highlight_style": "steps" if content == b"generated" else "none",
		}
		schema = types.ModuleType("web_listing_schema")
		schema.TEMPLATE_DOCTYPES = {"ilL-Extrusion-Kit-Template": "x"}
		files = {"/files/new.pdf": b"generated", "/files/old.pdf": b"indesign"}
		with service({ROOT + ".api.spec_sheet_fill": fill, ROOT + ".web_listing_schema": schema}) as (
			module,
			frappe,
		):
			sys_submittal = __import__("sys").modules[ROOT + ".api.spec_submittal"]
			sys_submittal._get_file_doc_by_url = lambda url: types.SimpleNamespace(
				get_content=lambda: files[url]
			)
			frappe.only_for = MagicMock()

			def get_all(doctype, **kwargs):
				if doctype == "ilL-Extrusion-Kit-Template":
					return ["KIT-RA01", "KIT-RA02"]
				if doctype == "ilL-Child-Webflow-Brand-Target":
					return ["illumenate"]
				return KIT

			frappe.get_all.side_effect = get_all
			frappe.db.get_value.side_effect = lambda doctype, name, field: (
				"/files/new.pdf" if name == "KIT-RA01" else "/files/old.pdf"
			)
			report = module.readiness()
		frappe.only_for.assert_called_once_with("System Manager")
		self.assertEqual((report["ready"], report["total"]), (1, 2))
		self.assertTrue(report["templates"][0]["ready"])
		self.assertFalse(report["templates"][1]["has_form"])


if __name__ == "__main__":
	unittest.main()
