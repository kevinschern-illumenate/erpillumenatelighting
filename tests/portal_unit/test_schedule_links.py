"""Schedule line links carry the stable line key, and the configurator page tolerates stale ones."""

import re
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

REPO = Path(__file__).resolve().parents[2]
PAGES = REPO / "illumenate_lighting/templates/pages"


class ScheduleLineContract(unittest.TestCase):
	def test_every_line_field_the_template_reads_is_provided(self):
		template = (PAGES / "schedule.html").read_text(encoding="utf8")
		source = (PAGES / "schedule.py").read_text(encoding="utf8")
		builder = source[source.index("line_dict = {") : source.index("lines_with_details.append")]
		provided = set(re.findall(r'"([a-z_]+)":', builder)) | set(
			re.findall(r'line_dict\["([a-z_]+)"\]', builder)
		)
		used = set(re.findall(r"\bline\.get\('([a-z_]+)'", template)) | set(
			re.findall(r"\bline\.([a-z_]+)\b(?!\()", template)
		)
		self.assertEqual(sorted(used - provided), [])

	def test_configure_links_use_the_line_key(self):
		template = (PAGES / "schedule.html").read_text(encoding="utf8")
		links = re.findall(r"line_key=\{\{ ([^}]+) \}\}", template)
		self.assertTrue(links)
		for expression in links:
			self.assertIn("line.get('line_key')", expression)


class Context(Record):
	__setattr__ = dict.__setitem__


def configure_page(
	form,
	resolve_line,
	drafts=True,
	for_line=None,
	copy=True,
	decode=None,
	pn=True,
	preset=None,
	presets=True,
	estimate=True,
):
	"""Load configure.py with only the boundaries its schedule-line branch touches."""
	stubs = {}
	for name, attributes in {
		".portal.access": {
			"can_view_catalog": lambda: True,
			"get_actor": lambda: Record(is_dealer=True, customer="CUST-A", is_internal=False),
		},
		".portal.presets": {"load": preset or (lambda name, schedule_name=None: None)},
		".portal.site_flags": {
			"presets_enabled": lambda: presets,
			"live_estimate_enabled": lambda: estimate,
			"conf_flag": lambda flag: False,
			"fixture_groups_enabled": lambda: False,
			"durable_drafts_enabled": lambda: drafts,
			"line_copy_enabled": lambda: copy,
			"part_number_decode_enabled": lambda: pn,
			"sheet_server_options_enabled": lambda: True,
			"build_preview_enabled": lambda: True,
		},
		".portal.part_number": {"NotAPartNumber": NotAPartNumber, "decode": decode or (lambda value: None)},
		".portal.rollout": {"require_family": lambda family: None},
		".portal.configuration": {
			"resolve_line": resolve_line,
			"family_for_template": lambda family, template: family,
		},
		".portal.configuration_reopen": {"for_line": for_line or (lambda line: None)},
		".api.configuration_contract": {
			"finite_number": lambda value, **kwargs: float(value),
			"TAPE_CATEGORIES": ("LED Tape", "COB Tape"),
			"TAPE_NEON_CATEGORIES": ("LED Tape", "COB Tape", "LED Neon"),
		},
		".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule": {
			"has_permission": lambda doc, ptype, user: True
		},
	}.items():
		stubs[ROOT + name] = types.ModuleType(ROOT + name)
		stubs[ROOT + name].__dict__.update(attributes)
	utils = types.ModuleType("frappe.utils")
	utils.quote = lambda value, safe="": value
	utils.get_url = lambda path: path
	stubs["frappe.utils"] = utils
	return load_service("illumenate_lighting.templates.pages.configure", stubs), form


class NotAPartNumber(ValueError):
	pass


