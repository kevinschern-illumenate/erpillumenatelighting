"""Plan 3.9: schedule lines the catalog has moved past are flagged for review, never changed."""

import copy
import json
import pathlib
import runpy
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".portal.catalog_drift"
REPO = pathlib.Path(__file__).resolve().parents[2]
REVISION = {
	"name": "SPEC-96",
	"voltage_output": "24V DC",
	"output_type": "Constant Voltage",
	"output_protocol": "0-10V",
	"max_wattage": 96,
	"max_wattage_per_output": 96,
	"usable_load_factor": 0.8,
	"independent_outputs_count": 1,
	"outputs_count": 1,
}


def linear_problems(request):
	selections = request["selections"]
	if selections.get("finish_code") == "GONE":
		selections.pop("finish_code")
		return ["Finish GONE is no longer offered; choose it again"]
	return []


class ExpiringCache:
	"""``frappe.cache()`` double that honours ``expires_in_sec`` against a test clock."""

	def __init__(self):
		self.now = 0
		self.store = {}

	def get_value(self, key):
		value, expires = self.store.get(key, (None, None))
		return value if expires is None or self.now < expires else None

	def set_value(self, key, value, expires_in_sec=None):
		expires = None if expires_in_sec is None else self.now + expires_in_sec
		self.store[key] = (copy.deepcopy(value), expires)


