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


def configure_page(form, resolve_line):
	"""Load configure.py with only the boundaries its schedule-line branch touches."""
	stubs = {}
	for name, attributes in {
		".portal.access": {"can_view_catalog": lambda: True},
		".portal.site_flags": {"conf_flag": lambda flag: False},
		".portal.rollout": {"require_family": lambda family: None},
		".portal.configuration": {"resolve_line": resolve_line},
		".portal.configuration_reopen": {"for_line": lambda line: None},
		".api.configuration_contract": {"finite_number": lambda value, **kwargs: float(value)},
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


class ConfigurePage(unittest.TestCase):
	def run_page(self, form, resolve_line):
		loader, form = configure_page(form, resolve_line)
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


if __name__ == "__main__":
	unittest.main()
