"""UI-1: one portal layout, one navigation, and stable edit-fixture URLs."""

import re
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

REPO = Path(__file__).resolve().parents[2]
PAGES = REPO / "illumenate_lighting/templates/pages"
NAV_INCLUDE = '{% include "templates/includes/portal_navigation.html" %}'
SIGNED_IN_PAGES = (
	"portal",
	"ill_projects",
	"project",
	"collaborators",
	"resources",
	"configure",
	"configure_tape",
	"edit_fixture",
	"schedule",
	"account",
	"drawings",
	"drawing_detail",
	"ill_support",
	"support_detail",
	"products_catalog",
	"product_detail",
	"orders",
	"order_detail",
	"quotes",
	"quote_detail",
	"quote_request_detail",
	"product_verification",
	"product_finder",
	"system_design",
	"accept_invitation",
)


class OneLayout(unittest.TestCase):
	def test_signed_in_pages_extend_the_portal_layout(self):
		for name in SIGNED_IN_PAGES:
			source = (PAGES / f"{name}.html").read_text()
			with self.subTest(page=name):
				self.assertIn('{% extends "templates/portal_base.html" %}', source)
				self.assertNotIn("{% block page_content %}", source)
				self.assertNotIn(NAV_INCLUDE, source, "the layout already includes the navigation")
				self.assertIn("{% block portal_content %}", source)

	def test_page_titles_are_translated_or_data(self):
		for name in SIGNED_IN_PAGES:
			source = (PAGES / f"{name}.html").read_text()
			title = re.search(r"\{% block portal_title %\}(.*?)\{% endblock %\}", source)
			with self.subTest(page=name):
				self.assertIsNotNone(title)
				# Nothing but template expressions and tags: raw words would skip translation.
				bare = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", title.group(1)).strip()
				self.assertEqual(bare, "")

	def test_layout_owns_navigation_and_title_format(self):
		base = (REPO / "illumenate_lighting/templates/portal_base.html").read_text()
		self.assertIn(NAV_INCLUDE, base)
		self.assertIn('{{ _("ilLumenate Portal") }}', base)
		self.assertIn('<main id="portal-main"', base)

	def test_every_section_can_be_current(self):
		nav = (REPO / "illumenate_lighting/templates/includes/portal_navigation.html").read_text()
		for href in (
			"/portal/drawings",
			"/portal/resources",
			"/portal/products",
			"/portal/product-finder",
			"/portal/support",
			"/portal/account",
		):
			self.assertIn(f"('{href}'", nav)
		self.assertIn('aria-current="page"', nav)


class Redirected(Exception):
	pass


def line(**values):
	base = {
		"name": "row-1",
		"line_key": "L-1",
		"manufacturer_type": "ILLUMENATE",
		"configured_fixture": "CF-1",
	}
	return Record({**base, **values})


class EditFixtureRoute(unittest.TestCase):
	def routes(self):
		with load_service(ROOT + ".portal.line_routes") as (module, _frappe):
			return types.SimpleNamespace(
				find_line=module.find_line,
				edit_url=module.edit_url,
				line_key=module.line_key,
				redirect=MagicMock(side_effect=Redirected),
			)

	def page(self, form, lines):
		routes = self.routes()
		schedule_module = types.SimpleNamespace(has_permission=MagicMock(return_value=True))
		api = types.SimpleNamespace(
			get_configured_fixture_for_editing=MagicMock(
				return_value={"success": True, "configuration": {"a": 1}}
			)
		)
		extras = {
			ROOT + ".portal.line_routes": routes,
			ROOT + ".portal.web_guard": types.SimpleNamespace(require_login=MagicMock()),
			ROOT + ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule": schedule_module,
			ROOT + ".api.portal": api,
		}
		context = load_service("illumenate_lighting.templates.pages.edit_fixture", extras)
		return context, routes, form, Record(name="SCH 1", status="DRAFT", lines=lines)

	def run_page(self, form, lines):
		context, routes, form, schedule = self.page(form, lines)
		with context as (module, frappe):
			frappe.form_dict = Record(form)
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = schedule
			frappe.get_all.return_value = []
			result = Record()
			try:
				module.get_context(result)
			except Redirected:
				return routes, None
			return routes, result

	def test_line_key_route_resolves_the_line(self):
		lines = [line(name="row-0", line_key="L-0", configured_fixture="CF-0"), line()]
		routes, context = self.run_page({"schedule": "SCH 1", "line_key": "L-1"}, lines)
		routes.redirect.assert_not_called()
		self.assertEqual(context.line_idx, 1)
		self.assertEqual(context.configured_fixture_id, "CF-1")

	def test_old_query_links_redirect_to_the_line_url(self):
		routes, _context = self.run_page({"schedule": "SCH 1", "line_idx": "0", "fixture": "CF-1"}, [line()])
		routes.redirect.assert_called_once_with("/portal/schedules/SCH%201/lines/L-1/edit")

	def test_unknown_line_key_is_not_found(self):
		with self.assertRaises(LookupError):
			self.run_page({"schedule": "SCH 1", "line_key": "missing"}, [line()])

	def test_rows_without_a_key_use_their_name(self):
		routes = self.routes()
		row = line(line_key=None)
		self.assertEqual(routes.edit_url("S", row), "/portal/schedules/S/lines/row-1/edit")
		self.assertEqual(routes.find_line(Record(lines=[row]), "row-1")[0], 0)


if __name__ == "__main__":
	unittest.main()
