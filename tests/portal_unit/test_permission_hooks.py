"""has_permission hook contracts for Frappe v16.

Frappe v16 denies access when any has_permission hook returns a falsy value,
including None. Frappe v15 treated None as "no opinion". A hook that returns
None therefore silently denies every non-Administrator user on v16.
"""

import ast
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

REPO = Path(__file__).resolve().parents[2]
HOOKS = REPO / "illumenate_lighting" / "hooks.py"


def _hook_paths():
	tree = ast.parse(HOOKS.read_text(encoding="utf-8"))
	for node in tree.body:
		if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "has_permission":
			return {
				key.value: value.value for key, value in zip(node.value.keys, node.value.values, strict=True)
			}
	raise AssertionError("hooks.py declares no has_permission mapping")


def _function(path):
	module, name = path.rsplit(".", 1)
	source = REPO / (module.replace(".", "/") + ".py")
	for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
		if isinstance(node, ast.FunctionDef) and node.name == name:
			return node
	raise AssertionError(f"{path} is not defined in {source}")


def _falls_through(body):
	"""True when execution can reach the end of this block without returning or raising."""
	if not body:
		return True
	last = body[-1]
	if isinstance(last, ast.Return | ast.Raise):
		return False
	if isinstance(last, ast.If):
		return _falls_through(last.body) or _falls_through(last.orelse)
	if isinstance(last, ast.Try):
		main = last.body + last.orelse if last.orelse else last.body
		return _falls_through(main) or any(_falls_through(handler.body) for handler in last.handlers)
	if isinstance(last, ast.With):
		return _falls_through(last.body)
	return True


class HookContracts(unittest.TestCase):
	def test_every_has_permission_hook_returns_a_decision(self):
		hooks = _hook_paths()
		self.assertIn("File", hooks)
		for doctype, path in hooks.items():
			function = _function(path)
			with self.subTest(doctype=doctype, hook=path):
				for node in ast.walk(function):
					if isinstance(node, ast.Return):
						self.assertFalse(
							node.value is None
							or (isinstance(node.value, ast.Constant) and node.value.value is None),
							f"line {node.lineno} returns None, which Frappe v16 treats as a denial",
						)
				self.assertFalse(_falls_through(function.body), "the hook can end without returning")


class FilePermission(unittest.TestCase):
	def service(self, frappe_decision=True):
		file_module = types.ModuleType("frappe.core.doctype.file.file")
		file_module.File = type("File", (), {"is_downloadable": lambda self: "native"})
		file_module.has_permission = MagicMock(return_value=frappe_decision)
		extras = {
			"frappe.core": types.ModuleType("frappe.core"),
			"frappe.core.doctype": types.ModuleType("frappe.core.doctype"),
			"frappe.core.doctype.file": types.ModuleType("frappe.core.doctype.file"),
			file_module.__name__: file_module,
		}
		return load_service(ROOT + ".portal.private_file", extras), file_module.has_permission

	def test_uploads_and_edits_defer_to_frappe_instead_of_denying(self):
		for frappe_decision in (True, False):
			context, native = self.service(frappe_decision)
			with context as (service, _frappe):
				for ptype in ("create", "write", "delete"):
					with self.subTest(ptype=ptype, frappe_decision=frappe_decision):
						doc = Record(
							attached_to_doctype="ilL-Webflow-Product", attached_to_name="ill-fs01-sw"
						)
						result = service.portal_file_permission(doc, ptype, "manager@example.com")
						self.assertIs(result, frappe_decision)
						native.assert_called_with(doc, ptype=ptype, user="manager@example.com")

	def test_non_portal_reads_defer_to_frappe(self):
		context, native = self.service(True)
		with context as (service, _frappe):
			doc = Record(attached_to_doctype="Sales Order", attached_to_name="SO-1")
			self.assertIs(service.portal_file_permission(doc, "read", "sales@example.com"), True)
			native.assert_called_once()

	def test_portal_decision_is_kept_and_download_uses_it(self):
		intake = types.ModuleType(ROOT + ".portal.order_intake")
		intake.can_access = MagicMock(return_value=False)
		context, native = self.service(True)
		with context as (service, _frappe):
			import sys

			sys.modules[intake.__name__] = intake
			try:
				doc = Record(attached_to_doctype="ilL-Order-Intake", attached_to_name="INTAKE-1")
				self.assertIs(service.portal_file_permission(doc, "read", "buyer@example.com"), False)
				native.assert_not_called()
				portal_file = service.PortalFile()
				portal_file.attached_to_doctype = "Sales Order"
				self.assertEqual(portal_file.is_downloadable(), "native")
				portal_file.attached_to_doctype = "ilL-Order-Intake"
				portal_file.attached_to_name = "INTAKE-1"
				self.assertIs(portal_file.is_downloadable(), False)
			finally:
				del sys.modules[intake.__name__]


if __name__ == "__main__":
	unittest.main()
