"""The portal shows a product when its template's Product Status is Active."""

import unittest

from test_services import ROOT, load_service


def call(name, *args, **kwargs):
	with load_service(ROOT + ".portal_listing") as (module, _frappe):
		return getattr(module, name)(*args, **kwargs)


def status(value):
	return lambda doctype, name: value


class OnPortal(unittest.TestCase):
	def test_an_active_template_is_shown_even_if_the_website_listing_is_not(self):
		product = {"fixture_template": "ILL-EL01-SW", "is_active": 0}
		self.assertTrue(call("on_portal", product, status("Active")))

	def test_other_template_statuses_are_hidden(self):
		product = {"fixture_template": "ILL-EL01-SW", "is_active": 1}
		for value in ("ERPNext Only", "Draft", "Discontinued", "Archived", None):
			self.assertFalse(call("on_portal", product, status(value)), value)

	def test_a_standalone_listing_follows_its_active_flag(self):
		self.assertTrue(call("on_portal", {"is_active": 1}, status("Archived")))
		self.assertFalse(call("on_portal", {"is_active": 0}, status("Active")))

	def test_the_status_is_read_from_the_linked_template(self):
		with load_service(ROOT + ".portal_listing") as (module, frappe):
			frappe.db.get_value.return_value = "Active"
			self.assertTrue(module.on_portal({"kit_template": "KIT-CA01"}))
			frappe.db.get_value.assert_called_once_with(
				"ilL-Extrusion-Kit-Template", "KIT-CA01", "product_status"
			)


class PortalCondition(unittest.TestCase):
	def test_checks_every_template_link_and_the_standalone_case(self):
		sql = call("portal_condition", "wp")
		for field in ("fixture_template", "kit_template", "led_sheet_template"):
			self.assertIn(f"wp.{field}", sql)
		self.assertIn("product_status = 'Active'", sql)
		self.assertIn("wp.is_active = 1", sql)


if __name__ == "__main__":
	unittest.main()
