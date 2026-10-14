"""Handled errors roll back (REL-1) and mutating endpoints are POST-only (REL-2)."""

import ast
import re
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

REPO = Path(__file__).resolve().parents[2]

# Whitelisted functions named like a mutation must refuse GET: Frappe rolls GET
# requests back, so a GET call "succeeds" and persists nothing (or, where the
# endpoint commits itself, mutates without CSRF protection).
MUTATING = re.compile(
	r"^(add|delete|duplicate|move|update|save|create|archive|unarchive|rename|toggle|remove|request|set|"
	r"submit|cancel|approve|reject|publish|generate|apply|reset|mark|accept|revoke|resend|clone|convert|"
	r"send|trigger|retry|reopen|respond|withdraw|acknowledge|change|confirm)_"
)
# Read-only despite the name.
READ_ONLY = {"guardrail_audits.py::run_coverage_audit"}


def _whitelisted_mutations():
	for path in (REPO / "illumenate_lighting").rglob("*.py"):
		if path.name.startswith("test_") or "/patches/" in str(path):
			continue
		for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
			if not isinstance(node, ast.FunctionDef) or not MUTATING.match(node.name):
				continue
			for decorator in node.decorator_list:
				if ast.unparse(decorator).startswith("frappe.whitelist"):
					yield f"{path.name}::{node.name}", decorator


class PostOnly(unittest.TestCase):
	def test_every_whitelisted_mutation_is_post_only(self):
		found = 0
		for name, decorator in _whitelisted_mutations():
			if name in READ_ONLY:
				continue
			found += 1
			with self.subTest(endpoint=name):
				methods = next(
					(
						ast.literal_eval(k.value)
						for k in getattr(decorator, "keywords", [])
						if k.arg == "methods"
					),
					None,
				)
				self.assertEqual(
					methods, ["POST"], f"{name} accepts {methods or 'GET, POST, PUT and DELETE'}"
				)
		self.assertGreater(found, 50)


class HandledErrorsRollBack(unittest.TestCase):
	def run_update(self, method):
		deps = {
			ROOT + ".portal.access": types.SimpleNamespace(
				can_manage_project_collaborators=lambda *a: True, get_actor=MagicMock()
			)
		}
		with load_service(ROOT + ".api.portal", deps) as (api, frappe):
			order = []
			frappe.local.request = types.SimpleNamespace(method=method)
			frappe.db.rollback.side_effect = lambda: order.append("rollback")
			frappe.log_error = MagicMock(side_effect=lambda **kw: order.append("log"))
			frappe.get_traceback = lambda: "Traceback"
			frappe.db.exists.return_value = True
			existing = Record(user="designer@x.test", access_level="VIEW", is_active=1)
			project = Record(collaborators=[existing], save=MagicMock())
			project.append = lambda field, row: project.collaborators.append(Record(row))
			project.add_comment = MagicMock(side_effect=RuntimeError("comment table locked"))
			frappe.get_doc.return_value = project
			result = api.update_project_collaborators(
				"P-1", [{"user": "designer@x.test", "access_level": "EDIT", "is_active": 1}]
			)
			return result, order, frappe, project

	def test_post_rolls_back_the_partial_save_before_logging(self):
		result, order, frappe, project = self.run_update("POST")
		project.save.assert_called_once()
		self.assertEqual(result["error_code"], "internal_error")
		self.assertEqual(order, ["rollback", "log"])
		self.assertIs(frappe.log_error.call_args.kwargs["defer_insert"], True)

	def test_get_page_renders_do_not_roll_back(self):
		_, order, _, _ = self.run_update("GET")
		self.assertEqual(order, ["log"])


if __name__ == "__main__":
	unittest.main()