class ConfigurePage(unittest.TestCase):
	def run_page(self, form, resolve_line, drafts=True, **page):
		loader, form = configure_page(form, resolve_line, drafts, **page)
		with loader as (module, frappe):
			frappe.session = Record(user="buyer@example.com")
			frappe.form_dict = Record(form)
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = Record(
				name="S1", ill_project="P1", modified="rev-1", lines=[Record(name="row1", line_key="KEY1")]
			)
			frappe.get_all.return_value = []
			frappe.throw = MagicMock(side_effect=RuntimeError)
			context = Context()
			try:
				module.get_context(context)
			except RuntimeError:
				return frappe.throw.call_args.args[0], None
			return None, context

	def test_serialized_null_line_key_is_ignored(self):
		resolve = MagicMock()
		error, context = self.run_page(
			{"category": "Linear Fixture", "schedule": "S1", "line_key": "None"}, resolve
		)
		self.assertIsNone(error)
		resolve.assert_not_called()
		self.assertIsNone(context.line_idx)

	def test_stale_line_key_is_a_message_not_a_server_error(self):
		def resolve(schedule, line_key):
			raise ValueError("The selected line changed or is unavailable; reload the schedule")

		error, _context = self.run_page(
			{"category": "Linear Fixture", "schedule": "S1", "line_key": "GONE"}, resolve
		)
		self.assertIn("reload the schedule", error)

	def test_line_key_selects_its_schedule_line(self):
		error, context = self.run_page(
			{"category": "Linear Fixture", "schedule": "S1", "line_key": "KEY1"},
			lambda schedule, line_key: schedule.lines[0],
		)
		self.assertIsNone(error)
		self.assertEqual((context.line_idx, context.line_key), (0, "KEY1"))
		self.assertTrue(context.draft_autosave)

	def test_configure_similar_prefills_a_new_line(self):
		request = {"family": "LED Neon", "template": "NEON-1", "selections": {}}
		resolve = MagicMock(return_value=Record(line_id="A<1>", line_key="KEY1"))
		error, context = self.run_page(
			{"schedule": "S1", "similar_to": "KEY1"}, resolve, for_line=lambda line: request
		)
		self.assertIsNone(error)
		resolve.assert_called_once()
		self.assertEqual(resolve.call_args.args[1], "KEY1")
		self.assertEqual(context.similar_to, "A<1>")
		self.assertEqual(context.initial_request, request)
		self.assertEqual(context.product_category, "LED Neon")
		self.assertIsNone(context.line_idx, "saving adds a new line")
		self.assertIsNone(context.line_key)

	def test_configure_similar_respects_the_kill_switch_and_stale_keys(self):
		resolve = MagicMock(side_effect=ValueError("The selected line changed or is unavailable; reload the schedule"))
		error, _context = self.run_page({"category": "Linear Fixture", "schedule": "S1", "similar_to": "GONE"}, resolve)
		self.assertIn("reload the schedule", error)
		error, context = self.run_page(
			{"category": "Linear Fixture", "schedule": "S1", "similar_to": "GONE"}, resolve, copy=False
		)
		self.assertIsNone(error)
		self.assertIsNone(context.similar_to)
		self.assertIsNone(context.initial_request)

	def test_part_number_prefills_a_new_fixture_line(self):
		decoded = {
			"part_number": "ILL-SH01-S",
			"template": "FT-1",
			"selections": {"fixture_template_code": "FT-1", "finish_code": "Silver"},
			"unmatched": [],
			"review": [],
		}
		calls = []
		error, context = self.run_page(
			{"schedule": "S1", "pn": "ILL-SH01-S"}, MagicMock(), decode=lambda value: calls.append(value) or decoded
		)
		self.assertIsNone(error)
		self.assertEqual(calls, ["ILL-SH01-S"])
		self.assertEqual(context.pn_prefill, decoded)
		self.assertEqual(context.initial_request, {"template": "FT-1", "selections": decoded["selections"]})
		self.assertEqual((context.product_category, context.selected_template), ("Linear Fixture", "FT-1"))
		self.assertIsNone(context.line_idx, "saving adds a new line")

	def test_preset_prefills_a_new_line_and_lists_its_problems(self):
		request = {"family": "LED Tape", "template": "TN-1", "selections": {"cct": "30K"}, "segments": []}
		calls = []

		def load(name, schedule_name=None):
			calls.append((name, schedule_name))
			return {"name": name, "label": "Cove", "family": "LED Tape", "request": request, "problems": ["Gone"]}

		error, context = self.run_page({"schedule": "S1", "preset": "P1"}, MagicMock(), preset=load)
		self.assertIsNone(error)
		self.assertEqual(calls, [("P1", "S1")], "schedule editors load with the schedule grant")
		self.assertEqual(context.preset_prefill, {"label": "Cove", "problems": ["Gone"], "usable": True})
		self.assertEqual(context.initial_request, request)
		self.assertEqual((context.product_category, context.selected_template), ("LED Tape", "TN-1"))
		self.assertEqual(context.configurator_mode, "coordinator")
		self.assertIsNone(context.line_idx, "saving adds a new line")
		self.assertTrue(context.presets_enabled)
		self.assertTrue(context.preset_can_share)

	def test_unusable_missing_or_switched_off_presets_prefill_nothing(self):
		def unusable(name, schedule_name=None):
			return {"name": name, "label": "Old", "family": "Driver", "request": None, "problems": ["DRV is gone"]}

		def missing(name, schedule_name=None):
			raise LookupError("Preset not found")

		error, context = self.run_page({"category": "Linear Fixture", "schedule": "S1", "preset": "P1"}, MagicMock(), preset=unusable)
		self.assertIsNone(error)
		self.assertEqual(context.preset_prefill, {"label": "Old", "problems": ["DRV is gone"], "usable": False})
		self.assertIsNone(context.initial_request)
		self.assertEqual(context.product_category, "Driver", "the dealer configures the preset's family again")
		for page in ({"preset": missing}, {"preset": unusable, "presets": False}):
			with self.subTest(page=page):
				error, context = self.run_page(
					{"category": "Linear Fixture", "schedule": "S1", "preset": "P1"}, MagicMock(), **page
				)
				self.assertIsNone(error)
				self.assertIsNone(context.preset_prefill)
				self.assertIsNone(context.initial_request)
				self.assertEqual(context.product_category, "Linear Fixture")

	def test_part_number_without_a_template_or_switched_off_prefills_nothing(self):
		def invalid(value):
			raise NotAPartNumber("nope")

		for page in (
			{"decode": invalid},
			{"decode": lambda value: {"template": None, "selections": {}}},
			{"decode": invalid, "pn": False},
		):
			with self.subTest(page=page):
				error, context = self.run_page({"category": "Linear Fixture", "schedule": "S1", "pn": "X"}, MagicMock(), **page)
				self.assertIsNone(error)
				self.assertIsNone(context.pn_prefill)
				self.assertIsNone(context.initial_request)

	def test_draft_autosave_needs_a_schedule_and_the_kill_switch(self):
		form = {"category": "Linear Fixture", "schedule": "S1"}
		_error, context = self.run_page(form, MagicMock())
		self.assertTrue(context.draft_autosave)
		_error, context = self.run_page(form, MagicMock(), drafts=False)
		self.assertFalse(context.draft_autosave)
		_error, context = self.run_page({"category": "Linear Fixture"}, MagicMock())
		self.assertFalse(context.draft_autosave)

	def test_live_estimate_follows_its_kill_switch(self):
		form = {"category": "Driver", "schedule": "S1"}
		_error, context = self.run_page(form, MagicMock())
		self.assertTrue(context.live_estimate)
		_error, context = self.run_page(form, MagicMock(), estimate=False)
		self.assertFalse(context.live_estimate)


if __name__ == "__main__":
	unittest.main()
