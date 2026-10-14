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
