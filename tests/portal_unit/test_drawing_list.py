"""REL-8: the drawings page lists through the same scope as the request counts."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


class DrawingList(unittest.TestCase):
	def service(self):
		self.conditions = MagicMock(return_value=(["hide_from_portal = 0", "scope = 1"], {}))
		requests_api = types.SimpleNamespace(
			REQUEST_TABLE="`tabilL-Document-Request`", _scoped_request_conditions=self.conditions
		)
		context = load_service(ROOT + ".portal.drawing_list", {ROOT + ".api.document_requests": requests_api})
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		return module, frappe

	def test_lists_use_the_shared_scope_and_page(self):
		module, frappe = self.service()
		frappe.db.sql.return_value = [Record(name=f"DR-{i}") for i in range(3)]
		rows, has_more = module.requests("all", page=2, page_size=2, user="dana@acme.test")
		self.conditions.assert_called_once_with(tab="all", user="dana@acme.test")
		sql, params = frappe.db.sql.call_args.args
		self.assertIn("WHERE hide_from_portal = 0 AND scope = 1", sql)
		self.assertIn("ORDER BY creation DESC", sql)
		self.assertEqual((params["start"], params["length"]), (2, 3))
		self.assertEqual(([row.name for row in rows], has_more), (["DR-0", "DR-1"], True))

	def test_completed_requests_sort_by_last_change(self):
		module, frappe = self.service()
		frappe.db.sql.return_value = []
		self.assertEqual(module.requests("completed"), ([], False))
		self.assertIn("ORDER BY modified DESC", frappe.db.sql.call_args.args[0])

	def test_page_numbers_are_positive_integers(self):
		module, _frappe = self.service()
		self.assertEqual([module.page_number(v) for v in (None, "3", "-1", "x")], [1, 3, 1, 1])


class DrawingsPrefill(unittest.TestCase):
	"""Plan 3.3: bulk "Request drawings" opens the form pre-filled, never with an unreadable project."""

	def page(self, form, readable=()):
		guard = types.ModuleType(ROOT + ".portal.web_guard")
		guard.require_login = lambda *args, **kwargs: None
		lister = types.ModuleType(ROOT + ".portal.drawing_list")
		lister.requests = lambda *args, **kwargs: ([], False)
		lister.page_number = lambda value: 1
		context = load_service(
			"illumenate_lighting.templates.pages.drawings",
			{ROOT + ".portal.web_guard": guard, ROOT + ".portal.drawing_list": lister},
		)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.form_dict = Record(form)
		frappe.get_list = MagicMock(
			side_effect=lambda doctype, filters=None, **kwargs: [
				Record(name=name, project_name=name.title()) for name in readable if name == (filters or {}).get("name")
			]
		)
		return module

	def test_reference_is_trimmed_and_capped(self):
		module = self.page({"fixture_reference": "  " + "A" * 600})
		self.assertEqual(module._prefill([]), {"project": "", "fixture_reference": "A" * 500})

	def test_listed_project_is_selected_without_a_lookup(self):
		module = self.page({"project": "P-1"})
		projects = [Record(name="P-1")]
		self.assertEqual(module._prefill(projects)["project"], "P-1")
		self.assertEqual(len(projects), 1)

	def test_older_readable_project_is_added(self):
		module = self.page({"project": "P-9"}, readable=("P-9",))
		projects = [Record(name="P-1")]
		self.assertEqual(module._prefill(projects)["project"], "P-9")
		self.assertEqual([row.name for row in projects], ["P-9", "P-1"])

	def test_unreadable_project_is_dropped(self):
		module = self.page({"project": "P-X"})
		projects = []
		self.assertEqual(module._prefill(projects), {"project": "", "fixture_reference": ""})
		self.assertEqual(projects, [])
