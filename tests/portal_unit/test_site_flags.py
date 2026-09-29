"""Site-config values arrive typed differently depending on how Frappe Cloud stores them."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, load_service


class SiteFlags(unittest.TestCase):
	def test_boolean_flag_accepts_every_stored_form(self):
		with load_service(ROOT + ".portal.site_flags") as (flags, frappe):
			frappe.log_error = MagicMock()
			self.assertFalse(flags.conf_flag("ill_portal_fixture_groups"))
			for value, expected in (
				(True, True),
				(1, True),
				("true", True),
				("1", True),
				(False, False),
				(0, False),
				("false", False),
				("0", False),
				("", False),
			):
				with self.subTest(value=value):
					frappe.conf["ill_portal_fixture_groups"] = value
					self.assertIs(flags.conf_flag("ill_portal_fixture_groups"), expected)
			frappe.log_error.assert_not_called()

	def test_unreadable_flag_uses_default_and_is_logged_once(self):
		with load_service(ROOT + ".portal.site_flags") as (flags, frappe):
			frappe.log_error = MagicMock()
			frappe.conf["ill_portal_fixture_groups"] = "enabled"
			self.assertFalse(flags.conf_flag("ill_portal_fixture_groups"))
			self.assertTrue(flags.conf_flag("ill_portal_fixture_groups", default=True))
			frappe.log_error.assert_called_once()

	def test_list_accepts_json_and_json_strings(self):
		with load_service(ROOT + ".portal.site_flags") as (flags, frappe):
			frappe.log_error = MagicMock()
			self.assertIsNone(flags.conf_list("ill_portal_pilot_users"))
			frappe.conf["ill_portal_pilot_users"] = ["a@example.com"]
			self.assertEqual(flags.conf_list("ill_portal_pilot_users"), ["a@example.com"])
			frappe.conf["ill_portal_pilot_users"] = '["b@example.com"]'
			self.assertEqual(flags.conf_list("ill_portal_pilot_users"), ["b@example.com"])
			frappe.conf["ill_portal_pilot_users"] = "[]"
			self.assertEqual(flags.conf_list("ill_portal_pilot_users"), [])
			for invalid in ("a@example.com", '{"a": 1}', [1, 2]):
				with self.subTest(value=invalid):
					frappe.conf["ill_portal_pilot_users"] = invalid
					self.assertIsNone(flags.conf_list("ill_portal_pilot_users"))
			self.assertEqual(frappe.log_error.call_count, 3)


if __name__ == "__main__":
	unittest.main()