class CatalogDrift(unittest.TestCase):
	def setUp(self):
		self.enabled = True
		self.requests = {}
		self.active = {("ilL-Fixture-Template", "FT-1"): 1, ("ilL-Driver-Template", "DRV-1"): 1, ("ilL-Driver-Template", "DRV-OLD"): 0}
		self.visible = {("ilL-Fixture-Template", "FT-1"), ("ilL-Driver-Template", "DRV-1"), ("ilL-Driver-Template", "DRV-OLD")}
		self.plans = {"CF-1": json.dumps({"dependency_revisions": {"DRV-ITEM": REVISION}})}
		self.sheets = {}
		self.specs = {"SPEC-96": {k: v for k, v in REVISION.items() if k != "outputs_count"}}
		self.schedule_calls = []
		self.linear_calls = []

		def for_line(line):
			request = self.requests.get(line.get("line_key"))
			if isinstance(request, Exception):
				raise request
			return copy.deepcopy(request)

		def template_name(family, template):
			return template

		def tracked_linear(request):
			self.linear_calls.append(request)
			return linear_problems(request)

		def schedule_context(name, write=False, lock=False):
			self.schedule_calls.append((name, write))
			return self.schedule

		presets = types.SimpleNamespace(
			FAMILY_DOCTYPES={"Linear Fixture": "ilL-Fixture-Template", "Driver": "ilL-Driver-Template"},
			_template_name=template_name,
			_linear_problems=tracked_linear,
		)
		self.extras = {
			ROOT + ".portal.site_flags": types.SimpleNamespace(stale_badge_enabled=lambda: self.enabled),
			ROOT + ".portal.presets": presets,
			ROOT + ".portal.configuration_reopen": types.SimpleNamespace(for_line=for_line),
			ROOT + ".portal.configuration": types.SimpleNamespace(schedule_context=schedule_context),
			ROOT + ".portal.product_finder.facts": types.SimpleNamespace(catalog_stamp=lambda: self.stamp),
			ROOT + ".portal_listing": types.SimpleNamespace(
				template_visible=lambda doctype, name, staff=None: (doctype, name) in self.visible
			),
		}
		self.schedule = Record(name="SCH-1", lines=[])
		self.stamp = "2026-11-17 10:00:00:0"

	def wire(self, frappe):
		frappe.db.get_value = MagicMock(side_effect=lambda doctype, name, field: self.active.get((doctype, name)))

		def get_all(doctype, filters=None, fields=None, limit_page_length=None):
			names = filters["name"][1]
			if doctype == "ilL-Spec-Driver":
				self.spec_fields = fields
				return [Record(self.specs[name]) for name in names if name in self.specs]
			source = self.plans if doctype == "ilL-Configured-Fixture" else self.sheets
			field = fields[1]
			return [Record({"name": name, field: source[name]}) for name in names if name in source]

		frappe.get_all = MagicMock(side_effect=get_all)

	def check(self, lines):
		self.schedule["lines"] = lines
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			return module, frappe, module.check("SCH-1")

	def linear(self, key, finish="WH", link="CF-1"):
		self.requests[key] = {"family": "Linear Fixture", "template": "FT-1", "selections": {"finish_code": finish}}
		return Record(line_key=key, name="row-" + key, configured_fixture=link)

	def test_current_lines_are_not_flagged(self):
		module, _frappe, result = self.check([self.linear("A"), Record(line_key="OTHER", name="row-o")])
		self.assertEqual(result, {"enabled": True, "lines": {}})
		self.assertEqual(self.schedule_calls, [("SCH-1", False)], "read access is enough")
		self.assertEqual(module.check.whitelist_options, {"methods": ["GET"]})

	def test_retired_or_hidden_templates_and_withdrawn_options(self):
		self.requests["D"] = {"family": "Driver", "template": "DRV-OLD", "selections": {}}
		self.requests["E"] = {"family": "Driver", "template": "DRV-OLD", "selections": {}}
		self.requests["F"] = {"family": "Controller", "template": "CTL-1", "selections": {}}
		lines = [
			self.linear("A", finish="GONE"),
			Record(line_key="D", name="row-d"),
			Record(line_key="E", name="row-e"),
			Record(line_key="F", name="row-f"),
		]
		_module, frappe, result = self.check(lines)
		self.assertEqual(
			result["lines"],
			{
				"A": ["Finish GONE is no longer offered; choose it again"],
				"D": ["DRV-OLD is no longer offered"],
				"E": ["DRV-OLD is no longer offered"],
				"F": ["This product family is no longer offered"],
			},
		)
		self.assertEqual(frappe.db.get_value.call_count, 2, "each template is checked once")
		self.assertEqual(self.linear_calls[0]["selections"], {}, "the option check works on a copy")
		self.assertEqual(self.requests["A"]["selections"], {"finish_code": "GONE"})

	def test_hidden_template_is_no_longer_offered(self):
		self.visible.discard(("ilL-Fixture-Template", "FT-1"))
		_module, _frappe, result = self.check([self.linear("A")])
		self.assertEqual(result["lines"], {"A": ["FT-1 is no longer offered"]})
		self.assertEqual(self.linear_calls, [])

	def test_changed_or_removed_power_supply_specifications(self):
		self.specs["SPEC-96"]["max_wattage"] = 60
		_module, _frappe, result = self.check([self.linear("A")])
		self.assertEqual(result["lines"], {"A": ["Power supply DRV-ITEM specification changed"]})
		self.assertNotIn("outputs_count", self.spec_fields)
		self.specs.clear()
		_module, _frappe, result = self.check([self.linear("A")])
		self.assertEqual(result["lines"], {"A": ["Power supply DRV-ITEM is no longer in the catalog"]})

	def test_numeric_and_empty_values_compare_by_value(self):
		self.specs["SPEC-96"].update(max_wattage=96.0, usable_load_factor="0.8", output_protocol=None)
		self.plans["CF-1"] = json.dumps(
			{"dependency_revisions": {"DRV-ITEM": {**REVISION, "output_protocol": ""}}}
		)
		_module, _frappe, result = self.check([self.linear("A")])
		self.assertEqual(result["lines"], {})

	def test_led_sheet_plans_are_read_from_the_build_snapshot(self):
		self.sheets["CLS-1"] = json.dumps({"power_plan": {"dependency_revisions": {"DRV-ITEM": REVISION}}})
		self.specs["SPEC-96"]["voltage_output"] = "12V DC"
		line = Record(line_key="S", name="row-s", configured_led_sheet="CLS-1")
		_module, _frappe, result = self.check([line])
		self.assertEqual(result["lines"], {"S": ["Power supply DRV-ITEM specification changed"]})

	def test_unreadable_configuration_is_flagged_once(self):
		self.requests["A"] = LookupError("ilL-Configured-Fixture CF-9 not found")
		line = Record(line_key="A", name="row-a", configured_fixture="CF-9")
		_module, _frappe, result = self.check([line])
		self.assertEqual(result["lines"], {"A": ["The saved configuration can no longer be read"]})

	def test_stored_revisions_tolerate_bad_json(self):
		with load_service(MODULE, self.extras) as (module, _frappe):
			self.assertEqual(module.stored_revisions("not json"), {})
			self.assertEqual(module.stored_revisions("[1]"), {})
			self.assertEqual(module.stored_revisions({"dependency_revisions": {"A": 1, "B": {"name": "S"}}}), {"B": {"name": "S"}})
			self.assertEqual(module.stored_revisions({"driver_plan": {"dependency_revisions": {"B": {}}}}), {"B": {}})

	def test_kill_switch_and_guests(self):
		self.enabled = False
		_module, _frappe, result = self.check([self.linear("A", finish="GONE")])
		self.assertEqual(result, {"enabled": False, "lines": {}})
		self.assertEqual(self.schedule_calls, [])
		self.enabled = True
		with load_service(MODULE, self.extras) as (module, frappe):
			frappe.session.user = "Guest"
			with self.assertRaises(PermissionError):
				module.check("SCH-1")
		self.assertEqual(self.schedule_calls, [])

	def test_lines_are_never_written(self):
		line = self.linear("A", finish="GONE")
		before = dict(line)
		_module, frappe, _result = self.check([line])
		self.assertEqual(dict(line), before)
		frappe.db.set_value.assert_not_called()
		frappe.get_doc.assert_not_called()

	def test_answer_is_cached_for_the_same_lines_user_and_catalog(self):
		lines = [self.linear("A", finish="GONE")]
		_module, frappe, result = self.check(lines)
		set_value = frappe.cache().set_value
		self.assertEqual(set_value.call_count, 1)
		key, stored = set_value.call_args.args
		self.assertEqual(stored, result["lines"])
		self.assertEqual(set_value.call_args.kwargs, {"expires_in_sec": 600})
		self.assertIn(":SCH-1:buyer@example.com:2026-11-17 10:00:00:0:", key)

		# A cached answer is returned as it was, without reading a line again.
		self.linear_calls.clear()
		self.schedule["lines"] = lines
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			frappe.cache().get_value.side_effect = lambda k: stored if k == key else None
			self.assertEqual(module.check("SCH-1"), {"enabled": True, "lines": stored})
			frappe.cache().set_value.assert_not_called()
		self.assertEqual(self.linear_calls, [])

	def test_cache_key_moves_with_any_line_field_the_user_or_the_catalog(self):
		def key(lines, user="buyer@example.com"):
			self.schedule["lines"] = lines
			with load_service(MODULE, self.extras) as (module, frappe):
				self.wire(frappe)
				frappe.session.user = user
				module.check("SCH-1")
				return frappe.cache().set_value.call_args.args[0]

		base = key([self.linear("A")])
		self.assertEqual(key([self.linear("A")]), base, "same lines, same answer")
		self.assertNotEqual(key([self.linear("A", link="CF-2")]), base, "a line changed")
		self.assertNotEqual(key([self.linear("A"), self.linear("B")]), base, "a line was added")
		self.assertNotEqual(key([self.linear("A")], user="other@example.com"), base, "another user")
		self.stamp = "2026-11-17 10:05:00:0"
		self.assertNotEqual(key([self.linear("A")]), base, "the catalog moved")

	def test_a_changed_configured_record_shows_once_the_cached_answer_expires(self):
		"""Pins today's behaviour (plan 12): a configured record changing does not clear the answer.

		The key fingerprints the line rows, the user and the catalog stamp, not the configured
		record a line links to, so an edit that keeps the same record name is seen only after
		CACHE_SECONDS (10 minutes). Update this test if an invalidation hook is added.
		"""
		changed = "Power supply DRV-ITEM specification changed"
		edits = {
			"power plan": lambda: self.plans.update(
				{"CF-1": json.dumps({"dependency_revisions": {"DRV-ITEM": {**REVISION, "max_wattage": 60}}})}
			),
			"saved configuration": lambda: self.requests["A"].update(template="FT-GONE"),
		}
		expected = {"power plan": [changed], "saved configuration": ["FT-GONE is no longer offered"]}
		for name, edit in edits.items():
			with self.subTest(edit=name):
				self.setUp()
				cache = ExpiringCache()
				lines = [self.linear("A")]

				def check(at):
					cache.now = at
					self.schedule["lines"] = lines
					with load_service(MODULE, self.extras) as (module, frappe):
						self.wire(frappe)
						frappe.cache = lambda: cache
						return module, module.check("SCH-1")["lines"]

				module, first = check(0)
				self.assertEqual(first, {})
				self.assertEqual(module.CACHE_SECONDS, 600)
				edit()
				self.assertEqual(check(module.CACHE_SECONDS - 1)[1], {}, "stale until it expires")
				self.assertEqual(len(cache.store), 1, "the record change does not move the key")
				self.assertEqual(check(module.CACHE_SECONDS)[1], {"A": expected[name]})

	def test_no_hook_clears_the_answer_when_a_configured_record_changes(self):
		with load_service(MODULE, self.extras) as (module, _frappe):
			configured = {doctype for doctype, _field in module.PLAN_SOURCES.values()}
			prefix = module.CACHE_PREFIX
		hooks = runpy.run_path(str(REPO / "illumenate_lighting" / "hooks.py"))
		for doctype in sorted(configured):
			self.assertNotIn(doctype, hooks["doc_events"])
			self.assertNotIn(doctype, hooks["_finder_fact_doctypes"], "not part of the catalog stamp")
		self.assertNotIn("*", hooks["doc_events"])
		readers = [
			path.relative_to(REPO).as_posix()
			for path in (REPO / "illumenate_lighting").rglob("*.py")
			if prefix in path.read_text(encoding="utf-8")
		]
		self.assertEqual(readers, ["illumenate_lighting/illumenate_lighting/portal/catalog_drift.py"])

	def test_kill_switch_reads_and_writes_no_cache(self):
		self.enabled = False
		_module, frappe, _result = self.check([self.linear("A")])
		frappe.cache().set_value.assert_not_called()


if __name__ == "__main__":
	unittest.main()
