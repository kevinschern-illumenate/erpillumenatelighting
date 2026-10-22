"""Who the portal offers a template or product to: dealers see Active, staff also Internal Only."""

import types
import unittest

from test_services import ROOT, Record, load_service


def call(name, *args, **kwargs):
	with load_service(ROOT + ".portal_listing") as (module, _frappe):
		return getattr(module, name)(*args, **kwargs)


def status(value):
	return lambda doctype, name: value


def as_user(module, frappe, user, user_type="Website User", enabled=1):
	"""Make ``user`` the session user, with ``user_type`` on their User record."""
	frappe.session = Record(user=user)
	frappe.db.get_value.side_effect = lambda doctype, name, fields, as_dict=False: (
		{"user_type": user_type, "enabled": enabled} if doctype == "User" else None
	)


class OnPortal(unittest.TestCase):
	def test_an_active_template_is_shown_even_if_the_website_listing_is_not(self):
		product = {"fixture_template": "ILL-EL01-SW", "is_active": 0}
		self.assertTrue(call("on_portal", product, status("Active"), staff=False))

	def test_dealers_see_only_active_templates(self):
		product = {"fixture_template": "ILL-EL01-SW", "is_active": 1}
		for value in ("Internal Only", "Draft", "Discontinued", "Archived", None):
			self.assertFalse(call("on_portal", product, status(value), staff=False), value)

	def test_staff_also_see_internal_only_templates(self):
		product = {"fixture_template": "ILL-EL01-SW", "is_active": 1}
		self.assertTrue(call("on_portal", product, status("Internal Only"), staff=True))
		self.assertTrue(call("on_portal", product, status("Active"), staff=True))
		for value in ("Draft", "Discontinued", "Archived", None):
			self.assertFalse(call("on_portal", product, status(value), staff=True), value)

	def test_a_standalone_listing_follows_its_active_flag(self):
		self.assertTrue(call("on_portal", {"is_active": 1}, status("Archived"), staff=False))
		self.assertFalse(call("on_portal", {"is_active": 0}, status("Active"), staff=True))

	def test_the_status_is_read_from_the_linked_template(self):
		with load_service(ROOT + ".portal_listing") as (module, frappe):
			frappe.db.get_value.return_value = "Active"
			self.assertTrue(module.on_portal({"kit_template": "KIT-CA01"}, staff=False))
			frappe.db.get_value.assert_called_once_with(
				"ilL-Extrusion-Kit-Template", "KIT-CA01", "product_status"
			)

	def test_the_audience_defaults_to_the_session_user(self):
		product = {"fixture_template": "ILL-EL01-SW"}
		with load_service(ROOT + ".portal_listing") as (module, frappe):
			as_user(module, frappe, "dealer@example.com")
			self.assertFalse(module.on_portal(product, status("Internal Only")))
			as_user(module, frappe, "sales@illumenate.example", "System User")
			self.assertTrue(module.on_portal(product, status("Internal Only")))


class SeesInternal(unittest.TestCase):
	def check(self, user, user_type="Website User", enabled=1):
		with load_service(ROOT + ".portal_listing") as (module, frappe):
			as_user(module, frappe, user, user_type, enabled)
			return module.sees_internal()

	def test_staff_are_administrator_and_enabled_system_users(self):
		self.assertTrue(self.check("Administrator", "System User"))
		self.assertTrue(self.check("sales@illumenate.example", "System User"))

	def test_dealers_guests_and_disabled_staff_are_not(self):
		self.assertFalse(self.check("dealer@example.com", "Website User"))
		self.assertFalse(self.check("Guest", "Website User"))
		self.assertFalse(self.check("former@illumenate.example", "System User", enabled=0))

	def test_the_answer_is_cached_for_the_web_request(self):
		with load_service(ROOT + ".portal_listing") as (module, frappe):
			as_user(module, frappe, "sales@illumenate.example", "System User")
			frappe.local.request = object()
			self.assertTrue(module.sees_internal())
			self.assertTrue(module.sees_internal())
			self.assertEqual(frappe.db.get_value.call_count, 1)


class TemplateFilters(unittest.TestCase):
	def test_dealers_are_offered_active_templates_only(self):
		self.assertEqual(
			call("template_filters", False, product_category="LED Neon"),
			{"product_category": "LED Neon", "product_status": ["in", ["Active"]]},
		)

	def test_staff_are_offered_internal_only_templates_too(self):
		self.assertEqual(
			call("template_filters", True),
			{"product_status": ["in", ["Active", "Internal Only"]]},
		)


