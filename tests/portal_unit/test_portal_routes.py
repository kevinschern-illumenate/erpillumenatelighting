"""Hardening plan 7.1/7.2: one portal route contract, shared by Python, Desk and portal scripts."""

import re
import types
import unittest
from pathlib import Path

from test_route_inventory import _hooks, _resolves
from test_services import ROOT, load_service

from illumenate_lighting.illumenate_lighting.portal import routes

APP = Path(__file__).resolve().parents[2] / "illumenate_lighting"


class RouteContract(unittest.TestCase):
	def test_every_route_resolves_to_a_portal_page(self):
		rules, redirects = _hooks()
		for key in routes.PORTAL_ROUTES:
			with self.subTest(key=key):
				self.assertTrue(_resolves(routes.portal_path(key, "R-1"), rules, redirects))

	def test_names_are_one_encoded_path_segment(self):
		self.assertEqual(routes.portal_path("drawing", "DR/1 a"), "/portal/drawings/DR%2F1%20a")
		self.assertEqual(routes.portal_path("collaborators", "P-1"), "/portal/projects/P-1/collaborators")
		self.assertEqual(routes.portal_path("account"), "/portal/account")
		with self.assertRaises(ValueError):
			routes.portal_path("order", "")

	def test_desk_path_uses_the_frappe_slug(self):
		self.assertEqual(routes.desk_path("Sales Order", "SO 1"), "/app/sales-order/SO%201")
		self.assertEqual(routes.desk_path("ilL-Project-Fixture-Schedule", "S-1"), "/app/ill-project-fixture-schedule/S-1")

	def test_record_pages_map_back_to_their_desk_record(self):
		for key, doctype in routes.ROUTE_DOCTYPES.items():
			with self.subTest(key=key):
				self.assertEqual(routes.record_for_path(routes.portal_path(key, "A B")), (doctype, "A B"))
		self.assertEqual(routes.record_for_path("/portal/schedules/S-1/lines/k/edit"), ("ilL-Project-Fixture-Schedule", "S-1"))
		self.assertEqual(routes.record_for_path("portal/orders/SO-1?tab=x"), ("Sales Order", "SO-1"))
		for path in ("/portal/account", "/portal/projects", "/portal", "", None, "/app/ill-project/P-1", "/portal/configure/T-1"):
			with self.subTest(path=path):
				self.assertIsNone(routes.record_for_path(path))

	def test_boot_carries_the_contract(self):
		boot = types.SimpleNamespace()
		routes.extend_bootinfo(boot)
		self.assertEqual(boot.ill_portal_routes, routes.PORTAL_ROUTES)
		self.assertIsNot(boot.ill_portal_routes, routes.PORTAL_ROUTES)
		self.assertEqual(boot.ill_portal_route_doctypes, routes.ROUTE_DOCTYPES)

	def test_the_browser_fallback_matches_the_server(self):
		source = (APP / "public/js/portal_routes.js").read_text(encoding="utf-8")
		block = re.search(r"const DEFAULTS = \{(.*?)\};", source, re.S).group(1)
		defaults = dict(re.findall(r"(\w+): '([^']+)'", block))
		self.assertEqual(defaults, routes.PORTAL_ROUTES)

	def test_hooks_register_boot_and_jinja(self):
		hooks = (APP / "hooks.py").read_text(encoding="utf-8")
		self.assertIn('extend_bootinfo = ["illumenate_lighting.illumenate_lighting.portal.routes.extend_bootinfo"]', hooks)
		for method in ("ill_portal_routes", "ill_desk_link"):
			self.assertIn("portal.jinja_methods." + method, hooks)
		for doctype in ("ilL-Order-Change", "ilL-Drawing-Review", "ilL-Portal-Message", "ilL-Account-Request", "ilL-Portal-Invitation"):
			self.assertIn(f'"{doctype}"', hooks.split("public/js/desk_portal_links.js")[0].rsplit("for _name in", 1)[1])

	def test_former_literals_use_the_contract(self):
		request = (APP / "illumenate_lighting/doctype/ill_document_request/ill_document_request.py").read_text(encoding="utf-8")
		self.assertNotIn('"/portal/drawings/', request)
		self.assertEqual(request.count('portal_path("drawing", self.name)'), 2)
		configurator = (APP / "public/js/configurator/shared_configurator.js").read_text(encoding="utf-8")
		self.assertNotIn("'/portal/schedules/'", configurator)
		links = (APP / "public/js/desk_portal_links.js").read_text(encoding="utf-8")
		self.assertNotIn("/portal/", links)
		base = (APP / "templates/portal_base.html").read_text(encoding="utf-8")
		self.assertIn('id="ill-portal-routes">{{ ill_portal_routes() | tojson }}', base)


class DeskLink(unittest.TestCase):
	def link(self, path, user="staff@example.com", user_type="System User", enabled=True):
		extras = {ROOT + ".portal.site_flags": types.SimpleNamespace(desk_links_enabled=lambda: enabled)}
		with load_service(ROOT + ".portal.jinja_methods", extras) as (service, frappe):
			frappe.session.user = user
			frappe.get_cached_value = lambda doctype, name, field: user_type
			return service.ill_desk_link(path)

	def test_staff_get_the_desk_form_for_a_record_page(self):
		self.assertEqual(self.link("/portal/orders/SO-1"), "/app/sales-order/SO-1")
		self.assertEqual(self.link("portal/schedules/S%201/design"), "/app/ill-project-fixture-schedule/S%201")

	def test_dealers_guests_and_list_pages_get_nothing(self):
		self.assertEqual(self.link("/portal/orders/SO-1", user_type="Website User"), "")
		self.assertEqual(self.link("/portal/orders/SO-1", user="Guest"), "")
		self.assertEqual(self.link("/portal/orders"), "")
		self.assertEqual(self.link(None), "")

	def test_kill_switch_hides_the_link(self):
		self.assertEqual(self.link("/portal/orders/SO-1", enabled=False), "")

	def test_routes_for_portal_scripts(self):
		with load_service(ROOT + ".portal.jinja_methods") as (service, _frappe):
			self.assertEqual(service.ill_portal_routes(), routes.PORTAL_ROUTES)


if __name__ == "__main__":
	unittest.main()
