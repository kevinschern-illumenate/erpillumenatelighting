"""Bulk template tools take ``doctypes`` and default to ``webflow_sync_scope`` (plan 2026-11-23 Task 2)."""

import importlib
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

FIXTURE = "ilL-Fixture-Template"
TAPE = "ilL-Tape-Neon-Template"


class Base(unittest.TestCase):
	module_name = None

	def setUp(self):
		context = load_service(f"{ROOT}.{self.module_name}")
		self.module, self.frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		# n8n_config may already be imported against an earlier test's frappe stub.
		n8n_config = importlib.import_module(ROOT + ".api.n8n_config")
		patcher = patch.object(n8n_config, "frappe", self.frappe)
		patcher.start()
		self.addCleanup(patcher.stop)
		# n8n_config may keep this frappe stub after the test: never leave a scope behind.
		self.addCleanup(self.frappe.conf.pop, "webflow_sync_scope", None)
		self.frappe.only_for = MagicMock()
		self.frappe.parse_json = lambda value: __import__("json").loads(value)
		self.frappe.db.commit = MagicMock()
		self.frappe.db.set_value = MagicMock()
		self.frappe.db.has_column = MagicMock(return_value=True)
		self.queried = []

	def get_all(self, rows):
		def get_all(doctype, **kwargs):
			self.queried.append(doctype)
			return rows.get(doctype, [])

		self.frappe.get_all = MagicMock(side_effect=get_all)


class Arg(unittest.TestCase):
	def setUp(self):
		context = load_service(ROOT + ".web_listing_schema")
		self.module, self.frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		n8n_config = importlib.import_module(ROOT + ".api.n8n_config")
		patcher = patch.object(n8n_config, "frappe", self.frappe)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(self.frappe.conf.pop, "webflow_sync_scope", None)

	def test_explicit_list_string_and_json(self):
		arg = self.module.template_doctypes_arg
		self.assertEqual(arg([FIXTURE]), [FIXTURE])
		self.assertEqual(arg(FIXTURE), [FIXTURE])
		self.assertEqual(arg(f'["{TAPE}", "{FIXTURE}"]'), [FIXTURE, TAPE])  # TEMPLATE_DOCTYPES order

	def test_default_is_scope_then_all(self):
		arg = self.module.template_doctypes_arg
		self.assertEqual(arg(None), list(self.module.TEMPLATE_DOCTYPES))
		self.frappe.conf["webflow_sync_scope"] = {"doctypes": [FIXTURE]}
		self.assertEqual(arg(None), [FIXTURE])
		self.assertEqual(arg([TAPE]), [TAPE])  # an explicit list wins over the scope

	def test_unknown_doctype_raises(self):
		# frappe.throw, so the System Console shows a message rather than a traceback (final review).
		self.frappe.throw = MagicMock(side_effect=ValueError)
		for bad in (["ilL-Nothing"], "[not json"):
			with self.subTest(bad=bad), self.assertRaises(ValueError):
				self.module.template_doctypes_arg(bad)
		self.assertEqual(self.frappe.throw.call_count, 2)


class Refresh(Base):
	module_name = "template_listing"

	def test_refresh_all_templates_limits_doctypes(self):
		self.get_all({FIXTURE: ["FX-1"], TAPE: ["TAPE-1"]})
		result = self.module.refresh_all_templates(doctypes=[FIXTURE])
		self.assertEqual(self.queried, [FIXTURE])
		self.assertEqual(result["doctypes"], [FIXTURE])
		self.assertEqual(result["templates"], 1)

	def test_refresh_all_templates_defaults_to_scope(self):
		self.frappe.conf["webflow_sync_scope"] = '{"doctypes": ["ilL-Fixture-Template"]}'
		self.get_all({FIXTURE: ["FX-1"], TAPE: ["TAPE-1"]})
		self.assertEqual(self.module.refresh_all_templates()["doctypes"], [FIXTURE])
		self.assertEqual(self.queried, [FIXTURE])


class Report(Base):
	module_name = "template_link_report"

	def test_promote_live_templates_defaults_to_scope(self):
		self.frappe.conf["webflow_sync_scope"] = {"doctypes": [FIXTURE]}
		self.get_all(
			{
				"ilL-Webflow-Product": [
					Record(name="fx-1", webflow_status="Published"),
					Record(name="tape-1", webflow_status="Published"),
				],
				FIXTURE: [Record(name="FX-1", webflow_product="fx-1", product_status="Active")],
				TAPE: [Record(name="TAPE-1", webflow_product="tape-1", product_status="Active")],
			}
		)
		plan = self.module.promote_live_templates()
		self.assertEqual([row["template"] for row in plan["promote"]], [(FIXTURE, "FX-1")])
		self.assertEqual(plan["doctypes"], [FIXTURE])
		self.assertNotIn(TAPE, self.queried)

	def test_link_report_limits_doctypes(self):
		self.module._brands = MagicMock(return_value={})
		self.module.build_report = MagicMock(
			return_value={"set_template_link": [], "set_product_link": [], "clear_product_link": []}
		)
		self.get_all({FIXTURE: [], TAPE: []})
		brand = importlib.import_module(ROOT + ".api.webflow_brand")
		with patch.object(brand, "get_default_brand", return_value="illumenate"):
			report = self.module.link_consistency_report(doctypes=[FIXTURE])
		templates = self.module.build_report.call_args.args[1]
		self.assertEqual(list(templates), [FIXTURE])
		self.assertEqual(report["doctypes"], [FIXTURE])
		self.assertNotIn(TAPE, self.queried)


if __name__ == "__main__":
	unittest.main()