class TemplateScoped(unittest.TestCase):
	def endpoint(self, frappe, module, entry, template_status, **decorator):
		frappe.form_dict = {"cmd": entry}
		frappe.db.exists.return_value = True
		frappe.db.get_value.side_effect = lambda doctype, name, fields, as_dict=False: (
			{"user_type": "Website User", "enabled": 1} if doctype == "User" else template_status
		)
		frappe.DoesNotExistError = LookupError

		def quote(fixture_template_code, length_mm=0):
			return {"success": True, "template": fixture_template_code}

		quote.__module__ = "illumenate.api"
		return module.template_scoped("ilL-Fixture-Template", "fixture_template_code", **decorator)(quote)

	def configurator_access(self):
		access = types.ModuleType(ROOT + ".portal.configurator_access")

		def entry():
			import frappe

			return (frappe.form_dict or {}).get("cmd")

		access._entry_method = entry
		return {ROOT + ".portal.configurator_access": access}

	def test_a_dealer_calling_the_endpoint_for_an_internal_template_is_refused(self):
		with load_service(ROOT + ".portal_listing", self.configurator_access()) as (module, frappe):
			quote = self.endpoint(frappe, module, "illumenate.api.quote", "Internal Only")
			with self.assertRaises(LookupError):
				quote("ILL-SPECIAL", length_mm=1000)
			with self.assertRaises(LookupError):
				quote(fixture_template_code="ILL-SPECIAL")

	def test_an_active_template_and_server_side_calls_go_through(self):
		with load_service(ROOT + ".portal_listing", self.configurator_access()) as (module, frappe):
			quote = self.endpoint(frappe, module, "illumenate.api.quote", "Active")
			self.assertTrue(quote("ILL-EL01")["success"])
			# Another method was requested: this is a server-side re-quote of an existing line.
			quote = self.endpoint(frappe, module, "illumenate.api.save_line", "Internal Only")
			self.assertTrue(quote("ILL-SPECIAL")["success"])

	def test_a_resolver_finds_the_template_inside_browser_json(self):
		with load_service(ROOT + ".portal_listing", self.configurator_access()) as (module, frappe):
			resolve = lambda arguments: module.json_argument(arguments, "fixture_template_code", "kit")  # noqa: E731
			quote = self.endpoint(frappe, module, "illumenate.api.quote", "Internal Only", resolve=resolve)
			with self.assertRaises(LookupError):
				quote('{"kit": "KIT-SPECIAL"}')


class Permissions(unittest.TestCase):
	def test_list_conditions_hide_non_active_templates_from_non_staff(self):
		with load_service(ROOT + ".portal_listing") as (module, frappe):
			as_user(module, frappe, "dealer@example.com")
			self.assertEqual(
				module.fixture_template_conditions("dealer@example.com"),
				"`tabilL-Fixture-Template`.product_status = 'Active'",
			)
			as_user(module, frappe, "sales@illumenate.example", "System User")
			self.assertEqual(module.driver_template_conditions("sales@illumenate.example"), "")

	def test_documents_of_internal_templates_are_closed_to_non_staff(self):
		with load_service(ROOT + ".portal_listing") as (module, frappe):
			as_user(module, frappe, "dealer@example.com")
			self.assertFalse(module.template_has_permission({"product_status": "Internal Only"}, "read", "dealer@example.com"))
			self.assertTrue(module.template_has_permission({"product_status": "Active"}, "read", "dealer@example.com"))
			as_user(module, frappe, "sales@illumenate.example", "System User")
			self.assertTrue(module.template_has_permission({"product_status": "Internal Only"}, "read", "sales@illumenate.example"))


class PortalCondition(unittest.TestCase):
	def test_checks_every_template_link_and_the_standalone_case(self):
		sql = call("portal_condition", "wp", staff=False)
		for field in ("fixture_template", "kit_template", "led_sheet_template"):
			self.assertIn(f"wp.{field}", sql)
		self.assertIn("product_status in ('Active')", sql)
		self.assertIn("wp.is_active = 1", sql)

	def test_staff_condition_includes_internal_only(self):
		self.assertIn("product_status in ('Active', 'Internal Only')", call("portal_condition", "wp", staff=True))


if __name__ == "__main__":
	unittest.main()
