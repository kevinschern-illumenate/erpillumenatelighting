"""Guests opening a portal link sign in and land back on that link (REL-6)."""

import ast
import types
import unittest
from pathlib import Path

from test_services import ROOT, Record, load_service

REPO = Path(__file__).resolve().parents[2]
PAGES = REPO / "illumenate_lighting" / "templates" / "pages"

# Every page a notification email or portal navigation links to while signed in.
AUTHENTICATED_PAGES = (
	"account collaborators configure configure_sheet drawing_detail drawings edit_fixture ill_projects "
	"ill_support order_detail orders portal product_detail product_verification products_catalog project "
	"quote_detail quote_request_detail schedule support_detail catalog_builder"
).split()


class RequireLogin(unittest.TestCase):
	def guard(self, user, path="/portal/orders/SO-0001", query=b""):
		with load_service(ROOT + ".portal.web_guard") as (module, frappe):
			frappe.Redirect = type("Redirect", (Exception,), {})
			frappe.session = Record(user=user)
			frappe.local.flags = Record()
			frappe.local.request = types.SimpleNamespace(path=path, query_string=query)
			try:
				module.require_login()
			except frappe.Redirect:
				return frappe.local.flags.redirect_location
			return None

	def test_guest_returns_to_the_exact_item(self):
		self.assertEqual(self.guard("Guest"), "/login?redirect-to=/portal/orders/SO-0001")

	def test_query_string_survives_the_login_hop(self):
		location = self.guard("Guest", "/portal/configure", b"category=LED Tape&schedule=S-1")
		self.assertEqual(
			location, "/login?redirect-to=/portal/configure%3Fcategory%3DLED%20Tape%26schedule%3DS-1"
		)

	def test_signed_in_users_pass_through(self):
		self.assertIsNone(self.guard("dealer@a.test"))

	def test_authenticated_pages_use_the_shared_guard_first(self):
		for name in AUTHENTICATED_PAGES:
			with self.subTest(page=name):
				tree = ast.parse((PAGES / f"{name}.py").read_text(encoding="utf-8"))
				get_context = next(
					n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get_context"
				)
				calls = [
					n.func.id
					for statement in get_context.body
					for n in ast.walk(statement)
					if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
				]
				self.assertIn("require_login", calls)
				source = ast.get_source_segment(
					(PAGES / f"{name}.py").read_text(encoding="utf-8"), get_context
				)
				self.assertNotIn('== "Guest"', source, "bespoke guest handling loses the deep link")


if __name__ == "__main__":
	unittest.main()
